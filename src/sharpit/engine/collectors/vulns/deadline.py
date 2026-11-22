"""Whole vulnerability-scan deadline shared by OSV and EPSS requests."""

from __future__ import annotations

import time
from dataclasses import dataclass

DEFAULT_SCAN_TIMEOUT = 60.0
SCAN_DEADLINE_EXCEEDED = "OSV scan deadline exceeded"


class _Clock:
    def __call__(self) -> float:
        return time.monotonic()


_SYSTEM_CLOCK = _Clock()


@dataclass(frozen=True)
class RequestBudget:
    timeout: float
    capped_by_deadline: bool


class ScanDeadline:
    def __init__(self, timeout: float | None, clock: _Clock = _SYSTEM_CLOCK) -> None:
        self._timeout = timeout if timeout is not None and timeout > 0 else DEFAULT_SCAN_TIMEOUT
        self._clock = clock
        self._started = clock()
        self._expired = False

    def remaining(self) -> float:
        remaining = self._timeout - (self._clock() - self._started)
        if remaining <= 0:
            self._expired = True
            return 0.0
        return remaining

    def request_budget(self, per_request: float) -> RequestBudget:
        remaining = self.remaining()
        if remaining <= 0:
            raise TimeoutError(SCAN_DEADLINE_EXCEEDED)
        timeout = per_request if per_request > 0 else 10.0
        return RequestBudget(min(timeout, remaining), remaining <= timeout)

    def check_expired(self) -> bool:
        return self._expired or self.remaining() == 0

    def mark_expired(self) -> None:
        self._expired = True
