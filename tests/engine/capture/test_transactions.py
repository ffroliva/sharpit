from __future__ import annotations

import pytest

from sharpit.engine.capture.transactions import TransactionRecorder
from sharpit.engine.masking import Masker


# ported: TransactionRecorderTests.recordsACommittedRootTransaction
def test_records_committed_root() -> None:
    recorder = TransactionRecorder(Masker("MASKED", True, None))
    entry_id = recorder.begin(
        1, parent=None, method="orders:create", thread="MainThread", trace_id=None, connection_id="db-1"
    )
    assert entry_id > 0, "a captured transaction must receive a positive id"
    recorder.end(entry_id, "COMMITTED")
    report = recorder.report([])
    assert report["entries"][0]["status"] == "COMMITTED", "committing a root transaction must retain its status"


# ported: TransactionRecorderTests.recordsARolledBackTransactionWithErrorMessage
def test_records_rolled_back() -> None:
    recorder = _recorder()
    entry_id = _begin(recorder)
    recorder.end(entry_id, "ROLLED_BACK", RuntimeError("rolled back"))
    assert recorder.report([])["entries"][0]["status"] == "ROLLED_BACK", (
        "rolling back a root transaction must retain its status"
    )


def _recorder(**options: object) -> TransactionRecorder:
    return TransactionRecorder(Masker("MASKED", True, None), **options)  # type: ignore[arg-type]


def _begin(recorder: TransactionRecorder, connection_id: str | None = "db-1") -> int:
    return recorder.begin(
        1, parent=None, method="orders:create", thread="MainThread", trace_id=None, connection_id=connection_id
    )


# ported: TransactionRecorderTests.evictsOldestEntryOnceBufferIsFull
def test_bounded_entries_report_stats() -> None:
    recorder = _recorder(max_entries=1)
    first = _begin(recorder)
    recorder.end(first, "COMMITTED")
    second = _begin(recorder)
    recorder.end(second, "ROLLED_BACK")
    report = recorder.report([])
    assert report["bufferSize"] == 1, "the transaction ring must respect max_entries"
    assert report["totalCaptured"] == 2, "totalCaptured must include evicted transactions"
    assert report["stats"]["evicted"] == 1, "the report must count evicted transactions"
    assert report["stats"]["rolledBackCount"] == 1, "retained rolled back transactions must be counted"
    assert report["entries"][0]["status"] == "ROLLED_BACK", "the ring must retain its newest transaction"


def test_buffer_size_reports_capacity_when_empty() -> None:
    recorder = _recorder(max_entries=7)
    assert recorder.report([])["bufferSize"] == 7, "bufferSize must report the configured ring capacity"


def test_flags_slow_and_held() -> None:
    recorder = _recorder(slow_threshold_ms=0, hold_threshold_ms=0)
    entry_id = _begin(recorder)
    recorder.end(entry_id, "COMMITTED")
    row = recorder.report([])["entries"][0]
    assert row["slow"] is False, "a zero slow threshold must disable slow transaction flags"
    assert row["connectionHeld"] is False, "a zero hold threshold must disable held connection flags"


# ported: TransactionRecorderTests.clearEmptiesTheBufferWithoutResettingTotalCaptured
# ported: TransactionRecorderTests.beginTransactionReturnsSentinelWhenPaused
def test_paused_records_nothing() -> None:
    recorder = _recorder(recording=False)
    entry_id = _begin(recorder)
    assert entry_id == -1, "a paused recorder must return the sentinel id"
    assert recorder.report([])["entries"] == [], "a paused recorder must not retain transactions"


# ported: TransactionRecorderTests.completeTransactionIgnoresSentinelAndUnknownIds
def test_unknown_end_ignored() -> None:
    recorder = _recorder()
    entry_id = _begin(recorder)
    recorder.end(-1, "COMMITTED")
    recorder.end(entry_id + 1, "COMMITTED")
    assert recorder.report([])["entries"][0]["id"] == entry_id, "an unknown completion must leave entries unchanged"


# derived: masked transaction error message
def test_error_message_is_masked() -> None:
    recorder = _recorder()
    entry_id = _begin(recorder)
    recorder.end(entry_id, "UNKNOWN", RuntimeError("failed postgresql://user:secret@db.local/app"))
    message = recorder.report([])["entries"][0]["errorMessage"]
    assert "secret" not in message, "transaction errors must not expose connection passwords"
    assert "******" in message, "masked transaction errors must show the configured mask"


