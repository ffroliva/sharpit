"""# derived: a collection on the recording thread can run a finalizer that runs SQL: the recorder must not hang it."""

from __future__ import annotations

import gc
import threading
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Any

import pytest

from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

WAIT_SECONDS = 2.0


def _recorder(**options: Any) -> SqlTraceRecorder:
    return SqlTraceRecorder(Masker(Exposure.MASKED, True), **options)


def _record(recorder: SqlTraceRecorder, sql: str = "select 1") -> None:
    recorder.record(sql, duration_ns=1_000_000, thread="main", connection_id=None, dialect=Dialect.SQLITE)


def _collect(action: Callable[[], None]) -> None:
    """A real collection whose finalizer runs ``action``, as one between two bytecodes does."""

    class Finalized:
        def __del__(self) -> None:
            action()

    garbage = Finalized()
    garbage.cycle = garbage  # pyright: ignore[reportAttributeAccessIssue]
    del garbage
    gc.collect()


def _finishes(action: Callable[[], object]) -> bool:
    finished = threading.Event()

    def run() -> None:
        action()
        finished.set()

    threading.Thread(target=run, daemon=True).start()
    return finished.wait(WAIT_SECONDS)


def test_a_finalizer_that_runs_sql_during_a_record_does_not_deadlock():
    recorder = _recorder()

    class Collected(deque[Any]):
        collecting = True

        def append(self, item: Any) -> None:
            super().append(item)
            if self.collecting:
                self.collecting = False
                _collect(lambda: _record(recorder, "select 2"))

    recorder._entries = Collected(maxlen=recorder.max_entries)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    assert _finishes(lambda: _record(recorder))


def test_both_statements_of_a_reentered_record_are_counted():
    recorder = _recorder()

    class Collected(deque[Any]):
        collecting = True

        def append(self, item: Any) -> None:
            super().append(item)
            if self.collecting:
                self.collecting = False
                _collect(lambda: _record(recorder, "select 2"))

    recorder._entries = Collected(maxlen=recorder.max_entries)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    assert _finishes(lambda: _record(recorder))
    assert recorder.totals().statements == 2


def test_a_finalizer_that_clears_mid_record_loses_no_aggregate():
    """``move_to_end`` after a ``clear`` from the same thread: the key has gone, and that must not fail the record."""
    recorder = _recorder()
    _record(recorder)

    class Collected(OrderedDict[str, Any]):
        collecting = True

        def get(self, key: str, default: Any = None) -> Any:
            found = super().get(key, default)
            if self.collecting:
                self.collecting = False
                _collect(self.clear)
            return found

    recorder._aggregates = Collected(recorder._aggregates)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    assert _finishes(lambda: _record(recorder))
    assert recorder.aggregate_count == 1


@pytest.mark.parametrize("read", [SqlTraceRecorder.totals, SqlTraceRecorder.rows], ids=["totals", "rows"])
def test_a_read_waits_for_no_writer(read: Callable[[SqlTraceRecorder], object]):
    recorder = _recorder()
    _record(recorder)

    with recorder._lock:  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert _finishes(lambda: read(recorder))


def test_a_finalizer_that_runs_sql_during_a_report_does_not_stop_it():
    """The finalizer runs while ``report`` copies a group, so a new group lands mid-loop over the groups."""
    recorder = _recorder()
    _record(recorder, "select 1 from a")
    _record(recorder, "select 1 from b")  # a second group: the iterator checks a change only before a next item

    class Collecting:
        def __init__(self, aggregate: Any) -> None:
            self.aggregate, self.collecting = aggregate, True

        def __getattr__(self, name: str) -> Any:
            if self.collecting:
                self.collecting = False
                _collect(lambda: _record(recorder, "select 1 from c"))
            return getattr(self.aggregate, name)

    groups = recorder._aggregates  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    first = next(iter(groups))
    groups[first] = Collecting(groups[first])  # pyright: ignore[reportArgumentType]
    errors: list[RuntimeError] = []

    def report() -> None:
        try:
            recorder.report([])
        except RuntimeError as error:
            errors.append(error)

    assert _finishes(report)
    assert errors == []


def test_a_report_waits_for_a_writer_so_it_reads_one_view():
    """A writer holds the lock between the ring and the groups: a report read then would see a row with no group."""
    recorder = _recorder()
    _record(recorder)
    finished = threading.Event()

    with recorder._lock:  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        threading.Thread(target=lambda: (recorder.report([]), finished.set()), daemon=True).start()
        assert not finished.wait(0.5), "report read the recorder while a writer held it"


def test_the_slowest_select_is_read_whole():
    """``totals`` reads no lock, so the slowest select's time and text are published as one value."""
    recorder = _recorder()
    recorder.record("select 1", duration_ns=5_000_000, thread="main", connection_id=None, dialect=Dialect.SQLITE)

    totals = recorder.totals()

    assert (totals.max_millis, totals.max_sql) == (5, "select ?")


def test_clear_resets_the_slowest_select():
    recorder = _recorder()
    recorder.record("select 1", duration_ns=5_000_000, thread="main", connection_id=None, dialect=Dialect.SQLITE)
    recorder.clear()

    totals = recorder.totals()

    assert (totals.max_millis, totals.max_sql) == (0, None)
