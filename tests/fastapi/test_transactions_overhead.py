"""Transactions listener overhead budget: begin plus commit stays within 30 µs per pair."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from tests.overhead import check_budget, paired  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.capture.transactions import (  # noqa: E402
    CONNECTION_CALLBACKS,
    TransactionRecorder,
    tx_checkin,
)
from sharpit.engine.sources import dispatch  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

BUDGET_NS = 30_000
ROUNDS, PER_ROUND = 45, 200


@contextmanager
def _listeners_detached() -> Iterator[None]:
    """Remove the production class listeners for the "off" side, leaving every attachment and routing entry intact."""
    for event, callback in CONNECTION_CALLBACKS.items():
        sa.event.remove(sa.engine.Engine, event, callback)
    sa.event.remove(sa.pool.Pool, "checkin", tx_checkin)
    try:
        yield
    finally:
        for event, callback in CONNECTION_CALLBACKS.items():
            sa.event.listen(sa.engine.Engine, event, callback)
        sa.event.listen(sa.pool.Pool, "checkin", tx_checkin)


@pytest.fixture
def handle() -> Iterator[tuple[SharpitHandle, Any, Any]]:
    engine = sa.create_engine("sqlite://")
    installed = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    recorder = installed.context.capture.transactions
    assert isinstance(recorder, TransactionRecorder)
    yield installed, engine, recorder
    installed.uninstall_capture()
    engine.dispose()


def test_transaction_overhead_budget(handle: tuple[SharpitHandle, Any, Any]) -> None:
    installed, engine, recorder = handle
    with engine.connect() as connection:
        with connection.begin():  # warm SQLAlchemy's event path
            pass

        def round_transactions() -> int:
            started = time.perf_counter_ns()
            for _ in range(PER_ROUND):
                with connection.begin():
                    pass
            return (time.perf_counter_ns() - started) // PER_ROUND

        def detached_round() -> int:
            with _listeners_detached():
                return round_transactions()

        result = paired(detached_round, round_transactions, ROUNDS)
    assert recorder.report([])["totalCaptured"] == 1 + ROUNDS * PER_ROUND
    check_budget("SQLAlchemy transaction listener pair", result, BUDGET_NS, "µs", 1000)


def test_overhead_measures_production_contexts_path(
    handle: tuple[SharpitHandle, Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _installed, engine, recorder = handle
    with _listeners_detached():
        pass
    fallback_calls: list[object] = []
    fallback = dispatch._targets
    monkeypatch.setattr(dispatch, "_targets", lambda e: fallback_calls.append(e) or fallback(e))
    with engine.connect() as connection, connection.begin():
        pass
    assert recorder.report([])["totalCaptured"] == 1, "the attached side must record the transaction"
    assert fallback_calls == [], "the attached side must route through the panel's own contexts, not SQL Trace's"
