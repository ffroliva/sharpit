"""Transactions listener overhead budget: begin plus commit stays within 30 µs per pair."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from tests.overhead import check_budget, paired  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.capture.transactions import (  # noqa: E402
    TransactionRecorder,
    attach,
    tx_begin,
    tx_commit,
    tx_release_savepoint,
    tx_rollback,
    tx_rollback_savepoint,
    tx_savepoint,
)
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

BUDGET_NS = 30_000
ROUNDS, PER_ROUND = 45, 200


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
            remover = installed.context.capture.teardowns.pop()
            remover()
            callbacks = {
                "begin": tx_begin,
                "commit": tx_commit,
                "rollback": tx_rollback,
                "savepoint": tx_savepoint,
                "rollback_savepoint": tx_rollback_savepoint,
                "release_savepoint": tx_release_savepoint,
            }
            for event, callback in callbacks.items():
                if sa.event.contains(sa.engine.Engine, event, callback):
                    sa.event.remove(sa.engine.Engine, event, callback)
            try:
                return round_transactions()
            finally:
                reattach = attach()
                assert reattach is not None
                for event, callback in callbacks.items():
                    if not sa.event.contains(sa.engine.Engine, event, callback):
                        sa.event.listen(sa.engine.Engine, event, callback)
                installed.context.capture.teardowns.append(reattach)

        result = paired(detached_round, round_transactions, ROUNDS)
    assert recorder.report([])["totalCaptured"] == 1 + ROUNDS * PER_ROUND
    check_budget("SQLAlchemy transaction listener pair", result, BUDGET_NS, "µs", 1000)
