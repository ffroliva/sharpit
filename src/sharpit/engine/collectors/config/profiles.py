"""Profile diff collector (spec §8 Config, BootUI ProfileDiffController)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.context import SharpitContext


def parse_env_lines(_content: str) -> list[tuple[str, str | None]]:
    """Parse .env lines into key-value pairs without interpolation."""
    return []


def profiles_report(ctx: SharpitContext) -> dict[str, Any]:
    """The masked, profile-grouped configuration view for the Profile Diff panel."""
    return {
        "activeProfiles": list(ctx.profiles),
        "profileSources": [],
    }
