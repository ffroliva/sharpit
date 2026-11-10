"""Bounded runtime journal; unlike BootUI's JournalQueue it uses no drain thread.

BootUI's heap-relative default has no Python analogue: Python exposes no stable,
portable heap limit for this in-memory buffer, so sharpit uses a fixed 32 MiB cap.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from sharpit.engine.masking import Exposure, Masker

DEFAULT_SOURCES = (
    "http", "sql", "transaction", "connection", "exception", "security", "authorization", "rest-client",
    "cache", "messaging", "scheduled", "log", "mail", "fault-tolerance", "ai", "lifecycle", "gc", "resources",
)  # fmt: skip
DEFAULT_MAX_BYTES = 32 * 1024 * 1024


class JournalSink(Protocol):
    """The publication port used by capture sources."""

    def offer(self, event: Mapping[str, Any]) -> bool: ...

    def records(self, source: str) -> tuple[dict[str, Any], ...]: ...


class _NullSink:
    def offer(self, event: Mapping[str, Any]) -> bool:
        return False

    def records(self, source: str) -> tuple[dict[str, Any], ...]:
        return ()


NULL_SINK: JournalSink = _NullSink()


def _size(value: object) -> int:
    if isinstance(value, str | bytes):
        return len(value)
    if isinstance(value, Mapping):
        return sum(_size(key) + _size(item) for key, item in value.items())
    if isinstance(value, Sequence):
        return sum(_size(item) for item in value)
    return 8


def _mask(value: object, name: str, masker: Masker) -> object:
    shown, hidden = masker.mask(name, value)
    if hidden or shown is None:
        return shown
    if isinstance(shown, str):
        return masker.mask_text(shown)
    if isinstance(shown, Mapping):
        return {str(key): _mask(item, str(key), masker) for key, item in shown.items()}
    if isinstance(shown, list | tuple):
        return [_mask(item, name, masker) for item in shown]
    return shown


class RuntimeJournal:
    """In-memory event ring with O(1) deque append and read-time masking; no dispatcher or background thread."""

    name = "runtime-journal"

    def __init__(
        self,
        *,
        max_events: int = 50_000,
        max_bytes: int = DEFAULT_MAX_BYTES,
        queue_capacity: int = 10_000,
        sources: Sequence[str] = DEFAULT_SOURCES,
        masker: Masker | None = None,
    ) -> None:
        self.max_events = max(1, max_events)
        self.max_bytes = max(1, max_bytes)
        self.queue_capacity = max(1, queue_capacity)
        self.sources = frozenset(sources)
        self.masker = masker or Masker(Exposure.MASKED, True)
        self.run_id = uuid.uuid4().hex[:8]
        self._events: deque[tuple[dict[str, Any], int, int]] = deque()
        self._bytes = 0
        self._accepted: Counter[str] = Counter()
        self._dropped: Counter[str] = Counter()
        self._evicted = 0
        self._binding_bound: str | None = None
        self._accepting = True
        self._lock = threading.Lock()
        self._busy = threading.local()

    def offer(self, event: Mapping[str, Any]) -> bool:
        if getattr(self._busy, "active", False):
            self._dropped["reentrant"] += 1
            return False
        with self._lock:
            self._busy.active = True
            try:
                if not self._accepting:
                    self._dropped["suspended"] += 1
                    return False
                source = event.get("source")
                if not isinstance(source, str) or source not in self.sources:
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
                stored = dict.copy(event) if isinstance(event, dict) else dict(event)
                self._events.append((stored, size, stamp))
                self._bytes += size
                self._accepted[source] += 1
                return True
            finally:
                self._busy.active = False

    def records(self, source: str) -> tuple[dict[str, Any], ...]:
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
        with self._lock:
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
                "recorded": dict(self._accepted),
                "dropped": dict(self._dropped),
                "droppedEvents": sum(self._dropped.values()),
                "previousRuns": [],
                "previousRunsUnavailable": None,
                "agentEvidence": None,
            }
