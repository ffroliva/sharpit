"""Service facade for Side Effects observations."""

from __future__ import annotations

from typing import Any


class SideEffectsService:
    def __init__(self, capture: Any) -> None:
        self.store = None

    def report(self) -> dict[str, Any]:
        return {"available": False, "unavailableReason": "", "sensors": [{"id": "", "group": "", "label": "", "state": "", "reason": "", "rows": 0, "occurrences": 0, "dropped": 0, "hooks": [], "toggle": None}], "limitations": []}

    def sensor(self, sensor_id: str | None, offset: int | None, limit: int | None) -> dict[str, Any]:
        return {"available": False, "unavailableReason": "", "sensor": {}, "rows": [], "page": {}, "limitations": []}

    def limitations(self, **kwargs: Any) -> list[str]:
        return []

    def ready_at(self) -> int | None:
        return None

    def clear_recording(self) -> None:
        return None
