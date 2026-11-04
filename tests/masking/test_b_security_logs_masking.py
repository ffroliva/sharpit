from __future__ import annotations

import json

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install, record_security_event
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
JWT = "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".dozjgNryP4J3jVmNHl0w5N"
URL = "/sharpit/api/security-logs"


def _recorded(principal: str, **options: object) -> TestClient:
    app = FastAPI()

    @app.get("/login")
    def login() -> dict[str, str]:
        record_security_event("AUTHENTICATION_SUCCESS", principal=principal)
        return {}

    install(app, enabled="ON", show_banner=False, **options)  # type: ignore[arg-type]
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    client.get("/login")
    return client


def test_recorded_principal_is_masked_in_the_report() -> None:
    assert JWT not in json.dumps(_recorded(JWT).get(URL).json())


def test_recorded_principal_filter_cannot_confirm_a_secret() -> None:
    assert _recorded(JWT).get(URL, params={"principal": JWT}).json()["events"] == []


def test_recorded_principal_follows_the_exposure_as_exchanges_do() -> None:
    client = _recorded(JWT, expose_values="FULL")
    assert client.get(URL).json()["events"][0]["principal"] == JWT


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
