"""W5a P-transaction: one ``transaction`` journal event per completed transaction (BootUI ``TransactionPayload``).

The event is offered from the transactions panel's own recorder, as BootUI offers it from ``TransactionRecorder``'s
completion: one tracker, one call-site walk, one routing. Metadata only: no SQL text, no parameter, no connection URL.
"""

from __future__ import annotations

import asyncio
import contextlib
import dis
import gc
import json
import os
import re
import sqlite3
import time
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")
orm = pytest.importorskip("sqlalchemy.orm")

from fastapi.testclient import TestClient  # noqa: E402

import sharpit  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture import sqltrace, transactions  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, internal  # noqa: E402
from sharpit.engine.collectors.insights.service import insights_service  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

LITERAL_CANARY = "zq-literal-canary-81"
PARAMETER_CANARY = "zq-parameter-canary-42"
SELECT = f"select 1 where 'x' = '{LITERAL_CANARY}' or :n = :n"
FIELDS = {
    "source", "epochMillis", "durationNanos", "traceId", "requestId", "thread",
    "method", "rolledBack", "nested", "savepoint", "startNanos", "readOnly", "isolation", "rollbackOnly",
    "failureClass", "ormStatements", "ormFlushes", "ormDirtyEntities",
}  # fmt: skip  # BootUI's TransactionPayload and envelope only (owner, 2026-11-12: no ``completion``)


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


def _install(sources: tuple[str, ...] = ("transaction",), engine: Any = None, **options: Any) -> Any:
    engine = sa.create_engine("sqlite://") if engine is None else engine
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


def _file_engine(tmp_path: Path) -> Any:
    """A pooled file database: each ``connect()`` is its own DBAPI connection (``sqlite://`` shares one per thread)."""
    return sa.create_engine(f"sqlite:///{tmp_path / 'tx.db'}")


def _journal(handle: Any) -> Any:
    journal = handle.context.capture.journal
    assert journal is not None
    return journal


def _records(handle: Any) -> tuple[dict[str, Any], ...]:
    return tuple(_journal(handle).records("transaction"))


def _read(conn: Any) -> None:
    conn.execute(sa.text(SELECT), {"n": PARAMETER_CANARY})


def _write(conn: Any) -> None:
    """A write: what makes a rollback undo something (a write-free rollback is BootUI's read-only commit)."""
    conn.execute(sa.text("create table if not exists w (a integer)"))
    conn.execute(sa.text("insert into w values (1)"))


@contextlib.contextmanager
def _request(handle: Any, request_id: str) -> Generator[None]:
    token = REQUEST.set(RequestInfo(request_id, handle.context.context_id, "GET", "/x", None, 0, None))
    try:
        yield
    finally:
        REQUEST.reset(token)


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
    assert record["rollbackOnly"] is False
    assert record["failureClass"] is None
    assert record["ormStatements"] == -1
    assert record["durationNanos"] >= 0
    assert record["startNanos"] > 0


# ported: TransactionRecorderTests.recordsARolledBackTransactionWithErrorMessage
def test_transaction_journal_rollback_sets_rolled_back():
    handle, engine = _install()
    with engine.connect() as conn:
        _write(conn)
        conn.rollback()
    assert [r["rolledBack"] for r in _records(handle)] == [True]


def test_transaction_journal_rollback_of_a_read_only_transaction_is_not_rolled_back():
    """Rolling back a transaction that wrote nothing undoes nothing: BootUI's read-only transaction commits."""
    handle, engine = _install()
    with engine.connect() as conn:
        _read(conn)
        conn.rollback()
    assert [r["rolledBack"] for r in _records(handle)] == [False]


def test_transaction_journal_exception_inside_begin_is_a_rollback():
    handle, engine = _install()
    with pytest.raises(RuntimeError), engine.begin() as conn:
        _write(conn)
        raise RuntimeError
    assert [r["rolledBack"] for r in _records(handle)] == [True]


def test_transaction_journal_close_without_commit_after_a_write_is_rolled_back():
    """SQLAlchemy rolls an uncommitted transaction back on close: after a write, BootUI's rolledBack."""
    handle, engine = _install()
    with engine.connect() as conn:
        _write(conn)
    assert [r["rolledBack"] for r in _records(handle)] == [True]


