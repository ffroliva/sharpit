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
        self._rings: dict[object, deque[dict[str, object]]] = {name: deque(maxlen=RING_CAPACITY) for name in RINGED}
        self._dropped: dict[object, int] = dict.fromkeys(RINGED, 0)
        self._cleared: dict[str, int] = dict.fromkeys(RINGED, 0)

    def append(self, row: dict[str, object]) -> None:
        source = row.get("source")
        if (ring := self._rings.get(source)) is None:
            return
        if len(ring) == RING_CAPACITY:
            # shortcut: two racing appends may count one drop twice or not at all; the count is advisory
            self._dropped[source] += 1
        ring.append(row)

    def drain(self, sensor: str) -> list[dict[str, object]]:
        ring = self._rings.get(sensor)
        if ring is None:
            return []
        taken: list[dict[str, object]] = []
        for _ in range(len(ring)):
            try:
                taken.append(ring.popleft())
            except IndexError:  # another reader emptied it
                break
        return taken

    def dropped(self, sensor: str) -> int:
        return self._dropped.get(sensor, 0)

    def cleared_at(self, sensor: str) -> int:
        return self._cleared.get(sensor, 0)

    def clear(self, sensor: str, now: int) -> None:
        if (ring := self._rings.get(sensor)) is not None:
            ring.clear()
            self._cleared[sensor] = now


class TeeSink:
    """The whole ``JournalSink`` protocol: rings a ringed sensor's row, then hands every call to the journal."""

    def __init__(self, journal: JournalSink, rows: SensorRows) -> None:
        self._journal = journal
        self._rows = rows
        self._rings = rows._rings  # pyright: ignore[reportPrivateUsage]
        self._rings_get = rows._rings.get  # pyright: ignore[reportPrivateUsage]
        self._dropped = rows._dropped  # pyright: ignore[reportPrivateUsage]
        self._flat = hasattr(journal, "offer_flat")

    def offer(self, event: Event) -> bool:
        try:  # noqa: SIM105 - publishing never raises into the host
            self._rows.append(dict(event))
        except Exception:  # noqa: BLE001, S110
            pass
        return self._journal.offer(event)

    def offer_flat(self, event: dict[str, str | int | bool | None], size: int | None = None, started: int = -1) -> bool:
        try:  # publishing never raises into the host
            if (ring := self._rings_get(source := event["source"])) is not None:
                if len(ring) == RING_CAPACITY:
                    self._dropped[source] += 1
                ring.append(event)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001, S110
            pass
        if self._flat:
            return self._journal.offer_flat(event, size, started)  # type: ignore[attr-defined, no-any-return]
        return self._journal.offer(event)

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        return self._journal.records(source)

    def accepts(self, source: str) -> bool:
        return self._journal.accepts(source)

    def count_dropped(self, key: str) -> None:
        self._journal.count_dropped(key)
