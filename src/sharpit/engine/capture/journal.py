"""Bounded runtime journal behind the ``JournalSink`` port (BootUI ``RuntimeEventSink``, ``RuntimeJournal``).

Deviations from BootUI, for the owner's list:

- No drain thread: BootUI's ``JournalQueue`` hands events to a dispatcher thread; here ``offer`` appends to a
  ``deque`` under a lock in the caller's thread, so ``queueDepth`` is always 0 and ``queue-capacity`` is unused: it is
  parsed with BootUI's default and reported as ``queueCapacity``, but nothing waits in a queue, so nothing is refused at
  it. Retention is a ring: at ``max-events`` or ``max-bytes`` the oldest event is evicted and counted.
- Byte bound: BootUI's unset ``max-bytes`` is the smaller of 32 MB and 5 % of the maximum heap. Python exposes no
  stable, portable heap limit for an in-memory buffer, so sharpit uses the fixed 32 MiB cap.
- ``dropped`` is keyed by source, as BootUI's is, but also counts the offers BootUI returns uncounted: while
  suspended, from a source not configured, and one event larger than the whole byte bound. An offer whose source
  cannot be read is counted under a key no source has: ``reentrant`` (made by a thread that holds the lock: inside an
  append or a read) or ``failed`` (a
  non-string source, or an event that raised or nested too deep while it was copied).

Sources: the wiring passes ``runtime_journal_sources`` (``settings_registry.JOURNAL_SOURCES`` when unset). A new
source, such as a W6 sensor's (``processes``, ``files``, ``network``, ``code-paths``), is added to
``JOURNAL_SOURCES``; until then its events are refused and counted as ``source-disabled``, never silently lost.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol, cast

from sharpit.engine import sqltext
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect

DEFAULT_MAX_BYTES = 32 * 1024 * 1024
REENTRANT, FAILED = "reentrant", "failed"  # the dropped keys of offers without a readable source
_MAX_DEPTH = 32  # deeper than any event a sensor builds: a cycle
SCALAR_BYTES = 8  # estimate for a number, bool or None: the event's own field lengths, never sys.getsizeof
_COUNTS = {"ai": frozenset({"inputTokens", "outputTokens"})}  # AiPayload's Long token counts: numbers, not secrets

Event = Mapping[str, object]


class JournalSink(Protocol):
    """The publication port capture sources call: ``offer`` never blocks and never raises."""

    def offer(self, event: Event) -> bool: ...

    def records(self, source: str) -> tuple[dict[str, object], ...]: ...

    def accepts(self, source: str) -> bool: ...

    def count_dropped(self, key: str) -> None: ...


class _NullSink:
    def offer(self, event: Event) -> bool:
        del event  # the port's signature; the null sink takes nothing
        return False

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        del source  # the port's signature; the null sink holds nothing
        return ()

    def accepts(self, source: str) -> bool:
        del source  # the port's signature; the null sink takes nothing
        return False

    def count_dropped(self, key: str) -> None:
        del key  # the port's signature; the null sink counts nothing


NULL_SINK: JournalSink = _NullSink()


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _snapshot(value: object, depth: int = 0) -> tuple[object, int]:
    """A deep, plain copy of ``value`` and its estimated size, in one walk.

    A host changing what it offered later changes neither the stored event nor its charged bytes. Too deep a value (a
    cycle) raises, and the offer is counted failed.
    """
    if depth > _MAX_DEPTH:
        raise ValueError("journal event nested too deep")
    plain = _plain(value)
    if isinstance(plain, str):
        return plain, len(plain)
    if isinstance(plain, Mapping):
        copied: dict[str, object] = {}
        size = 0
        for key, item in cast("Mapping[object, object]", plain).items():
            copied[str(key)], item_size = _snapshot(item, depth + 1)
            size += len(str(key)) + item_size
        return copied, size
    if isinstance(plain, list | tuple):
        items = [_snapshot(item, depth + 1) for item in cast("Sequence[object]", plain)]
        return [item for item, _ in items], sum(size for _, size in items)
    return plain, SCALAR_BYTES


def _flat(event: Event) -> tuple[object, int]:
    """``_snapshot``'s size for a flat event of scalars, without the copy: the caller handed the event over."""
    return event, sum(
        len(key) + (len(value) if isinstance(value, str) else SCALAR_BYTES) for key, value in event.items()
    )


# ported: JournalTextExposure: the runs a SQL shape keeps but cannot tell apart from a value, and what reads two ways
_ALTERNATIVE_QUOTE = re.compile(r"(?i)(?<![\w$])n?q'")
_DOUBLE_QUOTED = re.compile(r'"(?:[^"]|"")*+"?')
_UNREAD_NUMBER = re.compile(r"(?<![\w$.?])\.\d\w*+|\?[xXbB_]\w*+")
_UNTERMINATED_DOLLAR_QUOTE = re.compile(r"\$[^\W\d]\w*+\$.*+|\$\$.*+", re.DOTALL)
_READ_MASKER = Masker(Exposure.MASKED, True)  # compares two readings of a statement; never shown
_QUOTED_KEY = re.compile(r"`(\w++)`(?=\s*+[:=])|\[(\w++)\](?=\s*+[:=])")