def test_transaction_journal_read_only_session_close_is_not_rolled_back():
    """The FastAPI tutorial's ``get_db``: a Session that only reads is closed uncommitted, so SQLAlchemy rolls it
    back; BootUI's read-only transaction commits, so it is not a rolled-back transaction."""
    handle, engine = _install()
    session = orm.Session(engine)
    try:
        session.execute(sa.text(SELECT), {"n": 1})
    finally:
        session.close()
    assert [r["rolledBack"] for r in _records(handle)] == [False]


def test_transaction_journal_swallowed_integrity_error_then_session_close_is_rolled_back():
    handle, engine = _install()
    with engine.begin() as conn:
        conn.execute(sa.text("create table u (a integer primary key)"))
        conn.execute(sa.text("insert into u values (1)"))
    with orm.Session(engine) as session, contextlib.suppress(sa.exc.IntegrityError):
        session.execute(sa.text("insert into u values (1)"))  # the duplicate fails; the handler swallows it
    assert [r["rolledBack"] for r in _records(handle)] == [False, True]


def test_transaction_journal_autocommit_connection_offers_no_transaction():
    """Under AUTOCOMMIT each statement commits itself: no physical transaction, so nothing BootUI would record."""
    handle, engine = _install()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        _read(conn)
        conn.rollback()
    assert _records(handle) == ()
    with engine.connect() as conn:  # the control: the same work in a real transaction is offered
        _write(conn)
        conn.rollback()
    assert [r["rolledBack"] for r in _records(handle)] == [True]


class _FailingCommit:
    """A DBAPI connection whose commit takes 10 ms and then fails, as a deferred constraint does."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    def commit(self) -> None:
        time.sleep(0.01)
        raise RuntimeError("commit failed")


def test_transaction_journal_failed_dbapi_commit_is_not_a_commit():
    """The ``commit`` event fires before the DBAPI commit: the event waits for it, as the panel's row does."""
    engine = sa.create_engine("sqlite://", creator=lambda: _FailingCommit(sqlite3.connect(":memory:")))
    handle, _ = _install(engine=engine)
    with engine.connect() as conn:
        transaction = conn.begin()
        with pytest.raises(RuntimeError):
            transaction.commit()
    records = _records(handle)
    assert len(records) == 1
    assert records[0]["failureClass"] == "RuntimeError"
    assert records[0]["rolledBack"] is False
    assert records[0]["durationNanos"] >= 10_000_000, "the duration includes the DBAPI commit"


def test_transaction_journal_offered_with_sql_trace_disabled():
    handle, engine = _install(sql_trace_enabled=False)
    with engine.begin() as conn:
        _read(conn)
    assert len(_records(handle)) == 1


def test_transaction_journal_savepoint_is_nested():
    handle, engine = _install()
    with engine.begin() as conn:
        with conn.begin_nested():
            _read(conn)
        savepoint = conn.begin_nested()
        _write(conn)
        savepoint.rollback()
    records = _records(handle)
    assert [(r["savepoint"], r["nested"], r["rolledBack"]) for r in records] == [
        (True, True, False),
        (True, True, True),
        (False, False, False),
    ]


# ported: TransactionRecorderTests.tracksParentChildNestingOnTheSameThread
def test_transaction_journal_transaction_begun_inside_another_is_nested(tmp_path: Path):
    handle, engine = _install(engine=_file_engine(tmp_path))
    with engine.begin() as outer:
        _read(outer)
        with engine.begin() as inner:
            _read(inner)
    engine.dispose()
    assert [(r["nested"], r["savepoint"]) for r in _records(handle)] == [(True, False), (False, False)]


def test_transaction_journal_sequential_transactions_are_not_nested(tmp_path: Path):
    handle, engine = _install(engine=_file_engine(tmp_path))
    for _ in range(2):
        with engine.begin() as conn:
            _read(conn)
    engine.dispose()
    assert [r["nested"] for r in _records(handle)] == [False, False]


def test_transaction_journal_unclosed_connection_collected_does_not_nest_the_next(tmp_path: Path):
    handle, engine = _install(engine=_file_engine(tmp_path))
    abandoned = engine.connect()
    abandoned.begin()
    _read(abandoned)
    del abandoned  # never committed, rolled back or closed: no end event ever comes
    gc.collect()
    with engine.begin() as conn:
        _read(conn)
    engine.dispose()
    assert _records(handle)[-1]["nested"] is False


