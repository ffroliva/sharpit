from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from fastapi import FastAPI
from sharpit import install, record_security_event
from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.capture.securitylogs import (
    AUTHENTICATION_FAILURE,
    AUTHENTICATION_SUCCESS,
    AUTHORIZATION_FAILURE,
    SecurityEventBuffer,
    security_logs_report,
)
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import wiring_of

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
