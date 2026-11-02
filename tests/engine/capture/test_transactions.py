from __future__ import annotations

from sharpit.engine.capture.transactions import TransactionRecorder
from sharpit.engine.masking import Masker


def test_records_committed_root() -> None:
    recorder = TransactionRecorder(Masker("MASKED", True, None))
    entry_id = recorder.begin(
        1, parent=None, method="orders:create", thread="MainThread", trace_id=None, connection_id="db-1"
    )
    assert entry_id > 0, "a captured transaction must receive a positive id"
    recorder.end(entry_id, "COMMITTED")
    report = recorder.report([])
    assert report["entries"][0]["status"] == "COMMITTED", "committing a root transaction must retain its status"


def _recorder(**options: object) -> TransactionRecorder:
    return TransactionRecorder(Masker("MASKED", True, None), **options)  # type: ignore[arg-type]


def _begin(recorder: TransactionRecorder, connection_id: str | None = "db-1") -> int:
    return recorder.begin(
        1, parent=None, method="orders:create", thread="MainThread", trace_id=None, connection_id=connection_id
    )


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


def test_clear_keeps_total_captured() -> None:
    recorder = _recorder()
    entry_id = _begin(recorder)
    recorder.end(entry_id, "COMMITTED")
    recorder.clear()
    report = recorder.report([])
    assert report["bufferSize"] == 0, "clear must empty the retained transactions"
    assert report["totalCaptured"] == 1, "clear must keep the lifetime captured count"


def test_paused_records_nothing() -> None:
    recorder = _recorder(recording=False)
    entry_id = _begin(recorder)
    assert entry_id == -1, "a paused recorder must return the sentinel id"
    assert recorder.report([])["entries"] == [], "a paused recorder must not retain transactions"


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
    assert recorder.report([])["bufferSize"] == 0, (
        "sharpit's internal database reads must stay out of the transaction report"
    )


def test_sql_counts_correlate_at_report_time() -> None:
    import time
    from datetime import UTC, datetime

    recorder = _recorder()
    entry_id = _begin(recorder, "db-1")
    midpoint = datetime.fromtimestamp(time.time_ns() / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")
    recorder.end(entry_id, "COMMITTED")
    report = recorder.report([{"connectionId": "db-1", "timestamp": midpoint}])
    assert report["entries"][0]["sqlStatementCount"] == 1, "matching SQL Trace rows must be correlated when reporting"


def test_attacher_retries_late_sqlalchemy_and_removes_partial_listeners(monkeypatch) -> None:
    from sharpit.engine import sqla
    from sharpit.engine.capture.transactions import attach

    removed: list[str] = []
    installed: list[str] = []

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
    assert len(removed) == 6, "one remover must detach all six transaction events"
