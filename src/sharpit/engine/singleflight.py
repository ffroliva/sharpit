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

    @property
    def active(self) -> str:
        return self._active

    def try_acquire(self, operation: str) -> Callable[[], None] | None:
        """Start ``operation`` without blocking: its idempotent ``release``, or None while another one is running."""
        if not self._lock.acquire(blocking=False):
            return None
        self._active = operation
        released = threading.Lock()

        def release() -> None:
            if released.acquire(blocking=False):  # only the first call frees the flight
                self._active = ""
                self._lock.release()

        return release

    def run[T](self, operation: str, fn: Callable[[], T]) -> T:
        if not self._lock.acquire(blocking=False):
            raise ActionBusy(operation, self._active)
        self._active = operation
        try:
            return fn()
        finally:
            self._active = ""
            self._lock.release()


class Flight:
    """A ``try_acquire``d operation held until its caller and every worker it started are done.

    Python cannot stop a thread, so a timed-out worker keeps the flight: a new request gets 409 until it returns.
    """

    def __init__(self, release: Callable[[], None]) -> None:
        self._release = release
        self._pending = 1  # the caller itself
        self._lock = threading.Lock()

    def worker(self) -> Callable[[], None]:
        """Count one more worker; call the returned function exactly once, when that worker really ends."""
        with self._lock:
            self._pending += 1
        return self.done

    def done(self) -> None:
        with self._lock:
            self._pending -= 1
            last = self._pending == 0
        if last:
            self._release()