def test_sql_trace_unavailable_warning() -> None:
    recorder = _recorder()
    entry_id = _begin(recorder)
    recorder.end(entry_id, "COMMITTED")
    warnings = recorder.report(None)["warnings"]
    assert warnings == ["SQL Trace is not active, so SQL statement/connection counts are not correlated."], (
        "missing SQL Trace must explain why statement counts are unavailable"
    )


# ported: TransactionRecorderTests.tracksParentChildNestingOnTheSameThread
def test_savepoint_is_a_child_entry(monkeypatch) -> None:
    from types import SimpleNamespace

    from sharpit.engine.capture.transactions import tx_begin, tx_commit, tx_release_savepoint, tx_savepoint
    from sharpit.engine.sources import dispatch

    recorder = _recorder()
    context = SimpleNamespace(
        context_id="test-context",
        capture=SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None)),
        settings=SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        ),
    )
    connection = SimpleNamespace(info={}, engine=object(), connection=SimpleNamespace(dbapi_connection=object()))
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: [context])
    tx_begin(connection)
    outer_id = connection.info["sharpit_tx"][0][1]
    tx_savepoint(connection, "sa_savepoint_1")
    tx_release_savepoint(connection, "sa_savepoint_1", None)
    tx_commit(connection)
    rows = recorder.report([])["entries"]
    assert len(rows) == 2, "a savepoint must be represented as a child transaction entry"
    child = next(row for row in rows if row["parentId"] is not None)
    assert child["parentId"] == outer_id, "the savepoint entry must point to its outer transaction"
    outer = next(row for row in rows if row["id"] == outer_id)
    assert outer["status"] == "COMMITTED", "releasing a savepoint must not close its outer transaction"


def test_connection_event_slot_records_real_sqlite_transaction(monkeypatch) -> None:
    from types import SimpleNamespace

    import pytest

    from sharpit.engine.capture.transactions import attach
    from sharpit.engine.sources import dispatch

    sa = pytest.importorskip("sqlalchemy")
    recorder = _recorder()
    context = SimpleNamespace(
        context_id="sqlite-context",
        capture=SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None)),
        settings=SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        ),
    )
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: [context])
    engine = sa.create_engine("sqlite://")
    remove = attach()
    assert remove is not None, "the connection event slot should attach when SQLAlchemy is loaded"
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            transaction.commit()
    finally:
        remove()
        engine.dispose()
    report = recorder.report([])
    assert report["totalCaptured"] == 1, "the real SQLite begin event must be captured once"
    assert report["entries"][0]["status"] == "COMMITTED", "the real SQLite commit event must close the entry"


def test_failed_commit_is_unknown_with_masked_error_and_commit_duration(monkeypatch) -> None:
    import time
    from types import SimpleNamespace

    import pytest

    from sharpit.engine.capture.transactions import attach
    from sharpit.engine.sources import dispatch

    sa = pytest.importorskip("sqlalchemy")
    recorder = _recorder()
    context = SimpleNamespace(
        context_id="failed-commit-context",
        capture=SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None)),
        settings=SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        ),
    )
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: [context])

    class FailingCommitConnection:
        def __init__(self, connection) -> None:
            self.connection = connection

        def __getattr__(self, name: str):
            return getattr(self.connection, name)

        def commit(self) -> None:
            time.sleep(0.01)
            raise RuntimeError("failed postgresql://user:secret@db.local/app")

    base_engine = sa.create_engine("sqlite://")
    engine = sa.create_engine("sqlite://", creator=lambda: FailingCommitConnection(base_engine.pool._creator()))
    remove = attach()
    assert remove is not None, "the connection event slot should attach when SQLAlchemy is loaded"
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            with pytest.raises(RuntimeError):
                transaction.commit()
    finally:
        remove()
        engine.dispose()
        base_engine.dispose()

    row = recorder.report([])["entries"][0]
    assert row["status"] == "UNKNOWN", "a failed DBAPI commit must never be reported as committed"
    assert "secret" not in row["errorMessage"], "a failed commit must not expose connection passwords"
    assert row["durationMillis"] >= 10, "failed transaction duration must include time spent in DBAPI commit"


