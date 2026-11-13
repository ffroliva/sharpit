"""The ``connection`` journal event's overhead budget: what following and offering one released connection adds.

The event fires once per connection RELEASE, not per statement, so its budget is per release. Rounds alternate and the
first side swaps every round, through tests/overhead.py; how to read a failure: docs/development/overhead-budgets.md.
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

BUDGET_NS = 40_000  # first number, for the owner: set from the measurement in docs/development/overhead-budgets.md
ROUNDS, PER_ROUND = 45, 100


@pytest.fixture
def handle() -> Iterator[SharpitHandle]:
    sqla.detach_all()
    installed = install(
        FastAPI(),
        enabled="ON",
        show_banner=False,
        engines=[sa.create_engine("sqlite://")],
        runtime_journal_sources=("connection",),
    )
    yield installed
    installed.uninstall_capture()


def test_connection_journal_event_overhead_budget(handle: SharpitHandle):
    capture = handle.context.capture
    journal = capture.journal
    assert journal is not None
    engine = handle.context.engines[0]  # type: ignore[attr-defined]

    def run() -> int:
        started = time.perf_counter_ns()
        for _ in range(PER_ROUND):
            with engine.connect():
                pass
        return (time.perf_counter_ns() - started) // PER_ROUND

    run()  # warm the pool and the first-connect work

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
    assert len(journal.records("connection")) > 0
    check_budget("connection journal event per release", result, BUDGET_NS, "µs", 1000)