def test_transaction_journal_engine_begin_and_session_and_async_each_offer_once():
    handle, engine = _install()
    with engine.begin() as conn:  # engine.begin()
        _read(conn)
    with engine.connect() as conn:  # autobegin then commit
        _read(conn)
        conn.commit()
    with orm.Session(engine) as session:  # a Session
        session.execute(sa.text(SELECT), {"n": 1})
        session.commit()
    with orm.Session(engine) as session:  # a Session that rolls back a write
        session.execute(sa.text("create table if not exists w (a integer)"))
        session.rollback()
    assert [r["rolledBack"] for r in _records(handle)] == [False, False, False, True]

    async def run() -> None:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: PLC0415

        async_engine = create_async_engine("sqlite+aiosqlite://")
        handle.context.capture.engine_registry.add(async_engine)
        async with AsyncSession(async_engine) as session:
            await session.execute(sa.text(SELECT), {"n": 1})
            await session.commit()
        async with async_engine.begin() as conn:
            await conn.execute(sa.text(SELECT), {"n": 1})
        await async_engine.dispose()

    asyncio.run(run())
    assert len(_records(handle)) == 6


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
    enabled, enabled_engine = _install()  # the control: the same work with the source enabled is offered
    with enabled_engine.begin() as conn:
        _read(conn)
    assert len(_records(enabled)) == 1


def test_transaction_journal_source_disabled_is_counted_as_dropped():
    handle, engine = _install(sources=("http",))
    with engine.begin() as conn:
        _read(conn)
    assert _journal(handle).status()["dropped"].get("transaction") == 1


def test_transaction_journal_carries_the_request_id_of_this_install_only():
    ours, engine = _install()
    theirs, _ = _install()
    with _request(ours, "r-ours"), engine.begin() as conn:
        _read(conn)
    with _request(theirs, "r-theirs"), engine.begin() as conn:
        _read(conn)
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


def test_transaction_journal_event_size_is_what_the_flat_walk_charges(monkeypatch: pytest.MonkeyPatch):
    """The producer charges the event's size itself, as P-sql does: it must equal the journal's own walk."""
    from sharpit.engine.capture.journal import _flat  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]

    handle, engine = _install()
    journal = _journal(handle)
    offer = journal.offer_flat
    charged: list[tuple[int | None, int]] = []

    def spy(event: dict[str, Any], size: int | None = None) -> bool:
        if event.get("source") == "transaction":  # P-sql offers its statements through the same call
            charged.append((size, _flat(event)[1]))
        return offer(event, size)

    monkeypatch.setattr(journal, "offer_flat", spy)
    with engine.begin() as conn:
        _read(conn)
    with _request(handle, "r-sized"), engine.execution_options(isolation_level="SERIALIZABLE").connect() as conn:
        _read(conn)
        conn.rollback()
    assert len(charged) == 2
    assert [size for size, _ in charged] == [walked for _, walked in charged]


def test_transaction_event_copies_its_fixed_parts_instead_of_building_every_key():
    """r4: the 18-key event is a copy of one prebuilt dict with the per-transaction fields set, never a dict display
    rebuilt key by key on every commit (the listener budget)."""
    built = {instruction.opname for instruction in dis.get_instructions(transactions.transaction_event)}
    assert not built & {"BUILD_MAP", "BUILD_CONST_KEY_MAP"}


def test_transaction_event_never_hands_out_or_changes_its_fixed_parts():
    """Each event is its own dict in BootUI's key order: changing one never reaches the next."""
    row = {"thread": "t", "methodName": "m:f:1", "startTimestamp": 1, "status": "COMMITTED"}
    facts = (0, None, False, False, False, None, 0)
    first, _ = transactions.transaction_event(row, (None, "r-1", facts), None)
    first["source"] = "changed"
    first["ormFlushes"] = 7
    second, _ = transactions.transaction_event(row, (None, "r-2", facts), None)
    assert second is not first
    assert second["source"] == "transaction"
    assert second["ormFlushes"] == -1
    assert second["requestId"] == "r-2"
    assert tuple(second) == transactions._TX_KEYS  # pyright: ignore[reportPrivateUsage]


def test_transaction_call_site_walk_starts_above_sharpit_own_frames(monkeypatch: pytest.MonkeyPatch):
    """r4: the begin's call-site walk starts at the listener's caller; sharpit's own frames are never checked."""
    own = os.path.dirname(sharpit.__file__)
    checked: list[str] = []
    real = sqltrace.is_application_frame
    monkeypatch.setattr(sqltrace, "is_application_frame", lambda name: checked.append(name) or real(name))
    _, engine = _install()
    with engine.connect() as conn, conn.begin():
        pass
    assert checked, "the walk ran"
    assert [name for name in checked if name.startswith(own)] == []


