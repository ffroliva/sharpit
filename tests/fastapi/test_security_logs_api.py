from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException
from tests.golden import assert_parity

from conftest import golden
from fastapi import FastAPI
from sharpit import install, record_security_event
from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.capture.securitylogs import (
    AUTHENTICATION_FAILURE,
    AUTHENTICATION_SUCCESS,
    AUTHORIZATION_FAILURE,
    INVALID_AFTER,
    SecurityEventBuffer,
    security_logs_report,
)
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import CAPTURE_TOO_LATE_REASON, wiring_of

LOCAL = ("127.0.0.1", 50000)


def _app(**kwargs: Any) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()

    @app.get("/login")
    def login() -> None:  # pyright: ignore[reportUnusedFunction]
        raise HTTPException(401)

    @app.get("/forbidden")
    def forbidden() -> None:  # pyright: ignore[reportUnusedFunction]
        raise HTTPException(403)

    @app.get("/ok")
    def ok() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    @app.get("/record")
    def record() -> dict[str, str | None]:  # pyright: ignore[reportUnusedFunction]
        record_security_event(AUTHENTICATION_SUCCESS, principal="alice", data={"details": "ok"})
        info = REQUEST.get()
        return {"rid": info.id if info else None}

    @app.get("/bad")
    def bad() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        record_security_event(123)  # type: ignore[arg-type]
        record_security_event(AUTHENTICATION_SUCCESS, principal=5)  # type: ignore[arg-type]
        record_security_event(AUTHENTICATION_SUCCESS, data="not a mapping")  # type: ignore[arg-type]
        return {"ok": True}

    return app, install(app, show_banner=False, **({"enabled": "ON"} | kwargs))


def _events(handle: SharpitHandle) -> list[dict[str, Any]]:
    buffer = handle.context.capture.security_logs
    if not isinstance(buffer, SecurityEventBuffer):
        return []
    report = security_logs_report(
        buffer,
        handle.context.masker,
        principal=None,
        type=None,
        after_ns=None,
        offset=None,
        limit=None,
        unavailable_reason=None,
    )
    return report["events"]


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def test_401_becomes_authentication_failure() -> None:
    app, handle = _app()
    try:
        assert _client(app).get("/login").status_code == 401
        events = _events(handle)
        assert [e["type"] for e in events] == [AUTHENTICATION_FAILURE], "a 401 is an authentication failure"
        assert events[0]["principal"] is None, "no user in scope means no principal"
        assert {r["name"]: r["value"] for r in events[0]["data"]} == {
            "method": "GET",
            "path": "/login",
            "status": "401",
        }
    finally:
        handle.uninstall_capture()


def test_403_becomes_authorization_failure() -> None:
    app, handle = _app()
    try:
        assert _client(app).get("/forbidden").status_code == 403
        assert [e["type"] for e in _events(handle)] == [AUTHORIZATION_FAILURE], "a 403 is an authorization failure"
    finally:
        handle.uninstall_capture()


def test_200_records_nothing() -> None:
    app, handle = _app()
    try:
        assert _client(app).get("/ok").status_code == 200
        assert isinstance(handle.context.capture.security_logs, SecurityEventBuffer), "the panel's buffer exists"
        assert _events(handle) == [], "a 200 is not a security event"
    finally:
        handle.uninstall_capture()


def test_sharpit_403_not_recorded() -> None:
    app, handle = _app()
    try:
        response = _client(app).get("/sharpit/api/overview", headers={"host": "evil.example"})
        assert response.status_code == 403, "the guard refuses a foreign Host"
        assert isinstance(handle.context.capture.security_logs, SecurityEventBuffer), "the panel's buffer exists"
        assert _events(handle) == [], "sharpit's own refusals are never host security events"
    finally:
        handle.uninstall_capture()


