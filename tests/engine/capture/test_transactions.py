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