def test_transaction_call_site_is_the_application_frame_that_began_it():
    handle, engine = _install()
    with engine.begin() as conn:
        _read(conn)
    name = "test_transaction_call_site_is_the_application_frame_that_began_it"
    assert re.fullmatch(rf".*test_transaction_journal:{name}:\d+", str(_records(handle)[0]["method"]))


def test_transaction_journal_failure_never_breaks_the_transaction(monkeypatch: pytest.MonkeyPatch):
    handle, engine = _install()
    journal = _journal(handle)

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
    """A build that raises costs only its own event: the other install's commit, settled after it, is still offered."""
    engine = sa.create_engine("sqlite://")
    first, _ = _install(engine=engine)
    second, _ = _install(engine=engine)
    built = transactions.transaction_event
    calls: list[None] = []

    def fails_first(*args: Any) -> Any:
        calls.append(None)
        if len(calls) == 1:
            raise RuntimeError("cannot build")
        return built(*args)

    monkeypatch.setattr(transactions, "transaction_event", fails_first)
    with engine.begin() as conn:
        _read(conn)
    assert len(calls) == 2, "the second install's event must still be built"
    assert len(_records(first)) + len(_records(second)) == 1


def test_transaction_journal_isolation_level_is_carried_when_set():
    handle, engine = _install()
    with engine.execution_options(isolation_level="SERIALIZABLE").begin() as conn:
        _read(conn)
    assert [r["isolation"] for r in _records(handle)] == ["SERIALIZABLE"]


def test_transaction_journal_event_built_inside_the_guard_on_the_rollback_path(monkeypatch: pytest.MonkeyPatch):
    """The rollback path: a build that raises is counted as that install's dropped event and costs nothing else."""
    engine = sa.create_engine("sqlite://")
    first, _ = _install(engine=engine)
    second, _ = _install(engine=engine)
    built = transactions.transaction_event
    calls: list[None] = []

    def fails_first(*args: Any) -> Any:
        calls.append(None)
        if len(calls) == 1:
            raise RuntimeError("cannot build")
        return built(*args)

    monkeypatch.setattr(transactions, "transaction_event", fails_first)
    with engine.connect() as conn:
        _write(conn)
        conn.rollback()
    assert len(calls) == 2, "the second install's event must still be built"
    assert len(_records(first)) + len(_records(second)) == 1
    dropped = [_journal(h).status()["dropped"].get("transaction", 0) for h in (first, second)]
    assert sum(dropped) == 1, "the event the guard lost is counted dropped"


def test_transaction_journal_source_disabled_builds_nothing(monkeypatch: pytest.MonkeyPatch):
    """Not a journal source: the begin reads no journal facts and builds no event; it only counts the drop."""
    handle, engine = _install(sources=("http",), sql_trace_enabled=False)  # no sql drop beside it
    calls: list[str] = []
    facts, built = transactions._facts, transactions.transaction_event  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(transactions, "_facts", lambda *a, **k: calls.append("facts") or facts(*a, **k))
    monkeypatch.setattr(transactions, "transaction_event", lambda *a: calls.append("event") or built(*a))
    with engine.begin() as conn:
        _read(conn)
    assert calls == []
    assert _journal(handle).status()["dropped"] == {"transaction": 1}


# --- the FastAPI tutorial's get_db session, through K2 errors-behind-2xx (W5a P-transaction r3) ---

K2 = "errors-behind-2xx"


def _tutorial(tmp_path: Path, **options: Any) -> tuple[TestClient, Any]:
    engine = _file_engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text("create table items (id integer primary key, name text)"))
    app = FastAPI()

    def get_db() -> Iterator[Any]:
        db = orm.Session(engine)
        try:
            yield db
        finally:
            db.close()

    @app.get("/items")
    def read_items(db: Any = Depends(get_db)) -> int:  # noqa: B008  # pyright: ignore[reportUnusedFunction]
        return db.execute(sa.text("select count(*) from items")).scalar_one()

    @app.get("/items/undo")
    def write_then_undo(db: Any = Depends(get_db)) -> str:  # noqa: B008  # pyright: ignore[reportUnusedFunction]
        db.execute(sa.text("insert into items (name) values ('a')"))
        db.rollback()
        return "ok"

    options.setdefault("runtime_journal_sources", ("http", "transaction"))
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, engines=[engine], **options)
    return TestClient(app), handle


