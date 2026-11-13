"""The ``sql`` journal event's overhead budget: what offering it adds to a recorded statement (3 to 9 µs measured).

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

sa = pytest.importorskip("sqlalchemy")

from tests.overhead import check_budget, paired  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo  # noqa: E402
from sharpit.engine.capture.journal import RuntimeJournal  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

# first number, for the owner: measured 2026-11-12 over five paired runs, -n 0: 7.4 to 12.3 µs; round 2: 3.4 to 8.8 µs
BUDGET_NS = 25_000
ROUNDS, PER_ROUND = 45, 200
FULL_RING = 64  # a ring that is full: every offered statement evicts one, and the evicted event names a request


@pytest.fixture
def handle() -> Iterator[SharpitHandle]:
    sqla.detach_all()
    installed = install(FastAPI(), enabled="ON", show_banner=False, engines=[sa.create_engine("sqlite://")])
    yield installed
    installed.uninstall_capture()


def test_sql_journal_event_overhead_budget(handle: SharpitHandle):
    capture = handle.context.capture
    journal = capture.journal
    assert journal is not None
    statement = sa.text("select * from (select 1 as n) where n = :n")

    def run(conn: object) -> int:
        started = time.perf_counter_ns()
        for i in range(PER_ROUND):
            conn.execute(statement, {"n": i})  # type: ignore[attr-defined]
        return (time.perf_counter_ns() - started) // PER_ROUND

    with handle.context.engines[0].connect() as conn:  # type: ignore[attr-defined]
        run(conn)  # warm the statement cache and the normaliser cache

        def on() -> int:
            capture.journal = journal
            return run(conn)

        def off() -> int:
            capture.journal = None
            return run(conn)

        try:
            result = paired(off, on, ROUNDS)
        finally:
            capture.journal = journal
    assert len(journal.records("sql")) > 0
    check_budget("SQL journal event per statement", result, BUDGET_NS, "µs", 1000)


def test_sql_journal_event_overhead_budget_on_a_full_ring(handle: SharpitHandle):
    """The same budget when every offer evicts an event of a request (the loss-horizon path of ``_append``)."""
    capture = handle.context.capture
    assert capture.journal is not None
    full = RuntimeJournal(max_events=FULL_RING, sources=("sql",))
    statement = sa.text("select * from (select 1 as n) where n = :n")
    token = REQUEST.set(RequestInfo("r-full", handle.context.context_id, "GET", "/x", None, 0, None))

    def run(conn: object) -> int:
        started = time.perf_counter_ns()
        for i in range(PER_ROUND):
            conn.execute(statement, {"n": i})  # type: ignore[attr-defined]
        return (time.perf_counter_ns() - started) // PER_ROUND

    try:
        with handle.context.engines[0].connect() as conn:  # type: ignore[attr-defined]
            capture.journal = full
            run(conn)  # fills the ring and warms the caches

            def on() -> int:
                capture.journal = full
                return run(conn)

            def off() -> int:
                capture.journal = None
                return run(conn)

            result = paired(off, on, ROUNDS)
    finally:
        REQUEST.reset(token)
    assert full.status()["evictedEvents"] > 0
    assert getattr(full, "_loss_horizon", 0) is not None  # the evicted events named a request (the base has no horizon)
    check_budget("SQL journal event per statement, full ring", result, BUDGET_NS, "µs", 1000)
