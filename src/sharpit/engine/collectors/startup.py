from __future__ import annotations

from typing import Any


class StartupTimeline:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity

    def record(self, name: str, duration_ms: int | None) -> None:
        return None

    def report(self, query: str | None = None, limit: int | None = None) -> dict[str, Any]:
        return {"steps": [{"id": -1, "parentId": None, "name": "stub", "durationMs": 0, "tags": []}]}
