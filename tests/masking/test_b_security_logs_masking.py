from __future__ import annotations

from sharpit.engine.capture.securitylogs import AUTHENTICATION_FAILURE, SecurityEventBuffer, security_logs_report
from sharpit.engine.masking import MASK, Exposure, Masker

SECRETS = {
    "token": "tok-123",
    "password": "hunter2",
    "session_id": "s-1",
    "clientIp": "ignored-by-name",
    "remote_addr": "10.0.0.7",
    "note": "token=abc123 for postgresql://user:pw@db.local/app",
}


def test_security_event_data_masked_before_output() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, "alice", {**SECRETS, "big": "v" * 10_240}, None)
    report = security_logs_report(
        buffer,
        Masker(Exposure.MASKED, True, None),
        principal=None,
        type=None,
        after_ns=None,
        offset=None,
        limit=None,
        unavailable_reason=None,
    )
    text = str(report)
    leaked = [v for k, v in SECRETS.items() if k != "clientIp" and v in text]
    assert leaked == [], "secret values must be masked before output"
    assert "abc123" not in text, "a key=value secret inside free text must be masked"
    assert "user:pw@" not in text, "URL credentials inside free text must be masked"
    assert MASK in text, "the report must keep a visible redaction marker"
    assert "v" * 257 not in text, "a 10 kB value is truncated to 256 characters"
