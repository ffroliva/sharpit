from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.testclient import TestClient
from starlette.responses import Response

from sharpit import install
from sharpit.settings import load_settings
from sharpit.fastapi.capture import wiring_of

HEADER = "X-Sharpit-Request-Id"
LOCAL = ("127.0.0.1", 50000)


def _app(**settings: object) -> tuple[FastAPI, object]:
    app = FastAPI()
    app.get("/ok")(lambda: {"ok": True})
    handle = install(app, enabled="ON", show_banner=False, **settings)
    return app, handle


def test_request_id_header_matches_exchange_and_request_profile() -> None:
    # ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues
    app, _handle = _app()
    with TestClient(app, client=LOCAL) as client:
        response = client.get("/ok")
        assert HEADER in response.headers
        request_id = response.headers[HEADER]
        assert response.headers.get_list(HEADER) == [request_id]
        exchange = client.get("/sharpit/api/http-exchanges").json()["exchanges"][0]
        profile = client.get(f"/sharpit/api/activity/request/{request_id}").json()

    assert request_id == exchange["requestId"]
    assert profile["available"] is True
    assert profile["request"]["requestId"] == request_id


def test_request_id_header_requires_property_panel_and_trusted_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues
    trusted, _ = _app()
    assert HEADER in TestClient(trusted, client=LOCAL).get("/ok").headers

    monkeypatch.setenv("SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER", "false")
    disabled_property, _ = _app()
    monkeypatch.delenv("SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER")
    disabled_panel, _ = _app(panels={"http-exchanges": {"enabled": False}})

    assert HEADER not in TestClient(disabled_property, client=LOCAL).get("/ok").headers
    assert HEADER not in TestClient(disabled_panel, client=LOCAL).get("/ok").headers


def test_request_id_header_uses_guard_trust_and_rejects_forwarded_headers() -> None:
    # ported: QuarkusHttpExchangeCaptureFilterTest.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues
    app, _ = _app(trusted_proxies=("10.0.0.0/8",), allow_non_localhost=True)

    assert HEADER in TestClient(app, client=LOCAL).get("/ok").headers
    assert HEADER not in TestClient(app, client=("203.0.113.9", 50000)).get("/ok").headers
    assert HEADER not in TestClient(app, client=LOCAL).get("/ok", headers={"X-Forwarded-For": "127.0.0.1"}).headers
    assert HEADER not in TestClient(app, client=("10.1.2.3", 50000)).get("/ok").headers


def test_request_id_header_preserves_application_value_case_insensitively() -> None:
    app = FastAPI()
    app.get("/ok")(lambda: {"ok": True})
    app.get("/app-header")(lambda: Response(headers={"x-sHaRpIt-request-id": "application"}))
    install(app, enabled="ON", show_banner=False)

    client = TestClient(app, client=LOCAL)
    automatic = client.get("/ok")
    response = client.get("/app-header")

    assert HEADER in automatic.headers
    assert response.headers.get_list(HEADER) == ["application"]


def test_request_id_header_is_absent_from_sharpit_inactive_and_suspended_requests() -> None:
    # ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues
    app, handle = _app()
    active = TestClient(app, client=LOCAL).get("/ok")
    hook = next(h for h in handle.context.capture.hooks.hooks() if h.name == "capture-middleware")
    hook.suspend()
    suspended = TestClient(app, client=LOCAL).get("/ok")
    wiring = wiring_of(handle.context)
    assert wiring is not None
    wiring.detached = True
    detached = TestClient(app, client=LOCAL).get("/ok")

    inactive_app = FastAPI()
    inactive_app.get("/ok")(lambda: {"ok": True})
    install(inactive_app, enabled="OFF", show_banner=False)
    inactive = TestClient(inactive_app, client=LOCAL).get("/ok")

    sharpit = TestClient(app, client=LOCAL).get("/sharpit/api/panels")

    assert HEADER in active.headers
    assert HEADER not in suspended.headers
    assert HEADER not in detached.headers
    assert HEADER not in inactive.headers
    assert HEADER not in sharpit.headers


def test_request_id_header_requires_a_recorded_exchange() -> None:
    app, handle = _app()
    active = TestClient(app, client=LOCAL).get("/ok")
    handle.context.capture.exchanges = None

    response = TestClient(app, client=LOCAL).get("/ok")

    assert HEADER in active.headers
    assert HEADER not in response.headers


def test_request_id_header_covers_stream_redirect_and_mounted_app() -> None:
    app = FastAPI()
    app.get("/stream")(lambda: StreamingResponse(iter((b"a", b"b"))))
    app.get("/redirect")(lambda: RedirectResponse("/mounted/ok"))
    mounted = FastAPI()
    mounted.get("/ok")(lambda: {"ok": True})
    app.mount("/mounted", mounted)
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, client=LOCAL)

    streamed = client.get("/stream")
    redirected = client.get("/redirect", follow_redirects=False)
    mounted_response = client.get("/mounted/ok")

    assert streamed.content == b"ab"
    assert HEADER in streamed.headers
    assert redirected.status_code == 307
    assert HEADER in redirected.headers
    assert HEADER in mounted_response.headers


def test_request_id_header_is_present_on_handled_errors_and_absent_on_server_500() -> None:
    app = FastAPI()
    app.get("/handled-error")(lambda: (_ for _ in ()).throw(HTTPException(418)))

    @app.get("/server-error")
    def server_error() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("boom")

    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, client=LOCAL, raise_server_exceptions=False)

    handled = client.get("/handled-error")
    server_error = client.get("/server-error")

    assert handled.status_code == 418
    assert HEADER in handled.headers
    assert server_error.status_code == 500
    assert HEADER not in server_error.headers


def test_request_id_header_ids_are_generated_internally() -> None:
    app, _ = _app()
    response = TestClient(app, client=LOCAL).get(
        "/ok", headers={HEADER: "inbound-value", "X-Request-ID": "caller"}
    )

    assert HEADER in response.headers
    assert response.headers[HEADER] != "inbound-value"
    assert response.headers[HEADER] != "caller"


def test_request_id_header_invalid_property_fails_closed_with_warning() -> None:
    settings = load_settings({}, {"SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER": "invalid"})

    assert hasattr(settings, "http_exchanges_expose_request_id_header")
    assert settings.http_exchanges_expose_request_id_header is False
    assert any("Ignoring invalid SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER" in w for w in settings.warnings)