def test_savepoint_closes_one_child_per_context(monkeypatch) -> None:
    from types import SimpleNamespace

    from sharpit.engine.capture.transactions import tx_begin, tx_release_savepoint, tx_savepoint
    from sharpit.engine.sources import dispatch

    contexts = []
    for context_id in ("first", "second"):
        recorder = _recorder()
        contexts.append(
            SimpleNamespace(
                context_id=context_id,
                capture=SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None)),
                settings=SimpleNamespace(
                    transactions_enabled=True,
                    panels={"transactions": SimpleNamespace(enabled=True)},
                    sql_trace_capture_call_site=False,
                ),
            )
        )
    connection = SimpleNamespace(info={}, engine=object(), connection=SimpleNamespace(dbapi_connection=object()))
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: contexts)
    tx_begin(connection)
    tx_savepoint(connection, "sa_savepoint_1")
    tx_release_savepoint(connection, "sa_savepoint_1", None)
    assert len(connection.info["sharpit_tx"]) == 2, "a savepoint event must close its child entry in each context"


def test_untracked_savepoint_end_does_not_close_root(monkeypatch) -> None:
    from types import SimpleNamespace

    from sharpit.engine.capture.transactions import tx_begin, tx_commit, tx_rollback_savepoint
    from sharpit.engine.sources import dispatch

    recorder = _recorder()
    context = SimpleNamespace(
        context_id="untracked-savepoint-context",
        capture=SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None)),
        settings=SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        ),
    )
    connection = SimpleNamespace(info={}, engine=object(), connection=SimpleNamespace(dbapi_connection=object()))
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: [context])
    tx_begin(connection)
    root_id = connection.info["sharpit_tx"][0][1]
    tx_rollback_savepoint(connection, "not-tracked", None)
    tx_commit(connection)
    row = recorder.report([])["entries"][0]
    assert row["id"] == root_id, "an untracked savepoint event must leave the root transaction on the stack"
    assert row["status"] == "COMMITTED", "an untracked savepoint release must not close the root transaction"


def test_begin_over_open_entry_closes_it_unknown(monkeypatch) -> None:
    from types import SimpleNamespace

    from sharpit.engine.capture.transactions import tx_begin
    from sharpit.engine.sources import dispatch

    recorder = _recorder()
    context = SimpleNamespace(
        context_id="orphan-context",
        capture=SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None)),
        settings=SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        ),
    )
    connection = SimpleNamespace(info={}, engine=object(), connection=SimpleNamespace(dbapi_connection=object()))
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: [context])
    tx_begin(connection)
    first_id = connection.info["sharpit_tx"][0][1]
    tx_begin(connection)
    rows = {row["id"]: row for row in recorder.report([])["entries"]}
    assert rows[first_id]["status"] == "UNKNOWN", "a new begin must close an orphaned open entry as unknown"
    assert rows[max(rows)]["status"] == "OPEN", "an in-flight transaction must be reported as open"


def test_oldest_open_entry_is_not_evicted() -> None:
    recorder = _recorder(max_entries=1)
    first_id = _begin(recorder)
    second_id = _begin(recorder)
    rows = {row["id"]: row for row in recorder.report([])["entries"]}
    assert first_id in rows, "the oldest open transaction must remain retained"
    assert second_id in rows, "a newly opened transaction must be retained even when the ring is full"


def test_internal_transaction_callbacks_are_skipped(monkeypatch) -> None:
    from types import SimpleNamespace

    from sharpit.engine.capture.correlation import internal
    from sharpit.engine.capture.transactions import tx_begin, tx_commit
    from sharpit.engine.sources import dispatch

    recorder = _recorder()
    context = SimpleNamespace(
        context_id="internal-context",
        capture=SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None)),
        settings=SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        ),
    )
    connection = SimpleNamespace(info={}, engine=object(), connection=SimpleNamespace(dbapi_connection=object()))
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: [context])
    with internal():
        tx_begin(connection)
        tx_commit(connection)
    assert recorder.report([])["entries"] == [], (
        "sharpit's internal database reads must stay out of the transaction report"
    )


def test_listener_raising_recorder_is_swallowed(monkeypatch) -> None:
    from types import SimpleNamespace

    from sharpit.engine.capture.transactions import TransactionRecorder, tx_begin
    from sharpit.engine.sources import dispatch

    recorder = _recorder()
    hook_errors: list[BaseException] = []
    context = SimpleNamespace(
        context_id="raising-recorder-context",
        capture=SimpleNamespace(
            transactions=recorder,
            wiring=SimpleNamespace(hook_failed=lambda _hook, exc: hook_errors.append(exc)),
        ),
        settings=SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        ),
    )
    connection = SimpleNamespace(info={}, engine=object(), connection=SimpleNamespace(dbapi_connection=object()))

    def raising_begin(*_args, **_kwargs):
        raise RuntimeError("recorder failed")

    monkeypatch.setattr(TransactionRecorder, "begin", raising_begin)
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: [context])
    tx_begin(connection)
    assert len(hook_errors) == 1, "a recorder failure must be reported through the capture hook"


