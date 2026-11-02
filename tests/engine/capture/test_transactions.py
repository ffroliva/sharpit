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
