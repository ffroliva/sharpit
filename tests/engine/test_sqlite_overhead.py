"""sqlite3 source overhead budget (spec 0.3.0 §9 A8): tracing adds at most 50 µs per statement.

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator

import pytest
from tests.overhead import check_budget, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.sources import sqlite
from sharpit.fastapi.adapter import SharpitHandle

REAL_CONNECT = sqlite3.connect
BUDGET_NS = 50_000
ROUNDS, PER_ROUND = 45, 200


@pytest.fixture
def handle() -> Iterator[SharpitHandle]:
    sqla.detach_all()  # only this context records
    installed = install(FastAPI(), enabled="ON", show_banner=False)
    yield installed
    installed.uninstall_capture()
    sqlite3.connect = REAL_CONNECT


def _round(conn: sqlite3.Connection) -> int:
    started = time.perf_counter_ns()
    for i in range(PER_ROUND):
        conn.execute("select * from (select 1 as n) where n = ?", (i,))
    return (time.perf_counter_ns() - started) // PER_ROUND


def test_sqlite_statement_overhead_budget(handle: SharpitHandle):
    """A8: the same statement on a stock connection and on a traced one, recording into the console."""
    assert sqlite.is_attached() is True
    traced = sqlite3.connect(":memory:")
    stock = REAL_CONNECT(":memory:")
    _round(traced)  # warm the normaliser cache
    _round(stock)

    result = paired(lambda: _round(stock), lambda: _round(traced), ROUNDS)
    recorder = handle.context.capture.sql_trace
    assert recorder is not None
    assert recorder.report([])["totalCaptured"] == (ROUNDS + 1) * PER_ROUND
    check_budget("sqlite3 source per statement", result, BUDGET_NS, "µs", 1000)
    traced.close()
    stock.close()
