"""The journal keeps a compact record per event and builds the dict when it is read (lane perf sql-journal-compact).

The compact offer (``RuntimeJournal.offer_record`` with a ``RecordFields`` layout) is what P-sql uses; other producers
stay on ``offer_flat`` until they switch; ``offer`` and ``offer_flat`` keep working and store the same record.
"""

from __future__ import annotations

import gc
import threading
from collections import deque
from typing import Any

import pytest

from sharpit.engine.capture import journal as journal_module
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights import snapshot
from sharpit.engine.masking import Exposure, Masker

KEYS = ("source", "sql", "traceId", "thread", "durationNanos", "failed", "ratio")
EVENT = dict(zip(KEYS, ("sql", "select * from pets where id = ?", None, "MainThread", 42_000, False, 0.5), strict=True))


def _compact(journal: RuntimeJournal) -> tuple[Any, Any]:
    """The compact offer and the layout class: an assertion, not a crash, while they do not exist."""
    layout, offer = getattr(journal_module, "RecordFields", None), getattr(journal, "offer_record", None)
    assert layout is not None, "the journal has no RecordFields layout"
    assert offer is not None, "the journal has no compact offer"
    return offer, layout


def _dicts_reachable(root: object) -> int:
    seen: set[int] = set()
    todo, found = [root], 0
    while todo:
        item = todo.pop()
        if id(item) in seen or isinstance(item, type):
            continue
        seen.add(id(item))
        found += isinstance(item, dict)
        todo.extend(gc.get_referents(item))
    return found


def _charged(value: object) -> int:
    """The journal's size estimate, recounted from what a read shows."""
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(len(key) + _charged(item) for key, item in value.items())
    if isinstance(value, list):
        return sum(map(_charged, value))
    return 8


def test_the_ring_holds_no_dict_for_a_flat_event() -> None:
    journal = RuntimeJournal(max_events=10, max_bytes=10_000)
    assert journal.offer_flat(dict(EVENT)) is True  # type: ignore[arg-type]
    assert journal.offer(dict(EVENT)) is True
    assert _dicts_reachable(journal._events) == 0


def test_a_compact_offer_stores_the_very_tuple_it_was_given_and_no_dict() -> None:
    journal = RuntimeJournal(max_events=10, max_bytes=10_000)
    offer, fields = _compact(journal)
    layout = fields("sql", *KEYS[1:])
    values = tuple(EVENT.values())
    assert offer(layout, values) is True
    assert _dicts_reachable(journal._events) == 0
    assert any(item is values for item in gc.get_referents(*journal._events))


def test_a_compact_offer_reads_exactly_as_the_same_event_offered_flat() -> None:
    flat, compact = (RuntimeJournal(max_events=10, max_bytes=10_000, sources=("sql",)) for _ in range(2))
    offer, fields = _compact(compact)
    layout = fields("sql", *KEYS[1:])
    for _ in range(3):
        assert flat.offer_flat(dict(EVENT)) is True  # type: ignore[arg-type]
        assert offer(layout, tuple(EVENT.values())) is True
    assert compact.records("sql") == flat.records("sql")
    assert [list(record) for record in compact.records("sql")] == [list(KEYS)] * 3
    assert compact.status()["retainedBytes"] == flat.status()["retainedBytes"]
    assert compact.status()["recorded"] == {"sql": 3}
    assert snapshot.project(compact).records == snapshot.project(flat).records


def test_a_compact_offer_is_refused_and_counted_like_any_other() -> None:
    journal = RuntimeJournal(max_events=10, max_bytes=200, sources=("sql",))
    offer, fields = _compact(journal)
    layout = fields("sql", *KEYS[1:])
    values = tuple(EVENT.values())
    assert offer(fields("http", "path"), ("http", "/pets")) is False  # a source not configured
    assert offer(layout, ("sql", "x" * 300, *values[2:])) is False  # larger than the whole byte bound
    assert offer(layout, values[:-1]) is False  # not the layout's length
    assert offer(layout, ("http", *values[1:])) is False  # not the layout's source
    assert offer(layout, list(values)) is False  # a list can change after the offer
    assert offer(layout, (*values[:-1], {"nested": 1})) is False  # not a scalar: its size is not the estimate
    journal.suspend()
    assert offer(layout, values) is False
    assert journal.status()["dropped"] == {"http": 1, "sql": 2, "failed": 4}
    assert journal.status()["retainedEvents"] == 0


def test_a_compact_offer_with_a_size_below_one_still_charges_the_record() -> None:
    journal = RuntimeJournal(max_events=10, max_bytes=100)
    offer, fields = _compact(journal)
    layout = fields("sql", *KEYS[1:])
    values = tuple(EVENT.values())
    assert offer(layout, ("sql", "x" * 200, *values[2:]), -5) is False
    assert offer(layout, ("sql", "select 1", *values[2:]), 0) is True
    assert journal.status()["retainedBytes"] == sum(map(len, KEYS)) + len("sql" + "select 1" + "MainThread") + 4 * 8


def _offer_one(journal: RuntimeJournal, offer: Any, layout: Any, refused: Any, i: int) -> bool:
    """The stress mix by offer number: copied, flat, a refused source, an oversized record, or a compact record."""
    values = tuple(EVENT.values())
    if i % 4 == 0:
        return journal.offer({"source": "http", "path": "/pets", "tags": ["a", "b"], "i": i})
    if i % 4 == 1:
        return journal.offer_flat(dict(EVENT))  # type: ignore[arg-type]
    if i % 100 == 2:
        return offer(refused, ("gc", i))  # a source not configured: dropped
    if i % 100 == 3:
        return offer(layout, ("sql", "x" * (journal.max_bytes + 1), *values[2:]))  # over the byte bound: dropped
    return offer(layout, ("sql", "select ?" * (1 + i % 40), *values[2:]))


