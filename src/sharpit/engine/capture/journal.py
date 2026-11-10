"""Bounded runtime journal behind the ``JournalSink`` port (BootUI ``RuntimeEventSink``, ``RuntimeJournal``).

Deviations from BootUI, for the owner's list:

- No drain thread: BootUI's ``JournalQueue`` hands events to a dispatcher thread; here ``offer`` appends to a
  ``deque`` under a lock in the caller's thread, so ``queueDepth`` is always 0 and ``queue-capacity`` bounds retention.
- Byte bound: BootUI's unset ``max-bytes`` is the smaller of 32 MB and 5 % of the maximum heap. Python exposes no
  stable, portable heap limit for an in-memory buffer, so sharpit uses the fixed 32 MiB cap.
- ``dropped`` is keyed by reason (``reentrant``, ``suspended``, ``source-disabled``, ``max-bytes``,
  ``queue-capacity``, ``failed``), not by source, and counts filtered and suspended offers BootUI returns uncounted.

Sources: the wiring passes ``runtime_journal_sources`` (``settings_registry.JOURNAL_SOURCES`` when unset). A new
source, such as a W6 sensor's (``processes``, ``files``, ``network``, ``code-paths``), is added to
``JOURNAL_SOURCES``; until then its events are refused and counted as ``source-disabled``, never silently lost.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol, cast

from sharpit.engine.masking import Exposure, Masker

DEFAULT_MAX_BYTES = 32 * 1024 * 1024
_SCALAR_BYTES = 8  # estimate for a number, bool or None: the event's own field lengths, never sys.getsizeof

Event = Mapping[str, object]


class JournalSink(Protocol):
    """The publication port capture sources call: ``offer`` never blocks and never raises."""

    def offer(self, event: Event) -> bool: ...

    def records(self, source: str) -> tuple[dict[str, object], ...]: ...


class _NullSink:
    def offer(self, event: Event) -> bool:
        return False

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        return ()


NULL_SINK: JournalSink = _NullSink()


def _size(value: object) -> int:
    if isinstance(value, str | bytes):
        return len(value)
    if isinstance(value, Mapping):
        return sum(_size(key) + _size(item) for key, item in cast("Mapping[object, object]", value).items())
    if isinstance(value, Sequence):
        return sum(_size(item) for item in cast("Sequence[object]", value))
    return _SCALAR_BYTES


def _mask(value: object, name: str, masker: Masker) -> object:
    shown, hidden = masker.mask(name, value)
    if hidden or shown is None:
        return shown
    if isinstance(shown, str):
        return masker.mask_text(shown)
    if isinstance(shown, Mapping):
        return {str(key): _mask(item, str(key), masker) for key, item in cast("Mapping[object, object]", shown).items()}
    if isinstance(shown, list | tuple):
        return [_mask(item, name, masker) for item in cast("Sequence[object]", shown)]
    return shown


class RuntimeJournal:
    """In-memory event ring: O(1) append, raw events kept, masking applied when records are read."""

    name = "runtime-journal"

    def __init__(
        self,
        *,
        max_events: int = 50_000,
        max_bytes: int = DEFAULT_MAX_BYTES,
        queue_capacity: int = 10_000,
        sources: Iterable[str] | None = None,
        masker: Masker | None = None,
    ) -> None:
        self.max_events = max(1, max_events)
        self.max_bytes = max(1, max_bytes)
        self.queue_capacity = max(1, queue_capacity)
        self.sources = None if sources is None else frozenset(sources)  # None: no filter (the wiring always passes one)
        self.masker = masker or Masker(Exposure.MASKED, True)
        self.run_id = uuid.uuid4().hex[:8]
        self._events: deque[tuple[dict[str, object], int, int]] = deque()
        self._bytes = 0
        self._accepted: Counter[str] = Counter()
        self._dropped: Counter[str] = Counter()
        self._evicted = 0
        self._binding_bound: str | None = None
        self._accepting = True
        self._lock = threading.Lock()
        self._busy = threading.local()

    def offer(self, event: Event) -> bool:
        if getattr(self._busy, "active", False):  # an offer made while this thread is inside offer: never recurse
            self._dropped["reentrant"] += 1
            return False
        with self._lock:
            self._busy.active = True
            try:
                return self._append(event)
            except Exception:  # noqa: BLE001 - publishing never raises into the host; the event is dropped and counted
                self._dropped["failed"] += 1
                return False
            finally:
                self._busy.active = False

    def _append(self, event: Event) -> bool:
        if not self._accepting:
            self._dropped["suspended"] += 1
            return False
        source = event.get("source")
        if not isinstance(source, str) or (self.sources is not None and source not in self.sources):
            self._dropped["source-disabled"] += 1
            return False
        size = _size(event)
        if size > self.max_bytes:
            self._dropped["max-bytes"] += 1
            return False
        if len(self._events) >= self.queue_capacity:
            self._dropped["queue-capacity"] += 1
            return False
        stamp = time.time_ns() // 1_000_000
        while self._events and (len(self._events) >= self.max_events or self._bytes + size > self.max_bytes):
            _, removed, _ = self._events.popleft()
            self._bytes -= removed
            self._evicted += 1
            self._binding_bound = "COUNT" if len(self._events) + 1 >= self.max_events else "BYTES"
        self._events.append((dict(event), size, stamp))
        self._bytes += size
        self._accepted[source] += 1
        return True

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        with self._lock:
            events = tuple(event for event, _, _ in self._events if event.get("source") == source)
        return tuple({key: _mask(value, key, self.masker) for key, value in event.items()} for event in events)

    def suspend(self) -> None:
        with self._lock:
            self._accepting = False

    def resume(self) -> None:
        with self._lock:
            self._accepting = True

    def status(self) -> dict[str, Any]:
        """``RuntimeJournalStatusDto``; ``recorded`` lists every configured source, zero included."""
        with self._lock:
            recorded = dict.fromkeys(sorted(self.sources or ()), 0) | dict(self._accepted)
            return {
                "enabled": True,
                "runId": self.run_id,
                "retainedEvents": len(self._events),
                "retainedBytes": self._bytes,
                "maxEvents": self.max_events,
                "maxBytes": self.max_bytes,
                "reservedEvents": 0,
                "reservedCapacity": self.max_events // 10,
                "evictedEvents": self._evicted,
                "bindingBound": self._binding_bound,
                "oldestRetainedAt": self._events[0][2] if self._events else None,
                "queueDepth": 0,
                "queueCapacity": self.queue_capacity,
                "recorded": recorded,
                "dropped": dict(self._dropped),
                "droppedEvents": sum(self._dropped.values()),
                "previousRuns": [],
                "previousRunsUnavailable": None,
                "agentEvidence": None,
            }