def test_record_goes_to_the_current_apps_context_only() -> None:
    app_a, handle_a = _app()
    app_b, handle_b = _app()
    try:
        assert _client(app_a).get("/record").status_code == 200
        assert [e["type"] for e in _events(handle_a)] == [AUTHENTICATION_SUCCESS], "app A recorded its event"
        assert _events(handle_b) == [], "app B never sees app A's event"
    finally:
        handle_a.uninstall_capture()
        handle_b.uninstall_capture()


def test_record_outside_request_is_noop() -> None:
    _app_, handle = _app()
    try:
        record_security_event(AUTHENTICATION_SUCCESS, principal="alice")
        assert isinstance(handle.context.capture.security_logs, SecurityEventBuffer), "the panel's buffer exists"
        assert _events(handle) == [], "an event outside any request has no app to go to"
    finally:
        handle.uninstall_capture()


def test_record_when_inactive_is_noop() -> None:
    app, handle = _app(enabled="OFF")
    response = _client(app).get("/record")
    assert response.status_code == 200, "recording never fails the host request"
    assert handle.context.capture.security_logs is None, "an inactive sharpit keeps no buffer"


def test_record_bad_args_never_raises(caplog: pytest.LogCaptureFixture) -> None:
    app, handle = _app()
    try:
        with caplog.at_level(logging.WARNING, logger="sharpit"):
            assert _client(app).get("/bad").status_code == 200, "bad arguments never raise into the app"
        warnings = [r.getMessage() for r in caplog.records if "record_security_event" in r.getMessage()]
        assert len(warnings) == 3, warnings
        assert _events(handle) == [], "bad events are dropped"
    finally:
        handle.uninstall_capture()


# ported: SecurityLogsControllerTests.anEventPublishedDuringARequestCarriesItsRequestId
def test_event_in_request_carries_request_id() -> None:
    app, handle = _app()
    try:
        rid = _client(app).get("/record").json()["rid"]
        assert [e["requestId"] for e in _events(handle)] == [rid], "the event carries its request's id"
    finally:
        handle.uninstall_capture()


def test_hook_raising_is_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    app, handle = _app()
    wiring = wiring_of(handle.context)
    assert wiring is not None

    def explode(_scope: object, _status: int) -> None:
        raise RuntimeError("secret-bearing message")

    wiring.on_security_event = explode
    try:
        with caplog.at_level(logging.WARNING, logger="sharpit"):
            statuses = [_client(app).get("/login").status_code for _ in range(2)]
        assert statuses == [401, 401], "a failing hook never changes the host's response"
        warnings = [r.getMessage() for r in caplog.records if "security event" in r.getMessage()]
        assert len(warnings) == 1, warnings
    finally:
        handle.uninstall_capture()


API = "/sharpit/api/security-logs"
MCP = "/sharpit/api/mcp"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.c2lnbmF0dXJl"
GOLDEN_PRINCIPAL = "00000000-0000-4000-8000-000000000001"
GOLDEN_DETAILS = "WebAuthenticationDetails [RemoteIpAddress=127.0.0.1, SessionId=null]"


def _panel_app(**kwargs: Any) -> tuple[FastAPI, SharpitHandle]:
    """Routes that record what each test needs; ``_app`` above stays as its red commit had it."""
    app = FastAPI()

    @app.get("/denied")
    def denied() -> None:  # pyright: ignore[reportUnusedFunction]
        raise HTTPException(401)

    @app.get("/golden")
    def golden_event() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        record_security_event(AUTHENTICATION_SUCCESS, principal=GOLDEN_PRINCIPAL, data={"details": GOLDEN_DETAILS})
        return {"ok": True}

    @app.get("/event")
    def event(principal: str, kind: str, details: str = "") -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        record_security_event(kind, principal=principal, data={"details": details, "type": "BadCredentialsException"})
        return {"ok": True}

    options: dict[str, Any] = {"enabled": "ON", "show_banner": False, "config_scan": False, "mcp_enabled": "ON"}
    return app, install(app, **(options | kwargs))


def _call_tool(client: TestClient) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_security_logs"}}
    return client.post(MCP, json=call).json()


