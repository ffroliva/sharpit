"""SQL Trace overhead budget (spec §7.3): the listeners add at most 50 µs per statement.

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Iterator

import pytest

sa = pytest.importorskip("sqlalchemy")

from tests.overhead import check_budget, paired  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo  # noqa: E402
from sharpit.engine.sqltext import Dialect  # noqa: E402
from sharpit.engine.sqltext.lexer import read_all  # noqa: E402
from sharpit.engine.sqltext.rules import MYSQL_84, READINGS  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

BUDGET_NS = 50_000
FULL_RING = 64  # a ring that is full: every recorded statement evicts one, and the evicted event names a request
ROUNDS, PER_ROUND = 45, 200
MISS_BUDGET_NS = 300_000  # a distinct statement: the scan and the masker's passes; overhead-budgets.md has the numbers
MISS_ROUNDS, MISS_PER_ROUND = 20, 50  # 1,000 distinct statements a side
FAMILY_ROUNDS, FAMILY_PER_ROUND = 20, 300
# a distinct statement of 138 KB: nothing past the scan's 20,000 characters is shown, so the cost stays the window's
LARGE_MISS_BUDGET_NS = 40_000_000  # first number, for the owner: overhead-budgets.md has the measurements
LARGE_ROUNDS, LARGE_PER_ROUND = 12, 2
LARGE_VALUES = ",".join(f"'k{i}=v{i}'" for i in range(10_000))


@pytest.fixture
def handle() -> Iterator[SharpitHandle]:
    sqla.detach_all()  # only this context's listeners are measured
    engine = sa.create_engine("sqlite://")
    installed = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    yield installed
    installed.uninstall_capture()


def _round(conn: object, statement: object) -> int:
    started = time.perf_counter_ns()
    for i in range(PER_ROUND):
        conn.execute(statement, {"n": i})  # type: ignore[attr-defined]
    return (time.perf_counter_ns() - started) // PER_ROUND


def test_statement_overhead_budget(handle: SharpitHandle):
    engine = handle.context.engines[0]
    statement = sa.text("select * from (select 1 as n) where n = :n")
    with engine.connect() as conn:  # type: ignore[attr-defined]
        _round(conn, statement)  # warm the statement cache and the normaliser cache
        sqla.remove(handle.context)

        def on() -> int:
            sqla.add(handle.context, statements=True, discovery=True)
            r = _round(conn, statement)
            sqla.remove(handle.context)
            return r

        def off() -> int:
            return _round(conn, statement)

        result = paired(off, on, ROUNDS)
    recorder = handle.context.capture.sql_trace
    captured = (ROUNDS + 1) * PER_ROUND  # with the warm-up
    assert recorder is not None
    assert recorder.report([])["totalCaptured"] == captured
    check_budget("SQL listener per statement", result, BUDGET_NS, "µs", 1000)


def test_statement_overhead_budget_on_a_full_ring(handle: SharpitHandle):
    """The same 50 µs when the journal's ring is full, as a long-running app's is: every statement evicts an event of
    a request, and the loss horizon moves (the cost an empty-ring run never pays)."""
    engine = handle.context.engines[0]
    journal = handle.context.capture.journal
    assert journal is not None
    journal.max_events = FULL_RING
    statement = sa.text("select * from (select 1 as n) where n = :n")
    token = REQUEST.set(RequestInfo("r-full", handle.context.context_id, "GET", "/x", None, 0, None))
    try:
        with engine.connect() as conn:  # type: ignore[attr-defined]
            _round(conn, statement)  # warm the statement cache and the normaliser cache
            sqla.remove(handle.context)

            def on() -> int:
                sqla.add(handle.context, statements=True, discovery=True)
                r = _round(conn, statement)
                sqla.remove(handle.context)
                return r

            def off() -> int:
                return _round(conn, statement)

            on()  # fills the ring
            result = paired(off, on, ROUNDS)
    finally:
        REQUEST.reset(token)
    assert journal.status()["evictedEvents"] > 0
    check_budget("SQL listener per statement, full ring", result, BUDGET_NS, "µs", 1000)


def test_recorder_cache_miss_within_budget(handle: SharpitHandle):
    """The hit budget reuses one statement, so it cannot see the scan and the masker: here no statement repeats."""
    engine = handle.context.engines[0]
    serial = itertools.count()

    def miss_round(conn: object) -> int:
        statements = [f"select * from (select 1 as n{next(serial):06d}) where 0" for _ in range(MISS_PER_ROUND)]
        started = time.perf_counter_ns()
        for statement in statements:
            conn.exec_driver_sql(statement)  # type: ignore[attr-defined]
        return (time.perf_counter_ns() - started) // MISS_PER_ROUND

    with engine.connect() as conn:  # type: ignore[attr-defined]
        sqla.remove(handle.context)

        def on() -> int:
            sqla.add(handle.context, statements=True, discovery=True)
            r = miss_round(conn)
            sqla.remove(handle.context)
            return r

        def off() -> int:
            return miss_round(conn)

        result = paired(off, on, MISS_ROUNDS)
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    assert recorder.report([])["totalCaptured"] == MISS_ROUNDS * MISS_PER_ROUND
    check_budget("SQL listener per distinct statement", result, MISS_BUDGET_NS, "µs", 1000)


def test_mysql_family_read_budget():
    """Ordinary ORM identifiers skip the second reading; cap family time at 1.2x one reading."""
    statements = [f"SELECT `column_{i:06d}` FROM `table` WHERE `id` = 1" for i in range(FAMILY_PER_ROUND)]

    def measure(rule_sets: tuple) -> int:
        started = time.perf_counter_ns()
        for sql in statements:
            read_all(sql, rule_sets)
        return (time.perf_counter_ns() - started) // FAMILY_PER_ROUND

    result = paired(lambda: measure((MYSQL_84,)), lambda: measure(READINGS[Dialect.MYSQL_FAMILY]), FAMILY_ROUNDS)
    check_budget("MySQL family second reading", result, min(result.off) // 5, "ns", 1)


def test_recorder_cache_miss_on_a_large_statement_within_budget(handle: SharpitHandle):
    """Council M3 (Task 35): the masker read the whole raw statement, past the scan window nothing of it is shown."""
    engine = handle.context.engines[0]
    serial = itertools.count()

    def large_round(conn: object) -> int:
        statements = [
            f"select * from (select 1 as n{next(serial):06d}) where 0 and 'k' in ({LARGE_VALUES})"
            for _ in range(LARGE_PER_ROUND)
        ]
        started = time.perf_counter_ns()
        for statement in statements:
            conn.exec_driver_sql(statement)  # type: ignore[attr-defined]
        return (time.perf_counter_ns() - started) // LARGE_PER_ROUND

    with engine.connect() as conn:  # type: ignore[attr-defined]
        sqla.remove(handle.context)

        def on() -> int:
            sqla.add(handle.context, statements=True, discovery=True)
            r = large_round(conn)
            sqla.remove(handle.context)
            return r

        def off() -> int:
            return large_round(conn)

        result = paired(off, on, LARGE_ROUNDS)
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    assert recorder.report([])["totalCaptured"] == LARGE_ROUNDS * LARGE_PER_ROUND
    check_budget("SQL listener per distinct 138 KB statement", result, LARGE_MISS_BUDGET_NS, "ms", 1_000_000)


def test_suspended_statement_overhead_budget(handle: SharpitHandle):
    """Plan scenario 2: with the sqla-listeners hook suspended (low-footprint), a statement stays in budget."""
    engine = handle.context.engines[0]
    stock = sa.create_engine("sqlite://")  # never held by any context
    statement = sa.text("select * from (select 1 as n) where n = :n")
    hook = next(h for h in handle.context.capture.hooks.hooks() if h.name == "sqla-listeners")
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    with engine.connect() as conn, stock.connect() as stock_conn:  # type: ignore[attr-defined]
        _round(conn, statement)  # warm the statement cache and the normaliser cache
        _round(stock_conn, statement)
        captured = recorder.report([])["totalCaptured"]
        hook.suspend()
        result = paired(lambda: _round(stock_conn, statement), lambda: _round(conn, statement), ROUNDS)
    stock.dispose()
    assert recorder.report([])["totalCaptured"] == captured, "the suspended path recorded"
    check_budget("SQL listener per statement, suspended", result, BUDGET_NS, "µs", 1000)
