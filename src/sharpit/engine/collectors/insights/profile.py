"""The Profile resources floor (stub: W5c I2 red)."""

from __future__ import annotations

from typing import Any


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

    def _floor(self) -> dict[str, Any]:
        keys = (
            "state", "reason", "sampler", "startedAt", "endsAt", "finishedAt", "maxDurationSeconds", "cpuSamples",
            "outsideSamples", "requests", "routes", "routesOmitted", "limitations",
        )  # fmt: skip
        return dict.fromkeys(keys)


RESOURCES_OFF = ""
NO_SAMPLER = ""