_SHOWN = (str, bool, int, float, Mapping, list, tuple)  # what JSON and the masker read as they are


def _plain(value: object) -> object:
    """A value JSON can show: bytes decoded, sets listed, any other object as its text, so masking can read it."""
    if isinstance(value, bytes | bytearray):
        return bytes(value).decode("utf-8", "replace")
    if isinstance(value, memoryview):
        return cast("memoryview[int]", value).tobytes().decode("utf-8", "replace")
    if isinstance(value, set | frozenset):
        return sorted(cast("Iterable[object]", value), key=repr)
    return cast("object", value) if value is None or isinstance(value, _SHOWN) else str(value)


def _nested_comment(sql: str) -> bool:
    """A block comment opened inside another: PostgreSQL nests them, the normalizer closes at the first ``*/``."""
    start = sql.find("/*")
    while start >= 0:
        close, inner = sql.find("*/", start + 2), sql.find("/*", start + 2)
        if inner >= 0 and (close < 0 or inner < close):
            return True
        start = -1 if close < 0 else sql.find("/*", close + 2)
    return False


def _ambiguous(sql: str) -> bool:
    """A statement that reads differently by dialect (``JournalTextExposure.isAmbiguous``)."""
    if _ALTERNATIVE_QUOTE.search(sql) or _nested_comment(sql):
        return True
    if "\\" not in sql:
        return False
    plain = _statement(sql.replace("\\", ""), _READ_MASKER)
    return '"' in sql or plain != _statement(sql, _READ_MASKER)


def _statement(sql: str, masker: Masker) -> str:
    """The statement through the approved SQL text facade (A10): literals as ``?``, secrets masked."""
    return sqltext.statement_shape(masker, sql, Dialect.POSTGRESQL).text


def _literal_free(sql: str, masker: Masker) -> str:
    shape = _DOUBLE_QUOTED.sub("?", _statement(sql, masker))
    shape = _UNTERMINATED_DOLLAR_QUOTE.sub("?", _UNREAD_NUMBER.sub("?", shape))
    if (stray := shape.find("'")) >= 0:  # a quote the normalizer left open: nothing after it is shown
        shape = shape[:stray] + "?"
    return masker.mask_text(_QUOTED_KEY.sub(lambda m: m.group(1) or m.group(2), shape)) or ""


def _sql(sql: str, masker: Masker) -> str:
    """``JournalTextExposure.sql`` under MASKED: the literal-free shape, nothing after an ambiguous first quote."""
    quotes = [i for i in (sql.find("'"), sql.find('"')) if i >= 0]
    first_quote = min(quotes, default=-1)
    cut = sql.find("#")  # a MySQL comment, an operator elsewhere: nothing after it is shown
    if first_quote >= 0 and (cut < 0 or first_quote < cut) and _ambiguous(sql):
        cut = first_quote
    return _literal_free(sql, masker) if cut < 0 else _literal_free(sql[:cut], masker) + " ?"


def _path(path: str, masker: Masker) -> str:
    """Secret-like segments masked, and every ``;name=value`` matrix parameter masked whole (session ids live there)."""
    segments: list[str] = []
    for segment in masker.mask_path(path).split("/"):
        head, *params = segment.split(";")
        segments.append(";".join([head, *(f"{p.partition('=')[0]}={MASK}" if "=" in p else MASK for p in params)]))
    return "/".join(segments)


def _verbatim(masker: Masker) -> bool:
    """FULL exposure or secret masking off: text is shown as recorded (sharpit's own token still hidden)."""
    shown, hidden = masker.mask("password", "x")
    return shown is not None and not hidden