def _k2(handle: Any) -> dict[str, Any]:
    report = insights_service(handle.context).report()
    return next(c for c in report["checks"] if c["kind"] == K2)


def test_errors_behind_2xx_read_only_get_db_requests_are_not_rolled_back(tmp_path: Path):
    client, handle = _tutorial(tmp_path)
    for _ in range(4):
        assert client.get("/items").status_code == 200
    in_requests = [r for r in _records(handle) if r["requestId"] is not None]
    assert [r["rolledBack"] for r in in_requests] == [False] * 4
    check = _k2(handle)
    assert check["status"] == "EVALUATED"
    assert check["findings"] == 0


def test_errors_behind_2xx_finds_a_get_db_write_that_rolled_back(tmp_path: Path):
    client, handle = _tutorial(tmp_path)
    assert client.get("/items").status_code == 200
    assert client.get("/items/undo").status_code == 200
    check = _k2(handle)
    assert check["status"] == "EVALUATED"
    assert check["findings"] == 1


def test_transaction_journal_paused_panel_still_offers_and_k2_finds_the_rollback(tmp_path: Path):
    """BootUI ``TransactionRecorder.java:206-211``: a paused panel skips its own buffer, the journal keeps recording."""
    client, handle = _tutorial(tmp_path, transactions_recording=False)
    assert client.get("/items/undo").status_code == 200
    assert [r["rolledBack"] for r in _records(handle) if r["requestId"] is not None] == [True]
    assert handle.context.capture.transactions.report([])["totalCaptured"] == 0, "the paused panel shows nothing"
    assert _k2(handle)["findings"] == 1


def test_errors_behind_2xx_claims_no_transaction_evidence_while_its_panel_is_disabled(tmp_path: Path):
    """BootUI ``ErrorsBehind2xx.notApplicable``: a source counts only while its panel is ``visible``."""
    client, handle = _tutorial(tmp_path, panels={"transactions": {"enabled": False}})
    assert client.get("/items/undo").status_code == 200
    assert _k2(handle)["status"] == "NOT_APPLICABLE"


# BootUI ``TransactionRecorder.record`` (v2.3.0, 296-340) offers the event from ``active``, whatever the buffer did.
def test_transaction_journal_event_survives_the_panel_row_being_cleared():
    handle, engine = _install()
    with engine.begin() as conn:
        _read(conn)
        handle.context.capture.transactions.clear()  # DELETE /transactions while the transaction is open
    assert len(_records(handle)) == 1


def test_transaction_journal_event_survives_the_panel_row_being_evicted(tmp_path: Path):
    handle, engine = _install(engine=_file_engine(tmp_path), transactions_max_entries=1)
    with engine.connect() as one, engine.connect() as two:
        _read(one)
        _read(two)
        one.commit()
        two.commit()
    assert len(_records(handle)) == 2


def test_transaction_journal_read_only_savepoint_is_not_rolled_back():
    handle, engine = _install()
    with engine.begin() as conn:
        savepoint = conn.begin_nested()
        _read(conn)
        savepoint.rollback()
    assert [(r["savepoint"], r["rolledBack"]) for r in _records(handle)] == [(True, False), (False, False)]


def test_transaction_journal_read_only_transaction_with_a_released_savepoint_is_not_rolled_back():
    handle, engine = _install()
    with engine.connect() as conn:
        with conn.begin_nested():
            _read(conn)
        conn.rollback()
    assert [(r["savepoint"], r["rolledBack"]) for r in _records(handle)] == [(True, False), (False, False)]


def test_transaction_journal_select_behind_long_whitespace_is_not_a_write():
    handle, engine = _install()
    with engine.connect() as conn:
        conn.execute(sa.text("\n" + " " * 20 + "SELECT 1"))
        conn.rollback()
    assert [r["rolledBack"] for r in _records(handle)] == [False]


# ported: RecorderPublishingTests.aDisabledRecorderPublishesNothing
def test_transaction_journal_disabled_recorder_publishes_nothing():
    handle, engine = _install(transactions_enabled=False)
    with engine.begin() as conn:
        _write(conn)
    assert _records(handle) == ()
