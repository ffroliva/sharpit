from __future__ import annotations

import pytest
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.testclient import TestClient
from starlette.responses import Response

from fastapi import FastAPI, HTTPException
from sharpit import install
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.fastapi.capture import wiring_of
from sharpit.fastapi.request_id_header import with_request_id_header
from sharpit.settings import PanelSettings, load_settings

HEADER = "X-Sharpit-Request-Id"
LOCAL = ("127.0.0.1", 50000)


def _app(**settings: object) -> tuple[FastAPI, object]:
    app = FastAPI()
    app.get("/ok")(lambda: {"ok": True})
    handle = install(app, enabled="ON", show_banner=False, **settings)
    return app, handle


def test_request_id_header_matches_exchange_and_request_profile() -> None:
    # ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    app, _handle = _app()
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
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
    # ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    trusted, _ = _app()
    assert HEADER in TestClient(trusted, client=LOCAL).get("/ok").headers

    monkeypatch.setenv("SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER", "false")
    disabled_property, _ = _app()
    monkeypatch.delenv("SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER")
    disabled_panel, _ = _app(panels={"http-exchanges": {"enabled": False}})
    live_panel, live_handle = _app()
    live_panel_client = TestClient(live_panel, client=LOCAL)
    assert HEADER in live_panel_client.get("/ok").headers
    assert isinstance(live_handle.context.settings.panels, dict)
    live_handle.context.settings.panels["http-exchanges"] = PanelSettings(enabled=False)

    assert HEADER not in TestClient(disabled_property, client=LOCAL).get("/ok").headers
    assert HEADER not in TestClient(disabled_panel, client=LOCAL).get("/ok").headers
    assert HEADER not in live_panel_client.get("/ok").headers


def test_request_id_header_uses_guard_trust_and_rejects_forwarded_headers() -> None:
    # ported: QuarkusHttpExchangeCaptureFilterTest.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
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
    # ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
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
    error_response = client.get("/server-error")

    assert handled.status_code == 418
    assert HEADER in handled.headers
    assert error_response.status_code == 500
    assert HEADER not in error_response.headers


def test_request_id_header_ids_are_generated_internally() -> None:
    app, _ = _app()
    response = TestClient(app, client=LOCAL).get("/ok", headers={HEADER: "inbound-value", "X-Request-ID": "caller"})

    assert HEADER in response.headers
    assert response.headers[HEADER] != "inbound-value"
    assert response.headers[HEADER] != "caller"


def test_request_id_header_invalid_property_fails_closed_with_warning() -> None:
    # ported: QuarkusHttpExchangeCaptureFilterTest.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    settings = load_settings({}, {"SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER": "invalid"})

    assert hasattr(settings, "http_exchanges_expose_request_id_header")
    assert settings.http_exchanges_expose_request_id_header is False
    assert any("Ignoring invalid SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER" in w for w in settings.warnings)


def test_request_id_header_failure_is_reported_without_changing_response(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: QuarkusHttpExchangeCaptureFilterTest.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    import sharpit.fastapi.request_id_header as request_id_header

    app, handle = _app()
    wiring = wiring_of(handle.context)
    assert wiring is not None
    failures: list[tuple[str, BaseException]] = []
    monkeypatch.setattr(wiring, "hook_failed", lambda hook, exc: failures.append((hook, exc)))
    monkeypatch.setattr(request_id_header.guard, "is_trusted_source", lambda *_: (_ for _ in ()).throw(RuntimeError()))

    response = TestClient(app, client=LOCAL).get("/ok")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert HEADER not in response.headers
    assert [hook for hook, _ in failures] == ["request id response header"]


def test_request_id_header_uses_explicit_info_when_request_context_is_unset_and_copies_headers() -> None:
    # ported: QuarkusHttpExchangeCaptureFilterTest.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    _app_instance, handle = _app()
    original_headers = [(b"x-app", b"kept")]
    message = {"type": "http.response.start", "status": 200, "headers": original_headers}
    scope = {"type": "http", "method": "GET", "client": LOCAL, "headers": [], "scheme": "http"}
    info = RequestInfo("request-id", handle.context.context_id, "GET", "/ok", None, 0, None)
    assert REQUEST.get() is None
    decorated = with_request_id_header(handle.context, scope, message, info)

    assert dict(decorated["headers"]).get(b"x-sharpit-request-id") == b"request-id"
    assert original_headers == [(b"x-app", b"kept")]
    assert decorated["headers"] is not original_headers


def test_request_id_header_uses_capture_info_without_request_context(monkeypatch: pytest.MonkeyPatch) -> None:
    import sharpit.fastapi.request_id_header as request_id_header

    class MissingRequestContext:
        @staticmethod
        def get() -> None:
            return None

    monkeypatch.setattr(request_id_header, "REQUEST", MissingRequestContext(), raising=False)
    app, _ = _app()

    client = TestClient(app, base_url="http://localhost", client=LOCAL)
    response = client.get("/ok")

    assert HEADER in response.headers
    exchange = client.get("/sharpit/api/http-exchanges").json()["exchanges"][0]
    assert response.headers[HEADER] == exchange["requestId"]


def test_request_id_header_preserves_one_shot_application_headers() -> None:
    app = FastAPI()

    @app.get("/generator")
    def generator_response() -> Response:
        response = Response("ok")
        response.raw_headers = iter([(b"x-app", b"kept")])  # type: ignore[assignment]
        return response

    install(app, enabled="ON", show_banner=False)

    response = TestClient(app, client=LOCAL).get("/generator")

    assert response.headers.get("x-app") == "kept"


# ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
def test_request_id_header_obeys_container_gateway_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import sharpit.fastapi.request_id_header as request_id_header

    gateway = "172.18.0.1"
    monkeypatch.setattr(request_id_header.guard, "detect_container_gateway", lambda: gateway)
    automatic, _ = _app(trust_container_gateway="AUTO")
    disabled, _ = _app(trust_container_gateway="OFF")

    assert HEADER in TestClient(automatic, client=(gateway, 50000)).get("/ok").headers
    assert HEADER not in TestClient(disabled, client=(gateway, 50000)).get("/ok").headers