def test_report_golden_parity() -> None:
    app, handle = _panel_app()
    try:
        client = _client(app)
        assert client.get("/golden").status_code == 200
        response = client.get(API)
        assert response.status_code == 200, "the panel serves its report"
        body = response.json()
        assert_parity("security-logs", "report", body)
        expected = golden("2.2.0/security-logs/captured")["events"][0]
        events = body["events"]
        assert len(events) == 1, "the recorded event is reported"
        shown = {k: v for k, v in events[0].items() if k not in ("timestamp", "requestId", "traceId")}
        assert shown == {k: v for k, v in expected.items() if k not in ("timestamp", "requestId", "traceId")}
        assert body["typeSummaries"] == [{"type": AUTHENTICATION_SUCCESS, "count": 1}], "the type summary item"
        assert (body["auditEventsPresent"], body["unavailableReason"], body["maxLogs"]) == (True, None, 500)
    finally:
        handle.uninstall_capture()


# ported: SecurityLogsControllerTests.eventsAreNewestFirstAndBoundedByConfiguredMaximum
def test_events_newest_first_bounded() -> None:
    app, handle = _panel_app(security_logs_max_logs=2)
    try:
        client = _client(app)
        for who in ("a", "b", "c"):
            assert client.get("/event", params={"principal": who, "kind": AUTHENTICATION_SUCCESS}).status_code == 200
        response = client.get(API)
        assert response.status_code == 200, "the panel serves its report"
        assert [e["principal"] for e in response.json()["events"]] == ["c", "b"], "newest first, bounded by maxLogs"
        assert response.json()["maxLogs"] == 2, "maxLogs reports the configured bound"
    finally:
        handle.uninstall_capture()


# ported: SecurityLogsControllerTests.filtersByPrincipalTypeAndAfter
def test_filters() -> None:
    app, handle = _panel_app()
    try:
        client = _client(app)
        client.get("/event", params={"principal": "alice", "kind": AUTHENTICATION_SUCCESS})
        client.get("/event", params={"principal": "bob", "kind": AUTHENTICATION_SUCCESS})
        client.get("/denied")
        by_principal = client.get(API, params={"principal": " alice "})
        assert by_principal.status_code == 200, "the panel serves its report"
        assert [e["principal"] for e in by_principal.json()["events"]] == ["alice"], "exact trimmed principal"
        by_type = client.get(API, params={"type": AUTHENTICATION_FAILURE}).json()
        assert [e["type"] for e in by_type["events"]] == [AUTHENTICATION_FAILURE], "exact type"
        later = client.get(API, params={"after": "2999-01-01T00:00:00Z"}).json()
        assert later["events"] == [], "after keeps only later events"
        paged = client.get(API, params={"offset": 1, "limit": 1}).json()
        assert paged["page"]["returned"] == 1, "offset/limit page the events"
    finally:
        handle.uninstall_capture()


# ported: SecurityLogsControllerTests.masksSensitiveEventDataAndHidesValuesInMetadataOnlyMode
def test_masks_and_metadata_only() -> None:
    app, handle = _panel_app(expose_values="METADATA_ONLY")
    try:
        client = _client(app)
        client.get("/event", params={"principal": "alice", "kind": AUTHENTICATION_FAILURE, "details": "x"})
        response = client.get(API)
        assert response.status_code == 200, "the panel serves its report"
        events = response.json()["events"]
        assert [e["principal"] for e in events] == [None], "METADATA_ONLY hides the principal"
        assert [r["value"] for r in events[0]["data"]] == [None, None], "METADATA_ONLY hides every value"
    finally:
        handle.uninstall_capture()


# ported: SecurityLogsControllerTests.absentAuditRepositoryReturnsUnavailableReport
def test_unavailable_when_capture_missing() -> None:
    late = FastAPI()
    late.get("/host")(lambda: {})
    client = _client(late)
    assert client.get("/host").status_code == 200  # the middleware stack is built now
    handle = install(late, enabled="ON", show_banner=False, config_scan=False)
    try:
        response = client.get(API)
        assert response.status_code == 200, "the panel serves its report"
        body = response.json()
        assert (body["auditEventsPresent"], body["unavailableReason"]) == (True, CAPTURE_TOO_LATE_REASON)
    finally:
        handle.uninstall_capture()


