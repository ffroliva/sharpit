"""Profile diff collector (spec §8 Config, BootUI ProfileDiffController)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sharpit.engine.collectors.config import _display  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.collectors.config.settings_source import (
    KeySafety,
    ProfileSourceDescriptor,
    declared_profile_sources,
    parse_env,
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


def _source_properties(
    ctx: SharpitContext,
    source_name: str,
    content: str,
    descriptor: ProfileSourceDescriptor,
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

    for descriptor in declared_profile_sources(ctx.app_settings):
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
        props = _source_properties(ctx, str(declared), content, descriptor)
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
