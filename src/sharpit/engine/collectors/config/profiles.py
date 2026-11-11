"""Profile diff collector (spec §8 Config, BootUI ProfileDiffController)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from sharpit.engine.collectors.config import _display  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.collectors.config.settings_source import (
    KeySafety,
    ProfileSourceDescriptor,
    declared_profile_sources,
    parse_env,
    settings_entries,
)
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import MASK, Exposure

_MAX_ENV_FILE_SIZE = 256 * 1024  # 256 KiB cap
_ENV_PROFILE_PREFIX = ".env."


def _is_safe_symlink(target: Path, real: Path) -> bool:
    return not target.is_symlink() or real.parent == target.parent.resolve()


def _confined(declared: Path, root: Path) -> Path | None:
    try:
        if declared.is_absolute():
            target = declared
            real = target.resolve()
            if not real.is_relative_to(root) or not _is_safe_symlink(target, real):
                return None
        else:
            target = root / declared
            real = target.resolve()
            if not real.is_relative_to(root) or not _is_safe_symlink(target, real):
                return None
        return target if target.is_file() else None
    except (OSError, ValueError):
        return None


def _read(path: Path, encoding: str = "utf-8") -> str | None:
    try:
        with path.open("rb") as fh:
            raw = fh.read(_MAX_ENV_FILE_SIZE + 1)
        if len(raw) > _MAX_ENV_FILE_SIZE:
            return None
        if encoding.lower().replace("_", "-") == "utf-8":
            encoding = "utf-8-sig"
        return raw.decode(encoding)
    except (OSError, UnicodeDecodeError, LookupError, ValueError):
        return None


def _configuration_masked(ctx: SharpitContext) -> dict[type, set[str]] | None:
    """The names Configuration masks, per settings class, from the rows its own panel caches (the same lazy read a
    Configuration GET runs; never a new settings instance). None when that read fails: the caller masks."""
    try:
        per_instance = ctx.lazy("config.settings", lambda: [settings_entries(s, os.environ) for s in ctx.app_settings])
        masked: dict[type, set[str]] = {}
        for instance, (entries, _) in zip(ctx.app_settings, per_instance, strict=True):
            masked.setdefault(type(instance), set()).update(
                e.name for e in entries if _display(ctx, e.name, e.value, e.secret_typed)[1]
            )
        return masked
    except Exception:
        return None


def _mirrors_configuration_mask(
    descriptor: ProfileSourceDescriptor, key: str, masked: dict[type, set[str]] | None
) -> bool:
    """Whether Configuration masks the row of a field ``key`` maps to (same field, same model); True if unknown."""
    rules = descriptor.rules_for(key)
    if not rules:
        return False
    if masked is None:
        return True
    return any(rule.exact_names & masked.get(cast(type, rule.model), set()) for rule in rules)


def _source_properties(
    ctx: SharpitContext,
    source_name: str,
    content: str,
    descriptor: ProfileSourceDescriptor,
    configuration_masked: dict[type, set[str]] | None,
) -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    exposure = ctx.settings.expose_values
    for key, val in parse_env(content):
        safety = descriptor.classify(key)
        if safety is KeySafety.SAFE:
            display_val, masked = _display(ctx, key, val, False)
            if not masked and val is not None and exposure is not Exposure.METADATA_ONLY:
                names = {key, *descriptor.field_names(key)}
                parsed = descriptor.parsed_values(key, val)
                # Configuration's own display decides, by the field's names, on the raw text and on every value it
                # parses into; a value that cannot be parsed for sure is masked
                if (
                    parsed == []
                    or _mirrors_configuration_mask(descriptor, key, configuration_masked)
                    or any(_display(ctx, name, val, False)[1] for name in names)
                    or any(_display(ctx, name, value, False)[1] for name in names for value in parsed or ())
                ):
                    display_val, masked = MASK, True
        elif val is None or exposure is Exposure.METADATA_ONLY:
            display_val, masked = None, False
        elif exposure is Exposure.FULL and safety is KeySafety.UNSAFE_SCALAR:
            display_val, masked = "**********", False  # pydantic's SecretStr placeholder, as Configuration shows
        else:
            display_val, masked = "******", True

        props.append(
            {
                "name": key,
                "value": display_val,
                "source": source_name,
                "origin": None,
                "masked": masked,
                "override": False,
                "description": None,
                "defaultValue": None,
            }
        )
    props.sort(key=lambda p: p["name"])
    return props


def profiles_report(ctx: SharpitContext) -> dict[str, Any]:
    """The masked, profile-grouped configuration view for the Profile Diff panel."""
    profile_sources: list[dict[str, Any]] = []
    root = Path.cwd().resolve()
    descriptors = declared_profile_sources(ctx.app_settings)
    configuration_masked = _configuration_masked(ctx) if descriptors else None

    for descriptor in descriptors:
        declared = descriptor.path
        name = declared.name
        if not name.startswith(_ENV_PROFILE_PREFIX) or len(name) <= len(_ENV_PROFILE_PREFIX):
            continue
        profile = name[len(_ENV_PROFILE_PREFIX) :]
        target = _confined(declared, root)
        if target is None:
            continue
        content = _read(target, descriptor.encoding)
        if content is None:
            continue
        props = _source_properties(ctx, str(declared), content, descriptor, configuration_masked)
        if props:
            profile_sources.append(
                {
                    "sourceName": str(declared),
                    "profile": profile,
                    "properties": props,
                }
            )

    return {
        "activeProfiles": list(ctx.profiles),
        "profileSources": profile_sources,
    }
