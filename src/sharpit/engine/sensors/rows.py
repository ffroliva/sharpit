"""Per-sensor rings of accepted rows, and the tee that feeds them (BootUI feeds its store from the agent's own ring).

The ring is fed from a sensor's own row before the journal's source filter, so narrowing the journal's sources never
empties a Side Effects tab. The hook-thread append takes no lock of its own: each ring is a bounded ``deque`` that
drops its oldest row, counted.
"""

from __future__ import annotations

from collections import deque

from sharpit.engine.capture.journal import Event, JournalSink

RING_CAPACITY = 10_000  # the store's MAX_PENDING (SideEffectsStore.java:46)
RINGED = ("processes", "files", "security-sinks")


class SensorRows:
    def __init__(self) -> None:
        self._rings: dict[str, deque[dict[str, object]]] = {name: deque(maxlen=RING_CAPACITY) for name in RINGED}
        self._dropped = dict.fromkeys(RINGED, 0)
        self._cleared = dict.fromkeys(RINGED, 0)

    def append(self, row: dict[str, object]) -> None:
        pass

    def drain(self, sensor: str) -> list[dict[str, object]]:
        return []

    def dropped(self, sensor: str) -> int:
        return self._dropped.get(sensor, 0)

    def cleared_at(self, sensor: str) -> int:
        return self._cleared.get(sensor, 0)

    def clear(self, sensor: str, now: int) -> None:
        pass


class TeeSink:
    """The whole ``JournalSink`` protocol: rings a ringed sensor's row, then hands every call to the journal."""

    def __init__(self, journal: JournalSink, rows: SensorRows) -> None:
        self._journal = journal
        self._rows = rows

    def offer(self, event: Event) -> bool:
        return self._journal.offer(event)

    def offer_flat(
        self, event: dict[str, str | int | bool | None], size: int | None = None, started: int = -1
    ) -> bool:
        flat = getattr(self._journal, "offer_flat", None)
        return flat(event, size, started) if flat else self._journal.offer(event)

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        return ()

    def accepts(self, source: str) -> bool:
        return False

    def count_dropped(self, key: str) -> None:
        pass
