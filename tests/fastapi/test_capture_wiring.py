"""``CaptureMiddleware`` and ``CaptureWiring`` (spec §6.1, §7.1, §9, §14.2).

Middleware cases call the ASGI app directly where the outcome depends on message order (disconnects, cancellation,
pathsend); the rest go through ``TestClient``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from examples.fastapi_sample.app import create_app
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from fastapi import FastAPI, Request, WebSocket
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.context import SharpitContext
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import CAPTURE_TOO_LATE, CAPTURE_TOO_LATE_REASON, CaptureMiddleware

LOCAL = ("127.0.0.1", 50000)
CAPTURE_PANELS = ("http-exchanges", "exceptions", "sql-trace", "activity")
FakeApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _handle(**options: Any) -> SharpitHandle:
    return install(FastAPI(), **{"enabled": "ON", "show_banner": False, **options})


def _buffer(handle: SharpitHandle) -> HttpExchangeBuffer:
    buffer = handle.context.capture.exchanges
    assert buffer is not None
    return buffer


def _rows(handle: SharpitHandle) -> list[dict[str, Any]]:
    return _buffer(handle).report(None, None, None, None, None)["exchanges"]


def _scope(path: str = "/x", **extra: Any) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"localhost")],
        "client": LOCAL,
        "server": ("localhost", 80),
        **extra,
    }


async def _run(ctx: SharpitContext, app: FakeApp, inbox: list[Message] | None = None, scope: Scope | None = None):
    pending = list(inbox or [{"type": "http.request", "body": b"", "more_body": False}])
    sent: list[Message] = []

    async def receive() -> Message:
        if pending:
            return pending.pop(0)
        await asyncio.Event().wait()  # like a server with nothing more to say
        raise AssertionError  # pragma: no cover

    async def send(message: Message) -> None:
        sent.append(message)

    await CaptureMiddleware(app, ctx)(scope or _scope(), receive, send)
    return sent


def _start(status: int = 200) -> Message:
    return {"type": "http.response.start", "status": status, "headers": [(b"content-type", b"text/plain")]}


# --- status rules --------------------------------------------------------------------------------------------------


def test_status_499_on_disconnect():
    handle = _handle()

    async def app(_scope: Scope, receive: Receive, _send: Send) -> None:
        await receive()  # http.disconnect: the client left before any response
        return

    asyncio.run(_run(handle.context, app, [{"type": "http.disconnect"}]))
    row = _rows(handle)[0]
    assert (row["status"], row["statusFamily"]) == (499, "4xx")
    assert _buffer(handle).get(row["id"])["error"] is False  # pyright: ignore[reportOptionalSubscript]


def test_disconnect_after_start_keeps_status():
    handle = _handle()

    async def app(_scope: Scope, receive: Receive, send: Send) -> None:
        await send(_start(200))
        await send({"type": "http.response.body", "body": b"part", "more_body": True})
        await receive()  # http.disconnect mid-stream; no final chunk ever goes out

    asyncio.run(_run(handle.context, app, [{"type": "http.disconnect"}]))
    row = _rows(handle)[0]
    assert (row["status"], row["responseSizeBytes"]) == (200, 4)
    assert _buffer(handle).get(row["id"])["error"] is True  # pyright: ignore[reportOptionalSubscript]


def test_exception_after_start_keeps_status():
    handle = _handle()

    async def app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send(_start(201))
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(_run(handle.context, app))
    row = _rows(handle)[0]
    assert row["status"] == 201
    assert _buffer(handle).get(row["id"])["error"] is True  # pyright: ignore[reportOptionalSubscript]


def test_unhandled_exception_500_and_reraised():
    handle = _handle()

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(_run(handle.context, app))
    assert _rows(handle)[0]["status"] == 500
    # through a real app: Starlette's ServerErrorMiddleware sends the 500 after us
    app = FastAPI()

    @app.get("/fail")
    def fail() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("boom")

    real = install(app, enabled="ON", show_banner=False)
    assert TestClient(app, raise_server_exceptions=False).get("/fail").status_code == 500
    assert _rows(real)[0]["status"] == 500


def test_cancelled_not_recorded():
    # spec §7.1: a cancel with no start is a 499 row; CancelledError is re-raised, never caught as an error (F2)
    handle = _handle()
    entered = asyncio.Event()

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        entered.set()
        await asyncio.Event().wait()

    async def main() -> None:
        task = asyncio.create_task(_run(handle.context, app))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    row = _rows(handle)[0]
    assert row["status"] == 499
    assert _buffer(handle).get(row["id"])["error"] is False  # pyright: ignore[reportOptionalSubscript]


# --- bodies ---------------------------------------------------------------------------------------------------------


def _streaming_app(gen: Callable[[], Any]) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    app.get("/stream")(lambda: StreamingResponse(gen(), media_type="text/plain"))
    return app, install(app, enabled="ON", show_banner=False)


def test_streaming_response_size():
    async def gen() -> Any:
        for chunk in (b"a" * 10, b"b" * 20, b"c" * 5):
            yield chunk

    app, handle = _streaming_app(gen)
    assert TestClient(app).get("/stream").content == b"a" * 10 + b"b" * 20 + b"c" * 5
    row = _rows(handle)[0]
    assert (row["status"], row["responseSizeBytes"]) == (200, 35)


def test_streaming_chunks_forwarded_before_generator_ends():
    first_out = asyncio.Event()

    async def gen() -> Any:
        yield b"first"
        await asyncio.wait_for(first_out.wait(), 5)  # a buffering middleware would never let "first" out: timeout
        yield b"second"

    app, handle = _streaming_app(gen)
    sent: list[bytes] = []

    async def main() -> None:
        async def receive() -> Message:
            await asyncio.Event().wait()
            raise AssertionError  # pragma: no cover

        async def send(message: Message) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                sent.append(message["body"])
                first_out.set()

        call = app(_scope("/stream"), receive, send)
        await asyncio.wait_for(call, 10)

    asyncio.run(main())
    assert sent == [b"first", b"second"]
    assert _rows(handle)[0]["responseSizeBytes"] == 11


def test_pathsend_row_finalised():
    handle = _handle()

    async def app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send(_start(200))
        await send({"type": "http.response.pathsend", "path": "/tmp/file.bin"})

    sent = asyncio.run(_run(handle.context, app))
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.pathsend"]
    row = _rows(handle)[0]
    assert (row["status"], row["responseSizeBytes"]) == (200, 0)  # size is the sum of body chunks: none


# --- pass-through, self-exclusion, probe header, hook failure --------------------------------------------------------


def test_websocket_and_lifespan_pass_through():
    app = create_app(show_banner=False)
    handle: SharpitHandle = app.state.sharpit
    seen: list[object] = []

    @app.websocket("/ws/spy")
    async def spy(websocket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        seen.append(REQUEST.get())
        await websocket.accept()
        await websocket.close()

    with TestClient(app) as client:  # lifespan runs through the middleware too
        with client.websocket_connect("/ws/echo") as ws:
            ws.send_text("hello")
            assert ws.receive_text() == "hello"
        with client.websocket_connect("/ws/spy"):
            pass
    assert seen == [None]
    assert _rows(handle) == []


def test_hidden_self_counts_sharpit_requests():
    app = FastAPI()
    app.get("/host")(lambda: {})
    handle = install(app, enabled="ON", show_banner=False)
    client = TestClient(app, client=LOCAL, base_url="http://localhost")
    for path in ("/sharpit/api/panels", "/sharpit/", "/sharpit", "/host"):
        client.get(path, follow_redirects=False)
    report = client.get("/sharpit/api/http-exchanges").json()
    assert [e["path"] for e in report["exchanges"]] == ["/host"]
    assert report["hiddenSelf"] == 4  # the report request itself was counted before it ran
    assert (report["total"], report["recorded"]) == (1, 5)
    assert _buffer(handle).hidden_self == 4


def test_probe_header_stripped_from_real_request():
    app = FastAPI()

    @app.get("/echo")
    def echo(request: Request) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return {"probe": request.headers.get("x-sharpit-probe")}

    handle = install(app, enabled="ON", show_banner=False)
    resp = TestClient(app).get("/echo", headers={"X-Sharpit-Probe": "1"})
    assert resp.json() == {"probe": None}
    assert all(h["name"] != "x-sharpit-probe" for h in _rows(handle)[0]["requestHeaders"])

    # ruling C8: a scope tagged by sharpit's probe keeps the header and is recorded as an exchange
    probe = _scope("/echo", headers=[(b"host", b"localhost"), (b"x-sharpit-probe", b"1")])
    probe["extensions"] = {"sharpit.probe": True}
    sent: list[Message] = []

    async def main() -> None:
        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            sent.append(message)

        await app(probe, receive, send)

    asyncio.run(main())
    assert b'"probe":"1"' in b"".join(m.get("body", b"") for m in sent)
    assert any(h["name"] == "x-sharpit-probe" for h in _rows(handle)[0]["requestHeaders"])


def test_hook_failure_leaves_response(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    app = FastAPI()
    app.get("/ok")(lambda: {"ok": True})
    handle = install(app, enabled="ON", show_banner=False)

    def explode(_row: object) -> None:
        raise RuntimeError("secret-bearing message")

    monkeypatch.setattr(_buffer(handle), "add", explode)
    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        for _ in range(3):
            resp = client.get("/ok")
            assert (resp.status_code, resp.json()) == (200, {"ok": True})
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, warnings
    assert "request end" in warnings[0]
    assert "secret-bearing" not in warnings[0]


# --- wiring ---------------------------------------------------------------------------------------------------------


def _logger_handlers() -> dict[str, list[object]]:
    loggers = [logging.root, *(lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger))]
    return {lg.name: list(lg.handlers) for lg in loggers}


def _host_state(app: FastAPI) -> tuple[list[object], object, list[tuple[object, object]], dict[str, list[object]]]:
    return list(app.user_middleware), app.exception_handlers, list(app.exception_handlers.items()), _logger_handlers()


WITH_SQLALCHEMY = [
    pytest.param(False, id="plain"),
    pytest.param(True, id="sqlalchemy", marks=pytest.mark.needs_sqlalchemy),
]


def _assert_adds_nothing(with_sqlalchemy: bool, **options: Any) -> None:
    if with_sqlalchemy:
        pytest.importorskip("sqlalchemy")  # imported first, so install() could attach its class-level listeners
        sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    app = FastAPI()
    seen: list[object] = []
    app.get("/host")(lambda: seen.append(REQUEST.get()) or {})
    before = _host_state(app)
    install(app, show_banner=False, **options)
    after = _host_state(app)
    assert after[0] == before[0]  # user_middleware
    assert after[1] is before[1]  # the exception_handlers dict itself
    assert after[2] == before[2]
    assert all(a[1] is b[1] for a, b in zip(after[2], before[2], strict=True))
    assert after[3] == before[3]  # handlers on every logger
    with TestClient(app) as client:
        assert client.get("/host").status_code == 200
    assert seen == [None]  # the request contextvar was never set
    if with_sqlalchemy:
        assert not any(sqla.attached().values())  # no SQLAlchemy listener on Engine


@pytest.mark.parametrize("with_sqlalchemy", WITH_SQLALCHEMY)
def test_inactive_adds_nothing(with_sqlalchemy: bool):
    _assert_adds_nothing(with_sqlalchemy, enabled="OFF")


@pytest.mark.parametrize("with_sqlalchemy", WITH_SQLALCHEMY)
def test_all_capture_panels_disabled_adds_nothing(with_sqlalchemy: bool):
    # the database panels read the engine registry, so they are off too for "nothing" (step 4a, spec §6.1)
    disabled = (*CAPTURE_PANELS, *sqla.DISCOVERY_PANELS) if with_sqlalchemy else CAPTURE_PANELS
    _assert_adds_nothing(with_sqlalchemy, enabled="ON", panels={p: {"enabled": False} for p in disabled})


def test_add_middleware_after_start_warns_and_unavailable(caplog: pytest.LogCaptureFixture):
    app = FastAPI()
    app.get("/host")(lambda: {})
    client = TestClient(app, client=LOCAL, base_url="http://localhost")
    assert client.get("/host").status_code == 200  # the middleware stack is built now
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        install(app, enabled="ON", show_banner=False)
    assert [r.getMessage() for r in caplog.records] == [CAPTURE_TOO_LATE]
    panel = next(p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "http-exchanges")
    assert (panel["available"], panel["unavailableReason"]) == (False, CAPTURE_TOO_LATE_REASON)
    report = client.get("/sharpit/api/http-exchanges").json()
    assert (report["exchanges"], report["unavailableReason"]) == ([], CAPTURE_TOO_LATE_REASON)
    assert client.get("/sharpit/api/overview").status_code == 200  # everything else works


def _order_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "Call sharpit.install(app) last" in r.getMessage()]


def test_middleware_added_after_install_warns_once(caplog: pytest.LogCaptureFixture):
    late = FastAPI()
    late.get("/host")(lambda: {})
    install(late, enabled="ON", show_banner=False)
    late.add_middleware(CORSMiddleware, allow_origins=["*"])
    with caplog.at_level(logging.WARNING, logger="sharpit"), TestClient(late) as client:
        for _ in range(2):
            client.get("/host")
    warnings = _order_warnings(caplog)
    assert len(warnings) == 1, warnings
    assert "CORSMiddleware" in warnings[0], warnings

    caplog.clear()
    last = FastAPI()
    last.get("/host")(lambda: {})
    last.add_middleware(CORSMiddleware, allow_origins=["*"])
    install(last, enabled="ON", show_banner=False)
    with caplog.at_level(logging.WARNING, logger="sharpit"), TestClient(last) as client:
        client.get("/host")
        TestClient(late).get("/host")  # without lifespan the first request checks too: still one warning in all
    assert _order_warnings(caplog) == []


def test_second_install_no_double_middleware():
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    install(app, enabled="ON", show_banner=False)
    assert [m.cls for m in app.user_middleware].count(CaptureMiddleware) == 1  # pyright: ignore[reportUnknownMemberType]


def test_uninstall_capture_removes_hooks():
    app = FastAPI()
    seen: list[object] = []
    app.get("/host")(lambda: seen.append(REQUEST.get()) or {})
    handle = install(app, enabled="ON", show_banner=False)
    client = TestClient(app)
    client.get("/host")
    handle.uninstall_capture()
    handle.uninstall_capture()  # idempotent
    client.get("/host")
    assert seen[0] is not None
    assert seen[1] is None
    assert len(_rows(handle)) == 1


@pytest.mark.needs_sqlalchemy
def test_uninstall_capture_removes_sql_listeners():
    pytest.importorskip("sqlalchemy")
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    handle = install(FastAPI(), enabled="ON", show_banner=False)
    assert all(sqla.attached().values())
    assert sqla.routed(handle.context) == (True, True)
    handle.uninstall_capture()
    handle.uninstall_capture()  # idempotent
    assert not any(sqla.attached().values())
    assert sqla.routed(handle.context) == (False, False)


def test_lifespan_shutdown_detaches_and_startup_attaches():
    app = FastAPI()
    app.get("/host")(lambda: {})
    handle = install(app, enabled="ON", show_banner=False)
    with TestClient(app) as client:
        client.get("/host")
        assert handle.context.capture.loop is not None
    TestClient(app).get("/host")  # after shutdown: not captured
    assert len(_rows(handle)) == 1
    with TestClient(app) as client:  # a new startup attaches again
        client.get("/host")
    assert len(_rows(handle)) == 2


def test_install_creates_no_threads():
    before = set(threading.enumerate())
    app = FastAPI()

    @app.get("/host")
    async def host() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    handle = install(app, enabled="ON", show_banner=False, engines=[object()], health_checks={"db": lambda: True})
    assert set(threading.enumerate()) <= before
    assert handle.context.engines
    assert set(handle.context.health_checks) == {"db"}

    async def main() -> None:
        transport = httpx.ASGITransport(app=app, client=LOCAL)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            assert (await client.get("/host")).status_code == 200

    asyncio.run(main())
    assert set(threading.enumerate()) <= before
    assert len(_rows(handle)) == 1
