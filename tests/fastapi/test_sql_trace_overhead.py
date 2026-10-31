"""SQL Trace overhead budget (spec §7.3): the listeners add at most 50 µs per statement.

The fastest round of each side is compared: contention from other xdist workers only ever slows a round down.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

BUDGET_NS = 50_000
ROUNDS, PER_ROUND, ATTEMPTS = 15, 200, 3


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


def _overhead(handle: SharpitHandle, conn: object, statement: object) -> int:
    traced: list[int] = []
    plain: list[int] = []
    for _ in range(ROUNDS):  # interleaved, so machine noise hits both sides alike
        sqla.add(handle.context, statements=True, discovery=True)
        traced.append(_round(conn, statement))
        sqla.remove(handle.context)
        plain.append(_round(conn, statement))
    return min(traced) - min(plain)


def test_statement_overhead_budget(handle: SharpitHandle):
    engine = handle.context.engines[0]
    statement = sa.text("select * from (select 1 as n) where n = :n")
    with engine.connect() as conn:  # type: ignore[attr-defined]
        _round(conn, statement)  # warm the statement cache and the normaliser cache
        overhead = min(_overhead(handle, conn, statement) for _ in range(ATTEMPTS))
    recorder = handle.context.capture.sql_trace
    captured = (ROUNDS * ATTEMPTS + 1) * PER_ROUND  # with the warm-up
    assert recorder is not None
    assert recorder.report([])["totalCaptured"] == captured
    assert overhead <= BUDGET_NS, f"{overhead / 1000:.1f} µs per statement (budget {BUDGET_NS / 1000:.0f} µs)"
