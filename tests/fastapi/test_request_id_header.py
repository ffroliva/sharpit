from __future__ import annotations

import importlib
import importlib.util

import pytest
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.testclient import TestClient
from starlette.responses import Response

from fastapi import FastAPI, HTTPException, WebSocket
from sharpit import install
from sharpit.engine import guard
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.fastapi.capture import wiring_of
from sharpit.settings import load_settings

HEADER = "X-Sharpit-Request-Id"
LOCAL = ("127.0.0.1", 50000)


def _app(**settings: object) -> tuple[FastAPI, object]:
    app = FastAPI()
    app.get("/ok")(lambda: {"ok": True})
    handle = install(app, enabled="ON", show_banner=False, **settings)
    return app, handle


def test_request_id_header_matches_exchange_and_request_profile() -> None:
    # ported: RequestCorrelationFilterTests.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    app, handle = _app()
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
    monkeypatch.setenv("SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER", "false")
    disabled_property, _ = _app()
    monkeypatch.delenv("SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER")
    disabled_panel, _ = _app(panels={"http-exchanges": {"enabled": False}})
    trusted, _ = _app()
    remote, _ = _app(allow_non_localhost=True)

    assert HEADER in TestClient(trusted, client=LOCAL).get("/ok").headers
    assert HEADER not in TestClient(disabled_property, client=LOCAL).get("/ok").headers
    assert HEADER not in TestClient(disabled_panel, client=LOCAL).get("/ok").headers
    assert HEADER not in TestClient(remote, client=("203.0.113.9", 50000)).get("/ok").headers

    forwarded = TestClient(trusted, client=LOCAL).get("/ok", headers={"X-Forwarded-For": "127.0.0.1"})
    assert HEADER not in forwarded.headers


def test_request_id_header_skips_disabled_per_response_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER", "false")
    app, _ = _app()

    def unexpected_header_check(*_args: object) -> object:
        pytest.fail("request-id header check ran while disabled")

    monkeypatch.setattr("sharpit.fastapi.capture.with_request_id_header", unexpected_header_check)

    response = TestClient(app, client=LOCAL).get("/ok")

    assert HEADER not in response.headers


def test_request_id_header_matches_guard_after_outer_client_rewrite() -> None:
    # ported: QuarkusHttpExchangeCaptureFilterTest.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    app, handle = _app()
    decisions: list[bool] = []

    class RewriteClient:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope["client"] = LOCAL
                await self.inner(scope, receive, send)
                headers = {name.decode().lower(): "" for name, _ in scope["headers"]}
                facts = guard.RequestFacts("GET", scope["client"][0], headers, None)
                decisions.append(guard.is_trusted_source(facts, handle.context.settings, None))
                return
            await self.inner(scope, receive, send)

    wrapped = RewriteClient(app)
    response = TestClient(wrapped, client=("203.0.113.9", 50000)).get("/ok")

    assert decisions == [True]
    assert (HEADER in response.headers) is decisions[0]


def test_request_id_header_preserves_duplicate_application_headers() -> None:
    app = FastAPI()
    app.get("/ok")(lambda: {"ok": True})

    @app.get("/duplicates")
    def duplicates() -> Response:
        response = Response("ok")
        response.raw_headers.extend([(b"x-sharpit-request-id", b"first"), (b"X-Sharpit-Request-Id", b"second")])
        return response

    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, client=LOCAL)
    response = client.get("/duplicates")
    generated = client.get("/ok")

    assert response.headers.get_list(HEADER) == ["first", "second"]
    assert HEADER in generated.headers


def test_request_id_header_does_not_change_websocket_or_lifespan_scopes() -> None:
    app = FastAPI()
    app.get("/ok")(lambda: {"ok": True})
    observed: list[tuple[str, list[tuple[bytes, bytes]]]] = []

    @app.websocket("/ws")
    async def websocket(websocket: WebSocket):
        await websocket.accept(headers=[(b"x-app", b"ws")])
        await websocket.close()

    install(app, enabled="ON", show_banner=False)

    class ObserveProtocols:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            async def observe(message):
                if message["type"] in ("websocket.accept", "lifespan.startup.complete", "lifespan.shutdown.complete"):
                    observed.append((message["type"], list(message.get("headers", []))))
                await send(message)

            await self.inner(scope, receive, observe)

    with TestClient(ObserveProtocols(app), client=LOCAL) as client:
        response = client.get("/ok")
        with client.websocket_connect("/ws"):
            pass

    assert HEADER in response.headers
    assert observed == [
        ("lifespan.startup.complete", []),
        ("websocket.accept", [(b"x-app", b"ws")]),
        ("lifespan.shutdown.complete", []),
    ]


def test_request_id_header_preserves_application_value_case_insensitively() -> None:
    app = FastAPI()
    app.get("/ok")(lambda: Response(headers={"x-sHaRpIt-request-id": "application"}))
    install(app, enabled="ON", show_banner=False)
    response = TestClient(app, client=LOCAL).get("/ok")

    assert response.headers.get_list(HEADER) == ["application"]


