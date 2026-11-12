"""The ``sql`` journal event's overhead budget: what offering it adds to a recorded statement (7 to 12 µs measured).

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
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

# first number, for the owner: measured 2026-11-12 over five paired runs, -n 0: 7.4 to 12.3 µs
BUDGET_NS = 25_000
ROUNDS, PER_ROUND = 45, 200


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
