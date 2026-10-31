"""HTTP Probe API safety and response tests (BootUI ``HttpProbeServiceTests`` parity)."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.masking import MASK
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/http-probe"


@pytest.fixture
def handle() -> Any:
    handles: list[SharpitHandle] = []
    yield handles
    for installed in handles:
        installed.uninstall_capture()


def _install(app: FastAPI, handles: list[SharpitHandle], **kwargs: Any) -> SharpitHandle:
    result = install(app, enabled="ON", show_banner=False, **kwargs)
    handles.append(result)
    return result


def _client(app: Any, peer=LOCAL) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=peer, raise_server_exceptions=False)


def _probe(client: TestClient, path: str, **extra: Any):
    return client.post(API, json={"method": "GET", "path": path, **extra})


@pytest.mark.parametrize(
    "path",
    [
        "/sharpit/api/panels",
        "/sharpit%2Fapi/panels",
        "/%73harpit/api/panels",
        "//sharpit/api/panels",
    ],
)
def test_probe_cannot_reach_sharpit(path: str, handle: list[SharpitHandle]):
    app = FastAPI()
    _install(app, handle)
    with _client(app) as client:
        response = _probe(client, path)
    assert response.status_code in (400, 403)
    assert response.status_code != 200


def test_probe_tag_bypassing_validation_is_denied_by_guard(handle: list[SharpitHandle]):
    app = FastAPI()
    installed = _install(app, handle)
    from sharpit.engine.probe import ProbeRequest, run_probe

    result = asyncio.run(
        run_probe(
            app,
            ProbeRequest("GET", "/sharpit/api/panels", "", {}),
            {"headers": [(b"host", b"localhost")], "state": {}, "client": LOCAL},
            "",
            installed.context.masker,
        )
    )
    assert result["status"] == 403
    assert result["error"] is None
    assert result["body"] == '{"error":"sharpit refused an internal probe request."}'


def test_probe_under_real_root_path_cannot_reach_sharpit(handle: list[SharpitHandle]):
    app = FastAPI()
    _install(app, handle)
    with TestClient(app, base_url="http://localhost", client=LOCAL, root_path="/app") as client:
        response = client.post("/app/sharpit/api/http-probe", json={"method": "GET", "path": "/app/sharpit/api/panels"})
    assert response.status_code == 400
    assert response.json() == {"error": "HTTP Probe cannot target sharpit itself"}


def test_client_disconnect_keeps_probe_slot_until_sync_host_returns(handle: list[SharpitHandle]):
    app = FastAPI()
    entered, release = threading.Event(), threading.Event()

    @app.get("/slow")
    def slow():
        entered.set()
        release.wait()
        return {"ok": True}

    installed = _install(app, handle)

    async def scenario():
        body = b'{"method":"GET","path":"/slow"}'
        sent_request = False

        async def receive():
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()

        async def send(_message):
            return None

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": API,
            "raw_path": API.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"localhost"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
            "client": LOCAL,
            "server": ("localhost", 80),
            "state": {},
        }
        pending = asyncio.create_task(app(scope, receive, send))
        assert await asyncio.to_thread(entered.wait, 2)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

        slots = installed.context.peek("probe_slots")
        assert slots is not None and slots.count == 1
        release.set()
        for _ in range(100):
            if slots.count == 0:
                break
            await asyncio.sleep(0.01)
        assert slots.count == 0

    try:
        asyncio.run(scenario())
    finally:
        release.set()


def test_probe_opens_no_socket(no_side_effects: SideEffectGuard, handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/local")
    def local():
        return {"ok": True}

    _install(app, handle)
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop creates a self-pipe socketpair.
    with _client(app) as client:
        no_side_effects.block_network()
        response = _probe(client, "/local")
    assert response.status_code == 200
    assert no_side_effects.violations == []


def test_caller_client_copied(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/peer")
    def peer(request: Request):
        return {"client": request.client.host}

    _install(app, handle, allow_non_localhost=True, authentication_token="probe-token")
    with _client(app, ("10.0.0.5", 50000)) as client:
        response = client.post(
            API, json={"method": "GET", "path": "/peer"}, headers={"Authorization": "Bearer probe-token"}
        )
    assert response.status_code == 200
    assert response.json()["body"] == '{"client":"10.0.0.5"}'


# ported: HttpProbeServiceTests.oversizedBodyIsRejectedEvenForAMethodThatCannotCarryOne
def test_get_probe_does_not_send_request_body(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/request-body")
    async def request_body(request: Request):
        return {"body": (await request.body()).decode()}

    _install(app, handle)
    with _client(app) as client:
        result = _probe(client, "/request-body", body="ignored").json()
    assert result["body"] == '{"body":""}'


# ported: HttpProbeServiceTests.postBodySentToDownstreamServer; HttpProbeResponse DTO shape
def test_post_probe_sends_request_body_and_response_shape_matches_bootui(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.post("/request-body")
    async def request_body(request: Request):
        return {"body": (await request.body()).decode()}

    _install(app, handle)
    with _client(app) as client:
        result = client.post(API, json={"method": "POST", "path": "/request-body", "body": "payload"}).json()
    assert set(result) == {"status", "statusText", "headers", "body", "durationMs", "error", "truncated"}
    assert result["body"] == '{"body":"payload"}'


# ported: HttpProbeResponse
def test_shape_keys_match_bootui(handle: list[SharpitHandle]):
    app = FastAPI()
    _install(app, handle)
    with _client(app) as client:
        result = _probe(client, "/missing").json()
    assert set(result) == {"status", "statusText", "headers", "body", "durationMs", "error", "truncated"}


def test_host_reaches_trusted_host_middleware(handle: list[SharpitHandle]):
    app = FastAPI(middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=["localhost"])])

    @app.get("/host")
    def host(request: Request):
        return {"host": request.headers["host"]}

    _install(app, handle)
    with _client(app) as client:
        response = _probe(client, "/host")
    assert response.status_code == 200
    assert response.json()["status"] == 200
    assert "localhost" in response.json()["body"]


def test_lifespan_state_visible(handle: list[SharpitHandle]):
    @asynccontextmanager
    async def lifespan(_app):
        yield {"db": "lifespan-visible"}

    app = FastAPI(lifespan=lifespan)

    @app.get("/state")
    def state(request: Request):
        return {"value": request.state.db}

    _install(app, handle)
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        response = _probe(client, "/state")
    assert response.status_code == 200
    assert "lifespan-visible" in response.json()["body"]


def test_scope_root_path_and_raw_path(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/inspect")
    def inspect(request: Request):
        return {
            "root_path": request.scope["root_path"],
            "path": request.scope["path"],
            "raw_path": request.scope["raw_path"].decode(),
        }

    _install(app, handle)
    with TestClient(app, base_url="http://localhost", client=LOCAL, root_path="/app") as client:
        result = client.post("/app/sharpit/api/http-probe", json={"method": "GET", "path": "/inspect"}).json()
    assert result.get("status") == 200, result
    assert result["body"] == '{"root_path":"/app","path":"/app/inspect","raw_path":"/app/inspect"}'


# ported: HttpProbeServiceTests.responseOverLimitIsTruncatedAndFlagSet
def test_streaming_endpoint_truncated_at_1mib(handle: list[SharpitHandle]):
    app = FastAPI()

    async def stream():
        yield b"x" * (1024 * 1024 + 10)

    async def large():
        return StreamingResponse(stream())

    app.add_api_route("/large", large, response_class=StreamingResponse)
    _install(app, handle)
    with _client(app) as client:
        result = _probe(client, "/large").json()
    assert result["truncated"] is True
    assert len(result["body"]) == 1024 * 1024


def test_truncated_utf8_body_keeps_text_and_replaces_partial_character(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/large-text")
    def large_text():
        return PlainTextResponse("€" * 400_000)

    _install(app, handle)
    with _client(app) as client:
        result = _probe(client, "/large-text").json()
    assert result["truncated"] is True
    assert result["body"].startswith("€")
    assert " bytes, text/plain" not in result["body"]
    assert len(result["body"]) >= (1 << 20) // 3 - 2


def test_timeout_message_and_timed_out_probe_holds_slot(handle: list[SharpitHandle]):
    app = FastAPI()
    installed = _install(app, handle)
    from sharpit.engine import probe as probe_engine

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        slots = probe_engine.ProbeSlots()
        assert slots.acquire()

        async def host_app(scope, receive, send):
            del scope, receive, send
            entered.set()
            await release.wait()

        request = probe_engine.ProbeRequest("GET", "/slow", "", {})
        pending = asyncio.create_task(
            probe_engine.run_probe(
                host_app,
                request,
                {"headers": [], "state": {}},
                "",
                installed.context.masker,
                timeout=0.05,
                on_complete=slots.release,
            )
        )
        await entered.wait()
        result = await pending
        assert result["error"] == "HTTP Probe timed out after 0.05s"
        assert slots.count == 1
        release.set()
        for _ in range(100):
            if slots.count == 0:
                break
            await asyncio.sleep(0.01)
        assert slots.count == 0

    asyncio.run(scenario())


def test_async_probe_timeout_cancels_task_and_releases_slot(handle: list[SharpitHandle]):
    app = FastAPI()
    installed = _install(app, handle)
    from sharpit.engine import probe as probe_engine

    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        slots = probe_engine.ProbeSlots()
        assert slots.acquire()

        async def host_app(scope, receive, send):
            del scope, receive, send
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        result = await probe_engine.run_probe(
            host_app,
            probe_engine.ProbeRequest("GET", "/slow", "", {}),
            {"headers": [], "state": {}},
            "",
            installed.context.masker,
            timeout=0.01,
            on_complete=slots.release,
        )
        assert result["error"] == "HTTP Probe timed out after 0.01s"
        assert entered.is_set()
        await asyncio.wait_for(cancelled.wait(), timeout=0.1)
        assert cancelled.is_set()
        assert await asyncio.to_thread(_wait_for, lambda: slots.count == 0)
        assert slots.count == 0

    asyncio.run(scenario())


def test_sync_probe_timeout_keeps_slot_until_worker_returns(
    handle: list[SharpitHandle], monkeypatch: pytest.MonkeyPatch
):
    entered, release, response_ready, allow_close = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    app = FastAPI()

    @app.get("/sync-slow")
    def sync_slow():
        entered.set()
        release.wait(3)
        return {"done": True}

    installed = _install(app, handle)
    from sharpit.engine import probe as probe_engine

    monkeypatch.setattr(probe_engine, "PROBE_TIMEOUT", 0.05)
    slots = installed.context.lazy("probe_slots", probe_engine.ProbeSlots)
    result: list[dict[str, Any]] = []

    def invoke_probe():
        with _client(app) as client:
            result.append(_probe(client, "/sync-slow").json())
            response_ready.set()
            allow_close.wait(3)

    caller = threading.Thread(target=invoke_probe)
    caller.start()
    try:
        assert entered.wait(1)
        assert response_ready.wait(1)
        assert result[0]["error"] == "HTTP Probe timed out after 0.05s"
        assert slots.count == 1
        assert all(slots.acquire() for _ in range(3))
        with _client(app) as client:
            assert _probe(client, "/sync-slow").status_code == 409
        for _ in range(3):
            slots.release()
        release.set()
        assert _wait_for(lambda: slots.count == 0)
    finally:
        release.set()
        allow_close.set()
    caller.join(1)
    assert not caller.is_alive()


def _wait_for(check):
    import time

    until = time.monotonic() + 1
    while time.monotonic() < until:
        if check():
            return True
        time.sleep(0.01)
    return check()


def test_fifth_concurrent_probe_409(handle: list[SharpitHandle]):
    entered, release = threading.Event(), threading.Event()
    app = FastAPI()

    @app.get("/wait")
    def wait():
        entered.set()
        release.wait(2)
        return {"ok": True}

    installed = _install(app, handle)
    from sharpit.engine import probe as probe_engine

    slots = installed.context.lazy("probe_slots", probe_engine.ProbeSlots)
    clients = [_client(app) for _ in range(5)]
    threads = [threading.Thread(target=lambda c=client: _probe(c, "/wait")) for client in clients[:4]]
    for thread in threads:
        thread.start()
    assert entered.wait(1)
    assert _wait_for(lambda: slots.count == 4)
    fifth = _probe(clients[4], "/wait")
    release.set()
    for thread in threads:
        thread.join(2)
    assert fifth.status_code == 409


def test_probe_row_in_http_exchanges_and_real_request_header_stripped(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/echo-header")
    def echo_header(request: Request):
        return {"probe": request.headers.get("x-sharpit-probe")}

    installed = _install(app, handle)
    with _client(app) as client:
        client.get("/echo-header", headers={"X-Sharpit-Probe": "forged"})
        result = _probe(client, "/echo-header").json()
        rows = client.get("/sharpit/api/http-exchanges").json()["exchanges"]
    assert '"probe":"1"' in result["body"]
    assert sum(row["path"] == "/echo-header" for row in rows) >= 2
    assert installed.context.capture.exchanges is not None
    echo_rows = [row for row in rows if row["path"] == "/echo-header"]
    assert len(echo_rows) == 2
    assert any(not any(h["name"] == "x-sharpit-probe" for h in row["requestHeaders"]) for row in echo_rows)
    assert any(any(h["name"] == "x-sharpit-probe" for h in row["requestHeaders"]) for row in echo_rows)
    assert "forged" not in str(echo_rows)


# ported: HttpProbeServiceTests.onlyAllowedResponseHeadersPassedThrough, locationHeaderPassedThrough
def test_only_allow_listed_headers_returned_and_location_token_masked(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/headers")
    def headers():
        return Response(
            "ok",
            headers={
                "Set-Cookie": "session=secret",
                "Authorization": "Bearer secret",
                "X-Custom": "no",
                "Location": "/next?token=abc",
                "Content-Type": "text/plain",
            },
        )

    _install(app, handle)
    with _client(app) as client:
        result = _probe(client, "/headers").json()
    assert result["headers"] == {"content-type": "text/plain", "content-length": "2", "location": f"/next?token={MASK}"}


def test_probe_location_header_is_capped_by_utf8_bytes(handle: list[SharpitHandle]):
    installed = _install(FastAPI(), handle)
    from sharpit.engine.probe import ProbeRequest, run_probe

    async def host_app(scope, receive, send):
        del scope, receive
        location = "/" + "€" * 3000
        await send(
            {
                "type": "http.response.start",
                "status": 302,
                "headers": [(b"location", location.encode("utf-8"))],
            }
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    result = asyncio.run(
        run_probe(
            host_app,
            ProbeRequest("GET", "/", "", {}),
            {"headers": [], "state": {}},
            "",
            installed.context.masker,
        )
    )
    assert len(result["headers"]["location"].encode("utf-8")) <= 8192


def test_json_and_text_bodies_are_masked_and_binary_is_summarized(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/json")
    def json_body():
        return JSONResponse({"password": "hunter2", "ok": True})

    @app.get("/text")
    def text_body():
        return PlainTextResponse("access_token=secret-token")

    @app.get("/binary")
    def binary():
        return Response(b"\x00\x01\xff", media_type="application/octet-stream")

    _install(app, handle)
    with _client(app) as client:
        json_result, text_result, binary_result = (_probe(client, p).json() for p in ("/json", "/text", "/binary"))
    assert '"password":"******"' in json_result["body"]
    assert '"ok":true' in json_result["body"]
    assert "secret-token" not in text_result["body"]
    assert binary_result["body"] == "<3 bytes, application/octet-stream>"


def test_full_exposure_returns_raw_body(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/secret")
    def secret():
        return {"password": "hunter2"}

    _install(app, handle, expose_values="FULL")
    with _client(app) as client:
        result = _probe(client, "/secret").json()
    assert '"password":"hunter2"' in result["body"]


def test_app_exception_returns_masked_500(handle: list[SharpitHandle]):
    app = FastAPI()

    @app.get("/fail")
    def fail():
        raise RuntimeError("password=hunter2")

    _install(app, handle)
    with _client(app) as client:
        result = _probe(client, "/fail").json()
        groups = client.get("/sharpit/api/exceptions").json()["groups"]
    assert result["status"] == 500
    assert "hunter2" not in result["error"]
    assert groups


def test_probe_read_only_403(handle: list[SharpitHandle]):
    app = FastAPI()
    _install(app, handle, read_only=True)
    with _client(app) as client:
        response = _probe(client, "/")
    assert response.status_code == 403


def test_status_text_fallback_and_empty_response_error_match_bootui(handle: list[SharpitHandle]):
    installed = _install(FastAPI(), handle)
    from sharpit.engine.probe import ProbeRequest, run_probe

    async def status_response(scope, receive, send):
        del scope, receive
        await send({"type": "http.response.start", "status": 302, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def empty_response(scope, receive, send):
        del scope, receive, send

    async def invoke(host_app):
        return await run_probe(
            host_app,
            ProbeRequest("GET", "/", "", {}),
            {"headers": [], "state": {}},
            "",
            installed.context.masker,
        )

    redirect = asyncio.run(invoke(status_response))
    empty = asyncio.run(invoke(empty_response))
    assert redirect["statusText"] == "HTTP 302"
    assert empty["status"] == 0
    assert empty["statusText"] == "Error"
    assert empty["error"]
