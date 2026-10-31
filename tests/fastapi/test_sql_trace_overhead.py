"""SQL Trace overhead budget (spec §7.3): the listeners add at most 50 µs per statement.

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

BUDGET_NS = 50_000
ROUNDS, PER_ROUND = 45, 200


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