def _mask(value: object, name: str, masker: Masker) -> object:
    shown, hidden = masker.mask(name, _plain(value))
    if hidden or shown is None:
        return shown
    if isinstance(shown, str):
        if _verbatim(masker):
            return masker.mask_text(shown)
        rule = {"sql": _sql, "path": _path}.get(name.lower())
        return rule(shown, masker) if rule else masker.mask_text(shown)
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
        self._lock = threading.RLock()
        self._owned = cast("Any", self._lock)._is_owned  # noqa: SLF001  # whether THIS thread holds the lock

    def offer(self, event: Event) -> bool:
        return self._offer(event, _snapshot)

    def offer_flat(self, event: dict[str, str | int | bool | None], size: int | None = None) -> bool:
        """``offer`` for an event of plain scalars the caller hands over and never touches again: no deep copy.

        A per-statement producer passes ``size``, which must equal what ``_flat`` charges (its test proves it); a size
        below 1 is not trusted, and the event is walked instead, so it never bypasses ``max_bytes``.
        """
        if size is None or size < 1:
            return self._offer(event, _flat)
        return self._offer(event, lambda stored: (stored, size))

    def _offer(self, event: Event, store: Callable[[Event], tuple[object, int]]) -> bool:
        if self._owned():  # made while this thread is inside an append or a read (a finalizer): never recurse
            self.count_dropped(REENTRANT)  # before any copy of the event, so no host code runs under the lock
            return False
        with self._lock:
            try:
                return self._append(event, store)
            except Exception:  # noqa: BLE001 - publishing never raises into the host; the event is dropped and counted
                self._dropped[FAILED] += 1
                return False

    def _append(self, event: Event, store: Callable[[Event], tuple[object, int]]) -> bool:
        source = event.get("source")
        if not isinstance(source, str):
            self._dropped[FAILED] += 1
            return False
        if not self._accepting or (self.sources is not None and source not in self.sources):
            self._dropped[source] += 1  # suspended, or a source not configured: counted, never silently lost
            return False
        stored, size = store(event)
        if size > self.max_bytes:
            self._dropped[source] += 1  # one event larger than the whole byte bound
            return False
        stamp = time.time_ns() // 1_000_000
        while self._events and (len(self._events) >= self.max_events or self._bytes + size > self.max_bytes):
            self._binding_bound = "COUNT" if len(self._events) >= self.max_events else "BYTES"
            _, removed, _ = self._events.popleft()  # a ring: the oldest event makes room, counted as evicted
            self._bytes -= removed
            self._evicted += 1
        self._events.append((cast("dict[str, object]", stored), size, stamp))
        self._bytes += size
        self._accepted[source] += 1
        return True

    def accepts(self, source: str) -> bool:
        """Whether ``source`` is a configured source: a paused SQL Trace panel still feeds the journal then."""
        return self._accepting and (self.sources is None or source in self.sources)

    def count_dropped(self, key: str) -> None:
        """Count one offer a producer refused itself (a source not accepted, a record raised while it was building an
        event). Under the lock the other writers hold, which is reentrant: a producer may call it inside ``offer``."""
        with self._lock:
            self._dropped[key] += 1

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        with self._lock:
            events = tuple(event for event, _, _ in self._events if event.get("source") == source)
        return self._masked(source, events)

    def _masked(
        self, source: str, events: Iterable[dict[str, object]], memo: dict[tuple[str, str | None], object] | None = None
    ) -> tuple[dict[str, object], ...]:
        counts = _COUNTS.get(source, frozenset())
        masker = self.masker
        # one read sees the same texts over and over (a statement's shape, a thread name, a request's id on each of its
        # events): each is masked once. Only text and None are kept, whose result is immutable and depends on nothing
        # but (key, value) during one read; ``view`` shares one memo across its sources.
        memo = {} if memo is None else memo

        def shown(key: str, value: object) -> object:
            if key in counts and _count(value):
                return value
            kind = type(value)
            if kind is int or kind is bool or kind is float:
                return masker.mask(key, value)[0]  # what ``_mask`` answers for a plain number, without its walk
            if value is not None and kind is not str:
                return _mask(value, key, masker)
            entry = (key, cast("str | None", value))
            if entry not in memo:
                memo[entry] = _mask(value, key, masker)
            return memo[entry]

        return tuple({key: shown(key, value) for key, value in event.items()} for event in events)

    def view(
        self, sources: Iterable[str]
    ) -> tuple[dict[str, Any], dict[str, tuple[dict[str, object], ...]], int | None]:
        """``status()``, ``records(s)`` per source and the newest event's epoch ms from ONE lock acquisition."""
        held: dict[str, list[dict[str, object]]] = {s: [] for s in sources}
        with self._lock:
            status = self._status()
            newest = None
            for event, _, stamp in self._events:  # one pass, whatever the number of sources read
                if (bucket := held.get(cast("str", event.get("source")))) is not None:
                    bucket.append(event)
                newest = stamp if newest is None or stamp > newest else newest  # BootUI takes the max epoch
        memo: dict[tuple[str, str | None], object] = {}
        return status, {s: self._masked(s, events, memo) for s, events in held.items()}, newest

    def suspend(self) -> None:
        with self._lock:
            self._accepting = False

    def resume(self) -> None:
        with self._lock:
            self._accepting = True

    def discard(self) -> None:
        with self._lock:
            self._events.clear()
            self._bytes = 0

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status()

    def _status(self) -> dict[str, Any]:
        """``RuntimeJournalStatusDto``; ``recorded`` lists only sources with events (``byPropertyName``)."""
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