def test_request_id_header_is_absent_from_inactive_and_sharpit_routes() -> None:
    app, handle = _app()
    active_client = TestClient(app, client=LOCAL)
    active = active_client.get("/ok")
    hook = next(item for item in handle.context.capture.hooks.hooks() if item.name == "capture-middleware")
    hook.suspend()
    suspended = active_client.get("/ok")
    hook.resume()
    wiring = wiring_of(handle.context)
    assert wiring is not None
    wiring.detached = True
    detached = active_client.get("/ok")
    sharpit = TestClient(app, client=LOCAL).get("/sharpit/api/panels")
    inactive_app = FastAPI()
    inactive_app.get("/ok")(lambda: {"ok": True})
    install(inactive_app, enabled="OFF", show_banner=False)
    inactive = TestClient(inactive_app, client=LOCAL).get("/ok")

    assert HEADER not in sharpit.headers
    assert HEADER not in inactive.headers
    assert HEADER in active.headers
    assert HEADER not in suspended.headers
    assert HEADER not in detached.headers


def test_request_id_header_invalid_property_fails_closed_with_warning() -> None:
    # ported: QuarkusHttpExchangeCaptureFilterTest.exposesRequestIdHeaderOnlyOnTrustedApplicationResponsesWhenEnabledAndPreservesApplicationValues  # noqa: E501
    settings = load_settings({}, {"SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER": "invalid"})

    assert getattr(settings, "http_exchanges_expose_request_id_header", None) is False
    assert any(
        "Ignoring invalid SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER" in warning for warning in settings.warnings
    )


def test_request_id_header_covers_stream_redirect_and_errors() -> None:
    app = FastAPI()
    app.get("/stream")(lambda: StreamingResponse(iter((b"a", b"b"))))
    app.get("/redirect")(lambda: RedirectResponse("/stream"))
    app.get("/handled-error")(lambda: (_ for _ in ()).throw(HTTPException(418)))

    @app.get("/server-error")
    def server_error() -> None:
        raise RuntimeError("boom")

    mounted = FastAPI()
    mounted.get("/ok")(lambda: {"ok": True})
    app.mount("/mounted", mounted)
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, client=LOCAL, raise_server_exceptions=False)
    streamed = client.get("/stream")
    redirected = client.get("/redirect", follow_redirects=False)
    handled = client.get("/handled-error")
    server_error_response = client.get("/server-error")
    mounted_response = client.get("/mounted/ok")

    assert streamed.content == b"ab"
    assert HEADER in streamed.headers
    assert redirected.status_code == 307
    assert HEADER in redirected.headers
    assert handled.status_code == 418
    assert HEADER in handled.headers
    assert server_error_response.status_code == 500
    assert HEADER not in server_error_response.headers
    assert HEADER in mounted_response.headers


def test_request_id_header_requires_recorded_exchange_and_ignores_inbound_id() -> None:
    app, handle = _app()
    client = TestClient(app, client=LOCAL)
    recorded = client.get("/ok")
    handle.context.capture.exchanges = None
    unavailable = client.get("/ok", headers={HEADER: "caller", "X-Request-ID": "caller"})

    assert HEADER in recorded.headers
    assert HEADER not in unavailable.headers
    assert unavailable.headers.get(HEADER) != "caller"


def test_request_id_header_failure_does_not_change_host_response(monkeypatch: pytest.MonkeyPatch) -> None:
    app, handle = _app()
    wiring = wiring_of(handle.context)
    assert wiring is not None
    failures: list[str] = []
    monkeypatch.setattr(wiring, "hook_failed", lambda hook, _exc: failures.append(hook))
    monkeypatch.setattr(guard, "is_trusted_source", lambda *_: (_ for _ in ()).throw(RuntimeError()))

    response = TestClient(app, client=LOCAL).get("/ok")

    assert response.status_code == 200
    assert HEADER not in response.headers
    assert failures == ["request id response header"]


def test_request_id_header_uses_explicit_capture_info_and_copies_headers() -> None:
    assert importlib.util.find_spec("sharpit.fastapi.request_id_header") is not None
    request_id_header = importlib.import_module("sharpit.fastapi.request_id_header")
    _app_instance, handle = _app()
    original_headers = [(b"x-app", b"kept")]
    message = {"type": "http.response.start", "status": 200, "headers": original_headers}
    scope = {"type": "http", "method": "GET", "client": LOCAL, "headers": [], "scheme": "http"}
    info = RequestInfo("request-id", handle.context.context_id, "GET", "/ok", None, 0, None)
    assert REQUEST.get() is None
    decorated = request_id_header.with_request_id_header(handle.context, scope, message, info)

    assert dict(decorated["headers"]).get(b"x-sharpit-request-id") == b"request-id"
    assert original_headers == [(b"x-app", b"kept")]
    assert decorated["headers"] is not original_headers


def test_request_id_header_uses_capture_info_without_request_context(monkeypatch: pytest.MonkeyPatch) -> None:
    assert importlib.util.find_spec("sharpit.fastapi.request_id_header") is not None
    request_id_header = importlib.import_module("sharpit.fastapi.request_id_header")

    class MissingRequestContext:
        @staticmethod
        def get() -> None:
            return None

    monkeypatch.setattr(request_id_header, "REQUEST", MissingRequestContext(), raising=False)
    app, _ = _app()
    client = TestClient(app, base_url="http://localhost", client=LOCAL)
    response = client.get("/ok")
    exchange = client.get("/sharpit/api/http-exchanges").json()["exchanges"][0]

    assert HEADER in response.headers
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


def test_request_id_header_obeys_container_gateway_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = "172.18.0.1"
    monkeypatch.setattr(guard, "detect_container_gateway", lambda: gateway)
    automatic, _ = _app(trust_container_gateway="AUTO")
    disabled, _ = _app(trust_container_gateway="OFF")

    assert HEADER in TestClient(automatic, client=(gateway, 50000)).get("/ok").headers
    assert HEADER not in TestClient(disabled, client=(gateway, 50000)).get("/ok").headers
