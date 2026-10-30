"""Single-flight admission for explicit actions (port of BootUI ``SingleFlightAction``)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class WaitTimeout(Exception):
    """The caller stopped waiting; the worker keeps running and still holds the lock."""


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

    def run[T](self, operation: str, fn: Callable[[], T], wait_timeout: float | None = None) -> T:
        if not self._lock.acquire(blocking=False):
            raise ActionBusy(operation, self._active)
        self._active = operation
        done = threading.Event()
        outcome: dict[str, Any] = {}

        def worker() -> None:
            try:
                outcome["value"] = fn()
            except BaseException as exc:  # noqa: BLE001 - re-raised in the caller
                outcome["error"] = exc
            finally:
                self._active = ""
                self._lock.release()
                done.set()  # after release, so a returning caller can immediately run again

        try:
            threading.Thread(target=worker, name=f"sharpit-{operation}", daemon=True).start()
        except BaseException:
            self._active = ""
            self._lock.release()
            raise
        if not done.wait(wait_timeout):
            raise WaitTimeout(operation)
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]
