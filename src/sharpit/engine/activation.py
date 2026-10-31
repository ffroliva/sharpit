"""Fail-closed activation decision (port of BootUI ``BootUiActivationCondition.resolve``; contract 10, spec 7.3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sharpit.engine.guard import remote_access_configured
from sharpit.settings import SharpitSettings, parse_mode


@dataclass(frozen=True)
class ActivationStatus:
    enabled: bool
    localhost_only: bool
    reason: str
    warnings: tuple[str, ...]

    def to_dto(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "localhostOnly": self.localhost_only,
            "reason": self.reason,
            "warnings": list(self.warnings),
        }


def active_profiles(settings: SharpitSettings, environ: Mapping[str, str]) -> list[str]:
    """Union of the ``profile_vars`` env vars: comma-split, trimmed, lower-cased, de-duplicated in order."""
    seen: dict[str, None] = {}
    for var in settings.profile_vars:
        for part in environ.get(var, "").split(","):
            if p := part.strip().lower():
                seen.setdefault(p)
    return list(seen)


def decide(settings: SharpitSettings, profiles: Sequence[str], dev_signal: str | None) -> ActivationStatus:
    warnings = list(settings.warnings)
    localhost_only = not remote_access_configured(settings)  # sharpit: trusted proxies and gateway trust count too

    def result(enabled: bool, reason: str) -> ActivationStatus:
        return ActivationStatus(enabled, localhost_only, reason, tuple(warnings))

    mode = parse_mode(settings.enabled)
    if mode is None:
        return result(False, f"Disabled: invalid SHARPIT_ENABLED value '{settings.enabled}'")

    active = {p.strip().lower() for p in profiles}
    for profile in settings.disabled_profiles:
        if profile in active:
            if mode == "ON":
                warnings.append(
                    f"Profile '{profile}' is in SHARPIT_DISABLED_PROFILES but SHARPIT_ENABLED=ON forces it on."
                )
                return result(True, f"Explicitly enabled (SHARPIT_ENABLED=ON) despite disabled profile '{profile}'")
            return result(False, f"Disabled because active profile '{profile}' is in SHARPIT_DISABLED_PROFILES")

    if mode == "OFF":
        return result(False, "Disabled by SHARPIT_ENABLED=OFF")
    if mode == "ON":
        return result(True, "Enabled by SHARPIT_ENABLED=ON")
    for profile in settings.enabled_profiles:
        if profile in active:
            return result(True, f"Enabled by active profile '{profile}'")
    if dev_signal:
        return result(True, f"Enabled because a reloading development server was detected ({dev_signal})")
    return result(False, "Disabled: no enabled profile and no reloading development server detected")
