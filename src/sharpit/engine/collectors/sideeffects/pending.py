from __future__ import annotations

from collections import deque
from collections.abc import AbstractSet, Callable, Mapping

PENDING_MILLIS = 30_000
MAX_PENDING = 10_000
READ_RESOLVE_MILLIS = 250
UNKNOWN_ROUTE = "(unknown route)"
ROUTE_HIDDEN = "(route hidden)"


class Pending:
    def __init__(self, reader: Callable[[AbstractSet[str]], dict[str, str]], ready_at: Callable[[], int | None]):
        self.reader = reader
        self.ready_at = ready_at
        self._observations: deque[tuple[Mapping[str, object], str | None]] = deque()
        self.dropped = 0

    @property
    def waiting_count(self) -> int:
        return len(self._observations)

    def add(self, observation: Mapping[str, object], request_id: str | None) -> None:
        if len(self._observations) == MAX_PENDING:
            self.dropped += 1
            return
        self._observations.append((dict(observation), request_id))

    def resolve(self, now: int) -> list[dict[str, object]]:
        del now
        self.reader(frozenset())
        return []

    def clear(self, cleared_at: int) -> None:
        del cleared_at
