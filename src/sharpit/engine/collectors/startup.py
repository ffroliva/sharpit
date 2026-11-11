"""Bounded host-startup timeline and its read-only DTO.

Only the FIRST host startup is kept (the same rule as ``ctx.startup_time_ms``): BootUI times the application start once.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any

from sharpit.engine.paging import paged

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


@dataclass(frozen=True)
class StartupStep:
    id: int
    parent_id: int | None
    name: str
    duration_ms: int
    tags: tuple[tuple[str, str], ...]

    def dto(self) -> dict[str, Any]:
        """A fresh dict per call: a caller mutating it never touches the stored step."""
        return {
            "id": self.id,
            "parentId": self.parent_id,
            "name": self.name,
            "durationMs": self.duration_ms,
            "tags": [{"key": key, "value": value} for key, value in self.tags],
        }


class StartupTimeline:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._steps: list[StartupStep] = []
        self._lock = Lock()

    def record(self, name: str, duration_ms: int | None, tags: list[tuple[str, str]] | None = None) -> None:
        if self.capacity <= 0:
            return
        with self._lock:
            if len(self._steps) < self.capacity:
                step = StartupStep(len(self._steps), None, name, max(0, duration_ms or 0), tuple(tags or ()))
                self._steps.append(step)

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {"steps": [step.dto() for step in self._steps]}


def startup_report(ctx: SharpitContext) -> dict[str, Any]:
    if not ctx.settings.startup_enabled:
        return {"steps": []}
    return ctx.startup.report()


def startup_view(ctx: SharpitContext, query: str | None, limit: int) -> dict[str, Any]:
    """``McpAgentViews.startup``: the ``limit`` slowest steps matching ``query`` (name or tag value), plus ``page``."""
    steps: list[dict[str, Any]] = startup_report(ctx)["steps"]
    steps.sort(key=lambda step: (-step["durationMs"], step["id"]))
    listed, page = paged(
        steps, query, None, limit, lambda s: (s["name"], *(v for tag in s["tags"] for v in (tag["key"], tag["value"])))
    )
    return {"steps": listed, "page": page}
