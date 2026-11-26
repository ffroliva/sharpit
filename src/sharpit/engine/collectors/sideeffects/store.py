"""One run's Side Effects rows.

Not thread-safe: its service serializes it (ST:39-40).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

MAX_ROWS_PER_SENSOR: int = 500
MAX_ROWS: int = 2_000
EXEMPLARS: int = 3
CONFIRMATIONS: int = 4
OTHER: str = "Other"
RINGED: tuple[str, ...] = ("processes", "files", "security-sinks")


def epoch_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(slots=True)
class StoreRow:
    scope: str
    attribution: str
    sensor: str
    kind: str
    target: str
    call_site: str | None = None
    inside_method: str | None = None
    origin: str | None = None
    location: str | None = None
    count: int = 0
    failed: int = 0
    completed: int = 0
    non_zero_exits: int = 0
    last_exit_status: int | None = None
    total_millis: int = 0
    max_millis: int = 0
    first_seen: int = 0
    last_seen: int = 0
    exemplar_request_ids: list[str] = field(default_factory=list)
    client: str | None = None
    capture: str | None = None
    captured_by: str | None = None
    left_running: int = 0
    requests: int = 0
    parameter: str | None = None
    detail: str | None = None
    confirmed: bool = False
    standalone: bool = False

    @property
    def callSite(self) -> str | None:
        return self.call_site

    @property
    def insideMethod(self) -> str | None:
        return self.inside_method

    @property
    def nonZeroExits(self) -> int:
        return self.non_zero_exits

    @property
    def lastExitStatus(self) -> int | None:
        return self.last_exit_status

    @property
    def totalMillis(self) -> int:
        return self.total_millis

    @property
    def maxMillis(self) -> int:
        return self.max_millis

    @property
    def firstSeen(self) -> int:
        return self.first_seen

    @property
    def lastSeen(self) -> int:
        return self.last_seen

    @property
    def exemplarRequestIds(self) -> list[str]:
        return self.exemplar_request_ids

    @property
    def capturedBy(self) -> str | None:
        return self.captured_by

    @property
    def leftRunning(self) -> int:
        return self.left_running


@runtime_checkable
class SensorRows(Protocol):
    def drain(self, sensor: str) -> list[dict[str, object]]: ...

    def cleared_at(self, sensor: str) -> int: ...


class SideEffectsStore:
    """One run's Side Effects rows.

    Not thread-safe: its service serializes it (ST:39-40).
    """

    def __init__(
        self,
        rows: SensorRows,
        intake: Callable[[Mapping[str, object]], dict[str, object]] = dict,
        clock: Callable[[], int] = epoch_ms,
        max_rows_per_sensor: int = MAX_ROWS_PER_SENSOR,
        max_rows: int = MAX_ROWS,
    ) -> None:
        self._rows = rows
        self._intake = intake
        self._clock = clock
        self._max_rows_per_sensor = max_rows_per_sensor
        self._max_rows = max_rows

    def drain(self) -> None:
        """Drain the sensor rings and aggregate rows."""

    def rows_of(self, sensor: str) -> list[StoreRow]:
        """Return the visible rows of sensor."""
        return []

    def counts(self, sensor: str) -> tuple[int, int]:
        """Return (row_count, occurrences) of visible rows for sensor."""
        return (0, 0)

    def unconfirmed(self) -> int:
        """Return the count of unconfirmed security-sinks matches."""
        return 0

    def folded(self) -> int:
        """Return operations counted in Other rows."""
        return 0

    def clears(self) -> int:
        """Return how many recording clears were observed."""
        return 0

    def cleared(self) -> int:
        """Return rows dropped because their timestamp was not after a clear."""
        return 0

    def clear(self, now: int) -> None:
        """Clear store state at now."""
