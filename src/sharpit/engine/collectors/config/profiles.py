"""Profile diff collector (spec §8 Config, BootUI ProfileDiffController)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sharpit.engine.collectors.config import _display  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.collectors.config.settings_source import declared_env_files
from sharpit.engine.context import SharpitContext

_MAX_ENV_FILE_SIZE = 256 * 1024  # 256 KiB cap
_ENV_PROFILE_PREFIX = ".env."


def _parse_quoted(val: str) -> str:
    if val.startswith("'"):
        end = val.find("'", 1)
        return val[1:end] if end != -1 else val[1:]
    escaped = False
    end = -1
    for idx in range(1, len(val)):
        ch = val[idx]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            end = idx
            break
    inner = val[1:end] if end != -1 else val[1:]
    return inner.replace(r"\"", '"').replace(r"\\", "\\")


def _parse_env_value(val: str) -> str | None:
    val = val.strip()
    if not val:
        return None
    if val.startswith(("'", '"')):
        return _parse_quoted(val)
    return re.sub(r"\s+#.*$", "", val).strip()


def _parse_env_line(line: str) -> tuple[str, str | None] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, _, val = line.partition("=")
    key = re.sub(r"^export\s+", "", key.strip()).strip()
    if not key:
        return None
    return key, _parse_env_value(val)


def parse_env_lines(content: str) -> list[tuple[str, str | None]]:
    """Parse .env lines into key-value pairs without interpolation."""
    content = content.removeprefix("\ufeff")
    results: list[tuple[str, str | None]] = []
    for line in content.splitlines():
        item = _parse_env_line(line)
        if item is not None:
            results.append(item)
    return results


def _is_safe_symlink(target: Path, real: Path) -> bool:
    return not target.is_symlink() or real.parent == target.parent.resolve()


def _read_env_source(declared: Path, root: Path) -> str | None:
    try:
        if declared.is_absolute():
            target = declared
            if not _is_safe_symlink(target, target.resolve()):
                return None
        else:
            target = Path.cwd() / declared
            real = target.resolve()
            if not real.is_relative_to(root) or not _is_safe_symlink(target, real):
                return None

        if not target.is_file() or target.stat().st_size > _MAX_ENV_FILE_SIZE:
            return None
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _source_properties(ctx: SharpitContext, source_name: str, content: str) -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    for key, val in parse_env_lines(content):
        display_val, masked = _display(ctx, key, val, False)
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

    for declared in declared_env_files(ctx.app_settings):
        name = declared.name
        if not name.startswith(_ENV_PROFILE_PREFIX) or len(name) <= len(_ENV_PROFILE_PREFIX):
            continue
        profile = name[len(_ENV_PROFILE_PREFIX) :]
        content = _read_env_source(declared, root)
        if content is None:
            continue
        props = _source_properties(ctx, str(declared), content)
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