# ported: SecurityLogsControllerTests.invalidAfterParameterReturnsBadRequest
def test_invalid_after_is_400() -> None:
    app, handle = _panel_app()
    try:
        client = _client(app)
        for raw in ("2026-11-01T10:15:30", "not-a-date-<script>"):
            response = client.get(API, params={"after": raw})
            assert response.status_code == 400, raw
            assert response.json() == {"error": INVALID_AFTER}, "the error never echoes the value"
    finally:
        handle.uninstall_capture()


def test_security_event_values_masked_everywhere() -> None:
    app, handle = _panel_app(stream_max_seconds=0.01)
    try:
        client = _client(app)
        client.get("/event", params={"principal": "alice", "kind": AUTHENTICATION_FAILURE, "details": f"Bearer {JWT}"})
        assert client.get("/denied", headers={"Authorization": f"Bearer {JWT}"}).status_code == 401
        report = client.get(API)
        stream = client.get(f"{API}/stream")
        tool = _call_tool(client)
        assert report.status_code == 200, "the panel serves its report"
        assert stream.status_code == 200, "the panel serves its stream"
        assert len(report.json()["events"]) == 2, "both events are reported"
        bodies = (("get", report.text), ("stream", stream.text), ("mcp", str(tool)))
        assert [name for name, text in bodies if JWT in text] == [], "the bearer token never leaves sharpit"
        assert [e["principal"] for e in report.json()["events"]] == [None, "alice"], "principal unchanged"
        assert tool["result"]["isError"] is False, "the MCP read succeeds"
    finally:
        handle.uninstall_capture()


def test_stream_guarded() -> None:
    app, handle = _panel_app(stream_max_seconds=0.01)
    try:
        remote = TestClient(app, base_url="http://localhost", client=("203.0.113.9", 50000))
        assert remote.get(f"{API}/stream").status_code == 403, "a non-loopback peer is refused"
        wrong_host = _client(app).get(f"{API}/stream", headers={"host": "evil.example"})
        assert wrong_host.status_code == 403, "a foreign Host is refused"
        assert _client(app).get(f"{API}/stream").status_code == 200, "a local caller gets the stream"
    finally:
        handle.uninstall_capture()


def test_mcp_tools_list_has_only_get() -> None:
    app, handle = _panel_app()
    try:
        client = _client(app)
        listed = client.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]
        actions = {t["name"]: t["action"] for t in client.get("/sharpit/api/mcp-server").json()["tools"]}
        assert [t["name"] for t in listed if "security_log" in t["name"]] == ["get_security_logs"], "one read tool"
        assert actions.get("get_security_logs") is False, "the tool is not an action"
        reply = _call_tool(client)
        assert reply["result"]["isError"] is False, "the read tool answers"
        assert reply["result"]["structuredContent"]["auditEventsPresent"] is True, "it returns the report"
    finally:
        handle.uninstall_capture()


def test_panel_disabled_drops_events() -> None:
    app, handle = _app(panels={"security-logs": {"enabled": False}})
    try:
        assert _client(app).get("/record").status_code == 200, "recording never fails the host request"
        assert _client(app).get("/login").status_code == 401, "the host's 401 is unchanged"
        assert handle.context.capture.security_logs is None, "a disabled panel keeps no buffer"
        assert _client(app).get(API).status_code == 403, "a disabled panel's route is refused"
    finally:
        handle.uninstall_capture()


def test_report_golden_parity_with_an_anonymous_401() -> None:
    app, handle = _panel_app()
    try:
        client = _client(app)
        assert client.get("/denied").status_code == 401
        body = client.get(API).json()
        assert [event["principal"] for event in body["events"]] == [None]
        assert_parity("security-logs", "report", body)
    finally:
        handle.uninstall_capture()
