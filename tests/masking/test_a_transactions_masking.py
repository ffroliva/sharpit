from __future__ import annotations

from sharpit.engine.capture.transactions import TransactionRecorder
from sharpit.engine.masking import MASK, Exposure, Masker


def test_transaction_error_message_masks_connection_secrets() -> None:
    recorder = TransactionRecorder(Masker(Exposure.MASKED, True, None))
    entry_id = recorder.begin(
        1, parent=None, method="orders:create", thread="MainThread", trace_id=None, connection_id="db-1"
    )
    recorder.end(entry_id, "UNKNOWN", RuntimeError("failed at postgresql://user:secret@db.local/app"))
    message = recorder.report([])["entries"][0]["errorMessage"]
    assert "secret" not in message, "transaction error messages must be masked before report serialization"
    assert MASK in message, "the report must retain a visible redaction marker"
