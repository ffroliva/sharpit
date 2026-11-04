"""What one begin plus commit does, as counts: the overhead budget's wall clock cannot pin these on a shared runner."""

from __future__ import annotations

import weakref
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.capture import transactions  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

PAIRS = 50
INFO_READS_PER_PAIR = 3  # tx_begin's settle and _begin, then tx_commit


@pytest.fixture
def handle() -> Iterator[tuple[SharpitHandle, Any]]:
    engine = sa.create_engine("sqlite://")
    installed = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    yield installed, engine
    installed.uninstall_capture()
    engine.dispose()


def _pairs(engine: Any) -> None:
    with engine.connect() as connection:
        for _ in range(PAIRS):
            with connection.begin():
                pass


def _captured(installed: SharpitHandle) -> int:
    recorder = installed.context.capture.transactions
    assert isinstance(recorder, transactions.TransactionRecorder)
    return recorder.report([])["totalCaptured"]


def test_a_transaction_does_not_iterate_the_context_table(
    handle: tuple[SharpitHandle, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    installed, engine = handle
    iterations: list[object] = []
    values = weakref.WeakValueDictionary.values

    def counted(table: weakref.WeakValueDictionary[Any, Any]) -> Any:
        if table is transactions._contexts:  # pyright: ignore[reportPrivateUsage]
            iterations.append(table)
        return values(table)

    monkeypatch.setattr(weakref.WeakValueDictionary, "values", counted)
    _pairs(engine)
    assert _captured(installed) == PAIRS, "the listeners must have run for the count to mean anything"
    assert len(iterations) == 0, "values() builds a generator and an iteration guard on every begin"


def test_a_pair_reads_the_connection_info_at_most_three_times(
    handle: tuple[SharpitHandle, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    installed, engine = handle
    reads: list[None] = []
    info = sa.engine.Connection.info

    def counted(connection: Any) -> Any:
        reads.append(None)
        return info.fget(connection)

    monkeypatch.setattr(sa.engine.Connection, "info", property(counted))
    _pairs(engine)
    assert _captured(installed) == PAIRS, "the listeners must have run for the count to mean anything"
    assert len(reads) <= INFO_READS_PER_PAIR * PAIRS, f"{len(reads) / PAIRS} reads of conn.info per pair"
