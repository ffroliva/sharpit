"""W5a P-transaction: one ``transaction`` journal event per completed database transaction (BootUI ``TransactionPayload``).

Metadata only: no SQL text, no parameter, no connection URL.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")
pytest.importorskip("sqlalchemy.orm")
import sqlalchemy.orm  # noqa: E402,F401  (sa.orm)

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal  # noqa: E402
from sharpit.engine.sqla import transactions  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

LITERAL_CANARY = "zq-literal-canary-81"
PARAMETER_CANARY = "zq-parameter-canary-42"
SELECT = f"select 1 where 'x' = '{LITERAL_CANARY}' or :n = :n"
FIELDS = {
    "source", "epochMillis", "durationNanos", "traceId", "requestId", "thread",
    "method", "rolledBack", "nested", "savepoint", "startNanos", "readOnly", "isolation", "rollbackOnly",
    "failureClass", "ormStatements", "ormFlushes", "ormDirtyEntities", "completion",
}  # fmt: skip


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


def _install(sources: tuple[str, ...] = ("transaction",), url: str = "sqlite://", **options: Any) -> Any:
    engine = sa.create_engine(url)
    handle = install(
        FastAPI(),
        enabled="ON",
        show_banner=False,
        config_scan=False,
        engines=[engine],
        runtime_journal_sources=sources,
        **options,
    )
    return handle, engine


def _records(handle: Any) -> tuple[dict[str, Any], ...]:
    journal = handle.context.capture.journal
    assert journal is not None
    return tuple(journal.records("transaction"))  # type: ignore[arg-type]


def _read(conn: Any) -> None:
    conn.execute(sa.text(SELECT), {"n": PARAMETER_CANARY})


# ported: RecorderPublishingTests.transactionsPublishTheirMethodRollbackAndTheRequestTheyBeganIn
def test_transaction_journal_event_offered_once_per_commit_with_bootui_fields():
    handle, engine = _install()
    with engine.begin() as conn:
        _read(conn)
    records = _records(handle)
    assert len(records) == 1
    record = records[0]
    assert set(record) == FIELDS
    assert record["source"] == "transaction"
    assert record["rolledBack"] is False
    assert record["nested"] is False
    assert record["savepoint"] is False
    assert record["completion"] == "COMMIT"
    assert record["rollbackOnly"] is False
    assert record["failureClass"] is None
    assert record["ormStatements"] == -1
    assert record["durationNanos"] >= 0
    assert record["startNanos"] > 0


# ported: TransactionRecorderTests.recordsARolledBackTransactionWithErrorMessage
def test_transaction_journal_rollback_sets_rolled_back():
    handle, engine = _install()
    with engine.connect() as conn:
        _read(conn)
        conn.rollback()
    records = _records(handle)
    assert len(records) == 1
    assert records[0]["rolledBack"] is True
    assert records[0]["completion"] == "ROLLBACK"


def test_transaction_journal_exception_inside_begin_is_a_rollback():
    handle, engine = _install()
    with pytest.raises(RuntimeError), engine.begin() as conn:
        _read(conn)
        raise RuntimeError
    assert [r["rolledBack"] for r in _records(handle)] == [True]


def test_transaction_journal_close_without_commit_is_not_a_rollback_decision():
    handle, engine = _install()
    with engine.connect() as conn:  # a read-only request: SQLAlchemy rolls the open transaction back on close
        _read(conn)
    records = _records(handle)
    assert len(records) == 1
    assert records[0]["rolledBack"] is False
    assert records[0]["completion"] == "CLOSE"


def test_transaction_journal_savepoint_is_nested():
    handle, engine = _install()
    with engine.begin() as conn:
        with conn.begin_nested():
            _read(conn)
        savepoint = conn.begin_nested()
        savepoint.rollback()
    records = _records(handle)
    assert [(r["savepoint"], r["nested"], r["rolledBack"]) for r in records] == [
        (True, True, False),
        (True, True, True),
        (False, False, False),
    ]


# ported: TransactionRecorderTests.tracksParentChildNestingOnTheSameThread
def test_transaction_journal_transaction_begun_inside_another_is_nested():
    handle, engine = _install(url="sqlite://")
    with engine.begin() as outer:
        _read(outer)
        with engine.begin() as inner:
            _read(inner)
    assert [(r["nested"], r["savepoint"]) for r in _records(handle)] == [(True, False), (False, False)]


def test_transaction_journal_sequential_transactions_are_not_nested():
    handle, engine = _install()
    for _ in range(2):
        with engine.begin() as conn:
            _read(conn)
    assert [r["nested"] for r in _records(handle)] == [False, False]


def test_transaction_journal_engine_begin_and_session_and_async_each_offer_once():
    handle, engine = _install()
    with engine.begin() as conn:  # engine.begin()
        _read(conn)
    with engine.connect() as conn:  # autobegin then commit
        _read(conn)
        conn.commit()
    with sa.orm.Session(engine) as session:  # a Session
        session.execute(sa.text(SELECT), {"n": 1})
        session.commit()
    with sa.orm.Session(engine) as session:  # a Session that rolls back
        session.execute(sa.text(SELECT), {"n": 1})
        session.rollback()
    assert [r["completion"] for r in _records(handle)] == ["COMMIT", "COMMIT", "COMMIT", "ROLLBACK"]

    async def run() -> None:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        async_engine = create_async_engine("sqlite+aiosqlite://")
        async with AsyncSession(async_engine) as session:
            await session.execute(sa.text(SELECT), {"n": 1})
            await session.commit()
        async with async_engine.begin() as conn:
            await conn.execute(sa.text(SELECT), {"n": 1})
        await async_engine.dispose()

    before = len(_records(handle))
    asyncio.run(run())
    assert len(_records(handle)) - before == 2


def test_transaction_journal_not_offered_for_sharpit_internal_work():
    handle, engine = _install()
    with internal(), engine.begin() as conn:
        _read(conn)
    assert _records(handle) == ()
    with engine.begin() as conn:  # the control: the same work outside sharpit's own is offered
        _read(conn)
    assert len(_records(handle)) == 1


def test_transaction_journal_not_offered_when_source_disabled():
    handle, engine = _install(sources=("http",))
    with engine.begin() as conn:
        _read(conn)
    assert _records(handle) == ()


def test_transaction_journal_carries_the_request_id_of_this_install_only():
    ours, engine = _install()
    theirs, _ = _install()
    token = REQUEST.set(RequestInfo("r-ours", ours.context.context_id, "GET", "/x", None, 0, None))
    try:
        with engine.begin() as conn:
            _read(conn)
    finally:
        REQUEST.reset(token)
    token = REQUEST.set(RequestInfo("r-theirs", theirs.context.context_id, "GET", "/x", None, 0, None))
    try:
        with engine.begin() as conn:
            _read(conn)
    finally:
        REQUEST.reset(token)
    assert [r["requestId"] for r in _records(ours)] == ["r-ours"]
    assert "r-theirs" not in json.dumps(_records(ours))


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
def test_transaction_journal_carries_no_sql_text_parameter_or_url(exposure: str):
    handle, engine = _install(expose_values=exposure, sql_trace_capture_parameters=True)
    with engine.begin() as conn:
        _read(conn)
    records = _records(handle)
    assert len(records) == 1
    dumped = json.dumps(records)
    assert LITERAL_CANARY not in dumped
    assert PARAMETER_CANARY not in dumped
    assert "sqlite" not in dumped
    assert "select" not in dumped.lower()


def test_transaction_journal_failure_never_breaks_the_transaction(monkeypatch: pytest.MonkeyPatch):
    handle, engine = _install()
    journal = handle.context.capture.journal
    assert journal is not None

    def boom(*_: object, **__: object) -> bool:
        raise RuntimeError("journal down")

    monkeypatch.setattr(journal, "offer_flat", boom)
    with engine.begin() as conn:
        conn.execute(sa.text("create table t (a integer)"))
        conn.execute(sa.text("insert into t values (1)"))
    monkeypatch.undo()
    with engine.connect() as conn:
        assert conn.execute(sa.text("select count(*) from t")).scalar_one() == 1
    assert len(_records(handle)) == 1  # the offer works again once the journal does


def test_transaction_journal_event_built_inside_the_guard(monkeypatch: pytest.MonkeyPatch):
    handle, engine = _install()

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("cannot build")

    monkeypatch.setattr(transactions, "_event", boom)
    with engine.begin() as conn:
        _read(conn)
    monkeypatch.undo()
    with engine.begin() as conn:
        _read(conn)
    assert len(_records(handle)) == 1


def test_transaction_journal_isolation_level_is_carried_when_set():
    handle, engine = _install()
    with engine.execution_options(isolation_level="SERIALIZABLE").begin() as conn:
        _read(conn)
    assert [r["isolation"] for r in _records(handle)] == ["SERIALIZABLE"]