def test_listener_never_executes_sql() -> None:
    import pytest

    sa = pytest.importorskip("sqlalchemy")
    from fastapi import FastAPI
    from sharpit import install

    engine = sa.create_engine("sqlite://")
    statements: list[str] = []
    sa.event.listen(engine, "before_cursor_execute", lambda *_args: statements.append("sql"))
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            transaction.commit()
        assert statements == [], "transaction listeners must not execute SQL themselves"
    finally:
        handle.uninstall_capture()
        engine.dispose()


def test_sql_counts_correlate_at_report_time() -> None:
    import time
    from datetime import UTC, datetime

    recorder = _recorder()
    entry_id = _begin(recorder, "db-1")
    midpoint = datetime.fromtimestamp(time.time_ns() / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")
    recorder.end(entry_id, "COMMITTED")
    report = recorder.report([{"connectionId": "db-1", "timestamp": midpoint}])
    assert report["entries"][0]["sqlStatementCount"] == 1, "matching SQL Trace rows must be correlated when reporting"


@pytest.mark.asyncio
async def test_subscriber_signalled() -> None:
    import asyncio

    recorder = _recorder()
    subscription = recorder.changes.subscribe(asyncio.get_running_loop())
    recorder.set_recording(False)
    event = await asyncio.wait_for(subscription.__anext__(), timeout=1)
    assert event is None, "recording changes must notify transaction subscribers"
    subscription.close()


def test_attacher_retries_late_sqlalchemy_and_removes_partial_listeners(monkeypatch) -> None:
    from sharpit.engine import sqla
    from sharpit.engine.capture import transactions
    from sharpit.engine.capture.transactions import attach

    removed: list[str] = []
    installed: list[str] = []
    monkeypatch.setattr(transactions, "_attach_count", 0)
    monkeypatch.setattr(transactions, "_attach_removers", [])

    def late(event, _callback):
        installed.append(event)
        if event == "rollback":
            return None
        return lambda: removed.append(event)

    monkeypatch.setattr(sqla, "add_connection_listener", late)
    assert attach() is None, "late SQLAlchemy import must leave the lane attacher retryable"
    assert removed == ["commit", "begin"], "a partial attachment must remove every listener it armed"
    installed.clear()
    removed.clear()
    monkeypatch.setattr(sqla, "add_connection_listener", lambda event, _callback: lambda: removed.append(event))
    remove = attach()
    assert remove is not None, "the attacher must succeed when SQLAlchemy becomes available"
    assert len(removed) == 0, "successful attach must keep listeners until the remover runs"
    remove()
    assert len(removed) == 7, "one remover must detach all seven transaction events"


def test_listener_remover_releases_attachments_when_called(monkeypatch) -> None:
    from sharpit.engine import sqla
    from sharpit.engine.capture import transactions
    from sharpit.engine.capture.transactions import attach

    removed: list[str] = []
    monkeypatch.setattr(transactions, "_attach_count", 0)
    monkeypatch.setattr(transactions, "_attach_removers", [])
    monkeypatch.setattr(sqla, "add_connection_listener", lambda event, _callback: lambda: removed.append(event))
    remove = attach()
    assert remove is not None, "the transaction listener must attach for this context"
    remove()
    assert len(removed) == 7, "calling the owning teardown must release all class-level listeners"


def test_listener_release_never_runs_under_attach_lock(monkeypatch) -> None:
    import gc
    import threading

    from sharpit.engine import sqla
    from sharpit.engine.capture import transactions
    from sharpit.engine.capture.transactions import attach

    monkeypatch.setattr(transactions, "_attach_count", 0)
    monkeypatch.setattr(transactions, "_attach_removers", [])
    monkeypatch.setattr(sqla, "add_connection_listener", lambda _event, _callback: lambda: None)
    remover = attach()
    assert remover is not None, "the transaction listener must attach for this context"
    lock_held = threading.Event()
    completed = threading.Event()

    def collect() -> None:
        nonlocal remover
        transactions._attach_lock.acquire()
        lock_held.set()
        remover = None
        gc.collect()
        completed.set()

    thread = threading.Thread(target=collect, daemon=True)
    thread.start()
    assert lock_held.wait(timeout=0.2), "the collector thread must acquire the attach lock"
    thread.join(timeout=0.2)
    blocked = not completed.is_set()
    transactions._attach_lock.release()
    thread.join(timeout=0.2)
    assert not blocked, "listener release must not block while the attach lock is held"
