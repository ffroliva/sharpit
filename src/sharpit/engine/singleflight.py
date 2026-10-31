"""Single-flight admission for explicit actions (port of BootUI ``SingleFlightAction``)."""

from __future__ import annotations

import threading
from collections.abc import Callable


class ActionBusy(Exception):
    def __init__(self, operation: str, active: str) -> None:
        self.operation = operation
        self.active = active
        super().__init__(f"Operation '{operation}' cannot start while '{active}' is in progress.")

    def body(self) -> dict[str, str]:
        return {
            "error": "sharpit action already in progress",
            "operation": self.operation,
            "activeOperation": self.active,
            "message": str(self),
        }


class SingleFlight:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = ""

    def run[T](self, operation: str, fn: Callable[[], T]) -> T:
        if not self._lock.acquire(blocking=False):
            raise ActionBusy(operation, self._active)
        self._active = operation
        try:
            return fn()
        finally:
            self._active = ""
            self._lock.release()
