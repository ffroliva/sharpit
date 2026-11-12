"""The Profile resources floor (BootUI ``ResourceProfileService.java:85-125``): the three calls start nothing.

BootUI starts a bounded JFR session. sharpit has no resource sampler (proposed deviation P-I1), so status, start and
stop all answer BootUI's ``UNAVAILABLE`` shape with the reason: no journal, no ``resources`` source, or no sampler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sharpit.engine.collectors.insights.service import DISABLED

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

RESOURCES_OFF = (
    "Profile resources joins samples to the request segments the runtime journal's resources source measures: "
    "add resources to SHARPIT_RUNTIME_JOURNAL_SOURCES."
)
NO_SAMPLER = "sharpit has no resource sampler."


class ResourceProfile:
    def __init__(self, journal: Any, max_duration: float) -> None:
        self.journal = journal
        self.max_duration = max_duration

    def status(self) -> dict[str, Any]:
        return self._floor()

    def start(self) -> dict[str, Any]:
        return self._floor()

    def stop(self) -> dict[str, Any]:
        return self._floor()

    def _reason(self) -> str:
        if self.journal is None:
            return DISABLED
        sources = self.journal.sources  # None: no filter
        return NO_SAMPLER if sources is None or "resources" in sources else RESOURCES_OFF

    def _floor(self) -> dict[str, Any]:
        return {
            "state": "UNAVAILABLE", "reason": self._reason(), "sampler": None, "startedAt": None, "endsAt": None,
            "finishedAt": None, "maxDurationSeconds": int(self.max_duration), "cpuSamples": 0, "outsideSamples": 0,
            "requests": 0, "routes": [], "routesOmitted": 0, "limitations": [],
        }  # fmt: skip


def resource_profile(ctx: SharpitContext) -> ResourceProfile:
    return ctx.lazy(
        "runtime-insights.profile",
        lambda: ResourceProfile(ctx.capture.journal, ctx.settings.resources_jfr_max_duration),
    )
