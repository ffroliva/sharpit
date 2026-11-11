"""Bounded host-startup timeline and its read-only DTO."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class StartupStep:
    id: int
    parentId: int | None
    name: str
    durationMs: int
    tags: list[dict[str, str]]


class StartupTimeline:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._steps: list[StartupStep] = []
        self._lock = Lock()

    def record(self, name: str, duration_ms: int | None) -> None:
        if self.capacity <= 0:
            return
        with self._lock:
            if len(self._steps) < self.capacity:
                self._steps.append(StartupStep(len(self._steps), None, name, max(0, duration_ms or 0), []))

    def report(self, query: str | None = None, limit: int | None = None) -> dict[str, Any]:
        with self._lock:
            steps = [step for step in self._steps if step.name != "sharpit.install"]
        if query:
            needle = query.casefold()
            steps = [step for step in steps if needle in step.name.casefold()]
        if limit is not None:
            steps = steps[: max(0, limit)]
        return {"steps": [vars(step) for step in steps]}


def startup_report(ctx: Any, query: str | None = None, limit: int | None = None) -> dict[str, Any]:
    if not ctx.settings.startup_enabled:
        return {"steps": []}
    return ctx.startup.report(query, limit)