LARGEST = sum(map(len, KEYS)) + len("sql" + "select ?" * 40 + "MainThread") + 4 * 8  # the biggest record the mix keeps


@pytest.mark.parametrize(
    ("max_events", "max_bytes", "bound", "full_events", "full_bytes"),
    [(64, 100_000, "COUNT", 64, 0), (100_000, 6000, "BYTES", 1, 6000 - LARGEST)],
)
def test_threads_offering_both_ways_end_with_exact_counts_inside_the_bounds(
    max_events: int, max_bytes: int, bound: str, full_events: int, full_bytes: int
) -> None:
    """Stress: every offer is kept, evicted or dropped, exactly once, and no reader ever sees a bound exceeded.

    Each case fills one bound and never reaches the other, so the ring ends full by that bound and not over it."""
    threads, per_thread = 4, 3000
    journal = RuntimeJournal(
        max_events=max_events, max_bytes=max_bytes, sources=("sql", "http"), masker=Masker(Exposure.FULL, False)
    )
    offer, fields = _compact(journal)
    layout, refused = fields("sql", *KEYS[1:]), fields("gc", "pauseNanos")
    accepted = [0] * threads
    seen: list[tuple[int, int]] = []
    done = threading.Event()

    def publish(worker: int) -> None:
        accepted[worker] = sum(_offer_one(journal, offer, layout, refused, i) for i in range(per_thread))

    def read() -> None:
        while not done.is_set():
            status = journal.status()
            seen.append((status["retainedEvents"], status["retainedBytes"]))

    reader = threading.Thread(target=read)
    workers = [threading.Thread(target=publish, args=(n,)) for n in range(threads)]
    for thread in (reader, *workers):
        thread.start()
    for worker in workers:
        worker.join()
    done.set()
    reader.join()
    status = journal.status()
    seen.append((status["retainedEvents"], status["retainedBytes"]))
    assert status["bindingBound"] == bound
    assert status["retainedEvents"] >= full_events
    assert status["retainedBytes"] > full_bytes
    dropped_each = sum(1 for i in range(per_thread) if i % 4 > 1 and i % 100 in (2, 3))
    assert status["dropped"] == {"gc": threads * dropped_each // 2, "sql": threads * dropped_each // 2}
    assert sum(accepted) == threads * (per_thread - dropped_each)
    assert sum(status["recorded"].values()) == sum(accepted)
    assert status["evictedEvents"] + status["retainedEvents"] == sum(accepted)
    assert max(events for events, _ in seen) <= max_events
    assert max(size for _, size in seen) <= max_bytes
    held = (*journal.records("sql"), *journal.records("http"))  # verbatim at FULL: what was charged can be recounted
    assert len(held) == status["retainedEvents"]
    assert sum(map(_charged, held)) == status["retainedBytes"]


def _layout(journal: RuntimeJournal) -> tuple[Any, Any]:
    offer, fields = _compact(journal)
    return offer, fields("sql", *KEYS[1:])


def test_every_offer_made_while_the_thread_copies_an_event_is_dropped_as_reentrant() -> None:
    """Re-entrancy as on the base: the copy runs the event's own code, and what that code offers (any of the three
    offers) is dropped and counted, so no producer can recurse into the journal or deadlock it."""
    journal = RuntimeJournal(max_events=10, max_bytes=10_000, sources=("sql", "http"))
    offer, layout = _layout(journal)
    outcomes: list[bool] = []

    def nosy() -> None:
        outcomes.append(journal.offer({"source": "http"}))
        outcomes.append(journal.offer_flat({"source": "http"}))
        outcomes.append(offer(layout, tuple(EVENT.values())))

    class Nosy(dict):  # type: ignore[type-arg]
        def items(self) -> Any:  # the deep copy reads them
            nosy()
            return super().items()

        def values(self) -> Any:  # the flat walk reads them
            nosy()
            return super().values()

    assert journal.offer(Nosy(source="http", n=1)) is True
    assert outcomes == [False, False, False]
    assert journal.status()["dropped"] == {"reentrant": 3}
    assert journal.status()["recorded"] == {"http": 1}
    assert journal.offer_flat(Nosy(source="http", n=1)) is True  # the flat walk marks the thread busy as well
    assert outcomes == [False] * 6
    assert journal.status()["dropped"] == {"reentrant": 6}


def test_a_finalizer_that_offers_during_the_append_is_dropped_and_the_ring_stays_exact() -> None:
    """A producer that logs from a finalizer (P-log's WARN while an event is being built) can run inside a compact
    append, where the lock is held by this very thread: the nested offer is counted ``reentrant``, never appended."""
    journal = RuntimeJournal(max_events=10, max_bytes=10_000, sources=("sql", "log"))
    offer, layout = _layout(journal)
    nested: list[bool] = []

    class Finalized:
        def __del__(self) -> None:
            nested.append(journal.offer({"source": "log", "level": "WARN"}))
            nested.append(offer(layout, tuple(EVENT.values())))

    class Slot(deque):  # type: ignore[type-arg]
        """A ring whose append drops the last reference to a finalizer: runs inside ``_commit``'s critical section."""

        def append(self, item: Any) -> None:
            Finalized()
            super().append(item)

    journal._events = Slot()  # pyright: ignore[reportPrivateUsage]
    assert offer(layout, tuple(EVENT.values())) is True
    assert nested == [False, False]
    status = journal.status()
    assert status["dropped"] == {"reentrant": 2}
    assert status["recorded"] == {"sql": 1}
    assert status["retainedEvents"] == 1
    assert journal.offer({"source": "log", "level": "INFO"}) is True  # nothing is left marked busy or appending
