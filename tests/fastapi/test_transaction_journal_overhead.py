"""The ``transaction`` journal event's overhead budget: what offering it adds to one begin, statement, commit.

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

BUDGET_NS = 60_000
ROUNDS, PER_ROUND = 45, 200


@pytest.fixture
def handle() -> Iterator[SharpitHandle]:
    sqla.detach_all()
    installed = install(FastAPI(), enabled="ON", show_banner=False, engines=[sa.create_engine("sqlite://")])
    yield installed
    installed.uninstall_capture()


def test_transaction_journal_event_overhead_budget(handle: SharpitHandle):
    capture = handle.context.capture
    journal = capture.journal
    assert journal is not None
    engine = handle.context.engines[0]
    statement = sa.text("select 1")

    def run() -> int:
        started = time.perf_counter_ns()
        for _ in range(PER_ROUND):
            with engine.begin() as conn:  # type: ignore[attr-defined]
                conn.execute(statement)
        return (time.perf_counter_ns() - started) // PER_ROUND

    run()  # warm the statement cache

    def on() -> int:
        capture.journal = journal
        return run()

    def off() -> int:
        capture.journal = None
        return run()

    try:
        result = paired(off, on, ROUNDS)
    finally:
        capture.journal = journal
    assert len(journal.records("transaction")) > 0
    check_budget("transaction journal event per transaction", result, BUDGET_NS, "µs", 1000)
