"""``CaptureMiddleware`` and ``CaptureWiring`` (spec §6.1, §7.1, §9, §14.2).

Middleware cases call the ASGI app directly where the outcome depends on message order (disconnects, cancellation,
pathsend); the rest go through ``TestClient``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import httpx
import pytest
from examples.fastapi_sample.app import create_app
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.responses import Response
from starlette.types import Message, Receive, Scope, Send

import sharpit.fastapi.capture as capture_mod
import sharpit.fastapi.capture_exceptions as capture_exceptions
from fastapi import FastAPI, Request, WebSocket
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.capture import Suspendable
from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.context import SharpitContext
from sharpit.engine.lowfootprint import LowFootprintService
from sharpit.engine.panels import panel_is_implemented
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import (
    CAPTURE_TOO_LATE,
    CAPTURE_TOO_LATE_REASON,
    HOOK_NAMES,
    CaptureMiddleware,
    wiring_of,
)

LOCAL = ("127.0.0.1", 50000)
CAPTURE_PANELS = ("http-exchanges", "exceptions", "sql-trace", "activity", "security-logs")
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


async def _run(
    ctx: SharpitContext | None,
    app: FakeApp,
    inbox: list[Message] | None = None,
    scope: Scope | None = None,
    *,
    fail_start: Exception | None = None,
    wrap: bool = True,
    sent: list[Message] | None = None,
) -> list[Message]:
    pending = list(inbox or [{"type": "http.request", "body": b"", "more_body": False}])
    if sent is None:
        sent = []

    async def receive() -> Message:
        if pending:
            return pending.pop(0)
        await asyncio.Event().wait()  # like a server with nothing more to say: a streaming response listens for it
        raise AssertionError  # pragma: no cover

    async def send(message: Message) -> None:
        if fail_start is not None and message["type"] == "http.response.start":
            raise fail_start
        sent.append(message)

    target = CaptureMiddleware(app, ctx) if wrap and ctx is not None else app
    await target(scope or _scope(), receive, send)
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

    running = _run(handle.context, app)
    with pytest.raises(ValueError, match="boom"):
        asyncio.run(running)
    row = _rows(handle)[0]
    assert row["status"] == 201
    assert _buffer(handle).get(row["id"])["error"] is True  # pyright: ignore[reportOptionalSubscript]


def test_unhandled_exception_500_and_reraised():
    handle = _handle()

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise ValueError("boom")

    running = _run(handle.context, app)
    with pytest.raises(ValueError, match="boom"):
        asyncio.run(running)
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


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _explode(message: str) -> Callable[..., Any]:
    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(message)

    return explode


def _starts(sent: list[Message]) -> list[Message]:
    return [m for m in sent if m["type"] == "http.response.start"]


def test_hook_failure_leaves_response(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    # ported: BootUiHttpExchangesFilterTests.repositoryFailureDoesNotAlterTheServedResponse
    # ported: BootUiHttpExchangesWebFilterTests.repositoryFailureDoesNotPreventResponseCommitment
    app = FastAPI()
    app.get("/ok")(lambda: Response(content="complete", status_code=201, media_type="text/plain"))
    handle = install(app, enabled="ON", show_banner=False)
    monkeypatch.setattr(_buffer(handle), "add", _explode("secret-bearing message"))
    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        for _ in range(3):
            resp = client.get("/ok")
            assert (resp.status_code, resp.text) == (201, "complete")
    warnings = _warnings(caplog)
    assert len(warnings) == 1, warnings
    assert "request end" in warnings[0]
    assert "RuntimeError" in warnings[0]
    assert "secret-bearing" not in warnings[0]


# --- BootUI 2.4.0 #1615: HTTP exchange recording never disrupts a response -------------------------------------------


def test_metadata_failure_does_not_alter_a_committed_response(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    # ported: BootUiHttpExchangesFilterTests.metadataFailureDoesNotAlterACommittedResponse
    # ported: BootUiHttpExchangesWebFilterTests.metadataFailureDoesNotPreventResponseCommitment
    app = FastAPI()

    @app.get("/download")
    def download():
        return Response(content="complete", status_code=206, media_type="text/plain")

    handle = install(app, enabled="ON", show_banner=False)
    monkeypatch.setattr(capture_mod, "exchange_row", _explode("secret-header-message"))

    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        resp = client.get("/download?token=secret-query")
        assert resp.status_code == 206
        assert resp.text == "complete"

    assert _buffer(handle).rows() == []
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "request end" in warnings[0]
    assert "RuntimeError" in warnings[0]
    assert "secret-header-message" not in warnings[0]
    assert "secret-query" not in warnings[0]
    assert "/download" not in warnings[0]


@pytest.mark.parametrize(
    "failure_factory",
    [
        lambda: RuntimeError("app-runtime-error"),
        lambda: ValueError("app-value-error"),
        lambda: KeyError("app-key-error"),
    ],
    ids=["runtime", "value", "key"],
)
@pytest.mark.parametrize("recording", ["healthy", "failing-add", "failing-metadata"])
def test_preserves_every_application_exception_even_when_recording_also_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure_factory: Callable[[], Exception],
    recording: str,
):
    # ported: BootUiHttpExchangesFilterTests.preservesEveryApplicationExceptionEvenWhenRecordingAlsoFails
    # ported: BootUiHttpExchangesWebFilterTests.preservesApplicationErrorsAndLetsTheErrorHandlerCommitDespiteARecordingFailure  # noqa: E501
    app = FastAPI()

    failure = failure_factory()

    @app.get("/api/fail")
    def fail():
        raise failure

    handle = install(app, enabled="ON", show_banner=False)

    if recording == "failing-add":
        monkeypatch.setattr(_buffer(handle), "add", _explode("secret-repository-message"))
    if recording == "failing-metadata":
        monkeypatch.setattr(capture_mod, "exchange_row", _explode("secret-repository-message"))

    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        with pytest.raises(type(failure)) as exc_info:
            client.get("/api/fail")
        assert exc_info.value is failure

    store = handle.context.capture.exceptions
    assert store is not None
    assert type(failure).__name__ in [g["exceptionClassName"] for g in store.report()["groups"]]
    if recording == "healthy":
        rows = _buffer(handle).rows()
        assert len(rows) == 1
        assert rows[0]["status"] == 500
        assert rows[0]["error"] is True
    else:
        warnings = _warnings(caplog)
        assert len(warnings) == 1
        assert "request end" in warnings[0]
        assert "RuntimeError" in warnings[0]
        assert "secret-repository-message" not in warnings[0]


class _Teapot(Exception):
    pass


@pytest.mark.parametrize("failing_buffer", [False, True], ids=["healthy-buffer", "failing-buffer"])
def test_the_error_handler_commits_despite_a_recording_failure(monkeypatch: pytest.MonkeyPatch, failing_buffer: bool):
    # ported: BootUiHttpExchangesWebFilterTests.preservesApplicationErrorsAndLetsTheErrorHandlerCommitDespiteARecordingFailure  # noqa: E501
    app = FastAPI()

    @app.exception_handler(_Teapot)
    def handler(_request: Request, _exc: _Teapot):  # pyright: ignore[reportUnusedFunction]
        return Response(content="complete", status_code=418, media_type="text/plain")

    @app.get("/api/fail")
    def fail():  # pyright: ignore[reportUnusedFunction]
        raise _Teapot

    handle = install(app, enabled="ON", show_banner=False)
    if failing_buffer:
        monkeypatch.setattr(_buffer(handle), "add", _explode("secret-repository-message"))

    resp = TestClient(app).get("/api/fail")
    assert (resp.status_code, resp.text) == (418, "complete")


@pytest.mark.parametrize("failing_buffer", [False, True], ids=["healthy-buffer", "failing-buffer"])
def test_application_and_send_failures_propagate_unchanged(monkeypatch: pytest.MonkeyPatch, failing_buffer: bool):
    # ported: BootUiHttpExchangesWebFilterTests.doesNotSwallowSynchronousApplicationOrApplicationCommitFailures
    handle = _handle()
    if failing_buffer:
        monkeypatch.setattr(_buffer(handle), "add", _explode("secret-repository-message"))
    application_failure = RuntimeError("application")
    send_failure = OSError("commit")

    async def raises_at_once(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise application_failure

    async def answers(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send(_start(200))

    raising_call = _run(handle.context, raises_at_once, scope=_scope("/api/fail"))
    with pytest.raises(RuntimeError) as application:
        asyncio.run(raising_call)
    assert application.value is application_failure
    failing_send = _run(handle.context, answers, scope=_scope("/api/fail"), fail_start=send_failure)
    with pytest.raises(OSError, match="commit") as commit:
        asyncio.run(failing_send)
    assert commit.value is send_failure


@pytest.mark.parametrize("failing_step", ["mask_path", "request_id", "mail_wrapper", "first_request_hook"])
def test_setup_failure_still_invokes_the_application_exactly_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, failing_step: str
):
    # ported: BootUiHttpExchangesFilterTests.setupFailureStillInvokesTheApplicationExactlyOnce
    # ported: BootUiHttpExchangesWebFilterTests.preparationFailuresStillInvokeTheApplicationExactlyOnce
    app = FastAPI()
    calls = 0

    @app.get("/api/orders")
    def orders():
        nonlocal calls
        calls += 1
        return {"orders": []}

    handle = install(app, enabled="ON", show_banner=False)
    wiring = wiring_of(handle.context)
    assert wiring is not None
    owner, name = {
        "mask_path": (handle.context.masker, "mask_request_path"),
        "request_id": (capture_mod, "new_request_id"),
        "mail_wrapper": (capture_mod, "ensure_mail_wrapped"),
        "first_request_hook": (wiring, "on_first_request"),
    }[failing_step]
    monkeypatch.setattr(owner, name, _explode("secret-metadata-message"))

    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        resp = client.get("/api/orders")
        assert resp.status_code == 200
        assert resp.json() == {"orders": []}

    assert calls == 1
    assert _buffer(handle).rows() == []
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "request start" in warnings[0]
    assert "RuntimeError" in warnings[0]
    assert "secret-metadata-message" not in warnings[0]


def test_a_setup_failure_leaves_no_trace_on_an_application_exception(monkeypatch: pytest.MonkeyPatch):
    # ported: BootUiHttpExchangesFilterTests.setupFailureStillInvokesTheApplicationExactlyOnce (the failure stays unchanged)  # noqa: E501
    handle = _handle()
    monkeypatch.setattr(handle.context.masker, "mask_request_path", _explode("secret-metadata-message"))
    failure = ValueError("application")

    async def app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise failure

    call = _run(handle.context, app, scope=_scope("/api/fail"))
    with pytest.raises(ValueError) as raised:
        asyncio.run(call)
    assert raised.value is failure
    assert raised.value.__context__ is None  # the setup failure's message must not ride along in the traceback


def test_an_exception_from_sharpits_own_route_reaches_the_host_after_one_invocation(caplog: pytest.LogCaptureFixture):
    # ported: BootUiHttpExchangesFilterTests.setupFailureStillInvokesTheApplicationExactlyOnce (one invocation)
    handle = _handle()
    failure = ValueError("own-route-failure")
    calls = 0

    async def own_route(_scope: Scope, _receive: Receive, send: Send) -> None:
        nonlocal calls
        calls += 1
        await send(_start(200))
        raise failure

    sent: list[Message] = []
    call = _run(handle.context, own_route, scope=_scope("/sharpit/api/boom"), sent=sent)
    with caplog.at_level(logging.WARNING, logger="sharpit"), pytest.raises(ValueError) as raised:
        asyncio.run(call)
    assert raised.value is failure
    assert calls == 1
    assert len(_starts(sent)) == 1
    assert not any("request start" in w for w in _warnings(caplog))


@pytest.mark.parametrize("failing_step", ["first_request_hook", "mail_wrapper"])
def test_a_setup_failure_never_passes_a_forged_probe_header_to_the_host(
    monkeypatch: pytest.MonkeyPatch, failing_step: str
):
    app = FastAPI()

    @app.get("/echo")
    def echo(request: Request) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return {"probe": request.headers.get("x-sharpit-probe")}

    handle = install(app, enabled="ON", show_banner=False)
    wiring = wiring_of(handle.context)
    assert wiring is not None
    owner, name = (
        (wiring, "on_first_request") if failing_step == "first_request_hook" else (capture_mod, "ensure_mail_wrapped")
    )
    monkeypatch.setattr(owner, name, _explode("setup"))

    resp = TestClient(app).get("/echo", headers={"X-Sharpit-Probe": "1"})
    assert resp.status_code == 200
    assert resp.json() == {"probe": None}


@pytest.mark.parametrize(
    ("extensions", "headers"),
    [
        ("invalid-extensions", [(b"host", b"localhost"), (b"x-sharpit-probe", b"1")]),
        ({}, [(b"host", b"localhost"), (b"x-sharpit-probe", b"1", b"extra")]),
    ],
    ids=["non-dict-extensions", "3-tuple-header"],
)
def test_malformed_scope_probe_strip_fails_open_calling_app_once(
    caplog: pytest.LogCaptureFixture, extensions: Any, headers: list[Any]
):
    handle = _handle()
    calls = 0
    passed_scope: Scope | None = None

    async def app(scope: Scope, _receive: Receive, send: Send) -> None:
        nonlocal calls, passed_scope
        calls += 1
        passed_scope = scope
        await send(_start(200))

    scope = _scope("/api/orders", headers=headers, extensions=extensions)
    raised: Exception | None = None
    sent: list[Message] = []
    try:
        sent = asyncio.run(_run(handle.context, app, scope=scope))
    except Exception as exc:
        raised = exc

    assert raised is None
    assert calls == 1
    assert len(_starts(sent)) == 1
    assert passed_scope is not None
    assert not any(
        isinstance(h, (tuple, list)) and len(h) >= 1 and h[0] == capture_mod.PROBE_HEADER
        for h in passed_scope.get("headers", ())
    )
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "request start" in warnings[0]


def test_forged_probe_header_stripped_when_capture_hook_suspended():
    app = FastAPI()

    @app.get("/probe-check")
    def probe_check(request: Request) -> dict[str, Any]:
        return {"probe": request.headers.get("x-sharpit-probe")}

    handle = install(app, enabled="ON", show_banner=False)
    wiring = wiring_of(handle.context)
    assert wiring is not None
    wiring.suspended_hooks.add(capture_mod.HOOK_CAPTURE_MIDDLEWARE)

    client = TestClient(app)
    resp = client.get("/probe-check", headers={"X-Sharpit-Probe": "forged-client-value"})
    assert resp.status_code == 200
    assert resp.json() == {"probe": None}


def test_route_template_internal_error_still_records_exchange_and_journal(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    app = FastAPI()

    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        return {"item_id": item_id}

    handle = install(app, enabled="ON", show_banner=False)
    monkeypatch.setattr(capture_exceptions, "_mount_prefix", _explode("route template lookup failed"))

    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        resp = client.get("/items/42")
        assert resp.status_code == 200
        assert resp.json() == {"item_id": 42}

    buffer = _buffer(handle)
    rows = buffer.rows()
    assert len(rows) == 1
    assert rows[0]["status"] == 200

    journal = handle.context.capture.journal
    assert journal is not None
    events = [e for e in journal.records("http") if e.get("type") == "http" or "status" in e]
    assert len(events) == 1
    assert events[0]["status"] == 200

    assert not any("request end" in warning for warning in _warnings(caplog))


def test_exception_store_record_failure_still_records_exchange_and_journal_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    app = FastAPI()

    @app.get("/api/crash")
    def crash():
        raise ValueError("endpoint blew up")

    handle = install(app, enabled="ON", show_banner=False)
    store = handle.context.capture.exceptions
    assert store is not None

    forgotten_ids: list[str] = []
    real_forget = store.forget_request

    def track_forget(request_id: str) -> None:
        forgotten_ids.append(request_id)
        real_forget(request_id)

    monkeypatch.setattr(store, "record", _explode("exception store record failed"))
    monkeypatch.setattr(store, "forget_request", track_forget)

    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"), pytest.raises(ValueError, match="endpoint blew up"):
        client.get("/api/crash")

    buffer = _buffer(handle)
    rows = buffer.rows()
    assert len(rows) == 1
    assert rows[0]["status"] == 500

    journal = handle.context.capture.journal
    assert journal is not None
    events = [e for e in journal.records("http") if e.get("type") == "http" or "status" in e]
    assert len(events) == 1
    assert events[0]["status"] == 500

    assert len(forgotten_ids) == 1
    warnings = _warnings(caplog)
    assert any("request end" in w and "RuntimeError" in w for w in warnings)


def test_a_capture_clock_failure_on_the_last_chunk_still_serves_the_response(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    # ported: BootUiHttpExchangesWebFilterTests.callbackRegistrationFailureStillServesTheResponse
    # adapted: only the capture clock of the response stamp fails (once); the row is still recorded at request end
    app = FastAPI()
    fired: list[bool] = []

    def failing_once() -> int:
        if not fired:
            fired.append(True)
            raise RuntimeError("secret-send-message")
        return time.perf_counter_ns()

    class _TimeProxy:
        def __getattr__(self, name: str) -> Any:
            return getattr(time, name)

    @app.get("/download")
    def download():
        proxy = _TimeProxy()
        proxy.perf_counter_ns = failing_once  # type: ignore[method-assign]
        monkeypatch.setattr(capture_mod, "time", proxy)
        return Response(content="complete", status_code=200, media_type="text/plain")

    handle = install(app, enabled="ON", show_banner=False)

    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        resp = client.get("/download")
        assert resp.status_code == 200
        assert resp.text == "complete"

    assert fired == [True]
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "hook response failed" in warnings[0]
    assert "RuntimeError" in warnings[0]
    assert "secret-send-message" not in warnings[0]
    assert [row["status"] for row in _buffer(handle).rows()] == [200]


def _fail_recording_of(
    monkeypatch: pytest.MonkeyPatch, buffer: HttpExchangeBuffer, *, metadata: str, repository: str
) -> dict[str, int]:
    """Make the row assembly fail for a request path ending ``metadata`` and ``buffer.add`` for one ending
    ``repository``; every other exchange is recorded as usual. The counts say that each failure really ran."""
    failures = {"metadata": 0, "repository": 0}
    real_exchange_row, real_add = capture_mod.exchange_row, buffer.add

    def exchange_row(*args: Any, path: str, **kwargs: Any) -> dict[str, Any]:
        if path.endswith(metadata):
            failures["metadata"] += 1
            raise RuntimeError("secret-capture-message")
        return real_exchange_row(*args, path=path, **kwargs)

    def add(row: dict[str, Any]) -> None:
        if row["path"].endswith(repository):
            failures["repository"] += 1
            raise RuntimeError("secret-capture-message")
        real_add(row)

    monkeypatch.setattr(capture_mod, "exchange_row", exchange_row)
    monkeypatch.setattr(buffer, "add", add)
    return failures


def test_streams_the_full_pdf_despite_malformed_metadata_and_repository_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    # ported: SpringHttpExchangeStreamingTest.streamsTheFullPdfDespiteMalformedMetadataAndRepositoryFailures
    # ported: WebFluxHttpExchangeStreamingTest.streamsTheFullPdfDespiteARepositoryFailureDuringCommit  # noqa: E501
    app = FastAPI()
    body = b"%PDF-1.4\n" + b"x" * 200_000

    @app.get("/api/recording-stream/{anomaly}")
    def stream_pdf(anomaly: str):  # pyright: ignore[reportUnusedFunction]
        def generate():
            chunk_size = 16384
            for i in range(0, len(body), chunk_size):
                yield body[i : i + chunk_size]

        return StreamingResponse(generate(), media_type="application/pdf")

    handle = install(app, enabled="ON", show_banner=False)
    buffer = _buffer(handle)
    failures = _fail_recording_of(monkeypatch, buffer, metadata="/metadata", repository="/repository")

    async def stream_all() -> dict[str, list[Message]]:
        answers: dict[str, list[Message]] = {}
        for anomaly in ("normal", "metadata", "repository"):
            answers[anomaly] = await _run(None, app, scope=_scope(f"/api/recording-stream/{anomaly}"), wrap=False)
        return answers

    with caplog.at_level(logging.WARNING, logger="sharpit"):
        answers = asyncio.run(stream_all())

    for anomaly, sent in answers.items():
        (start,) = _starts(sent)
        assert start["status"] == 200, anomaly
        assert (b"content-type", b"application/pdf") in start["headers"], anomaly
        assert b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body") == body, anomaly
    assert failures == {"metadata": 1, "repository": 1}
    assert [(row["path"], row["status"], row["responseSizeBytes"]) for row in buffer.rows()] == [
        ("/api/recording-stream/normal", 200, len(body))
    ]
    warnings = _warnings(caplog)
    assert not any("secret-capture-message" in w for w in warnings)
    assert [("request end" in w, "RuntimeError" in w) for w in warnings] == [(True, True)]


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
    discovery = tuple(p for p in sqla.DISCOVERY_PANELS if panel_is_implemented(p))  # unimplemented ids are unknown
    disabled = (*CAPTURE_PANELS, *discovery) if with_sqlalchemy else CAPTURE_PANELS
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


def test_every_capture_hook_is_registered():
    app = FastAPI()
    app.get("/host")(lambda: {})
    handle = install(app, enabled="ON", show_banner=False)
    with TestClient(app) as client:
        client.get("/host")
        hooks = handle.context.capture.hooks.hooks()
        names = {hook.name for hook in hooks}
        assert names == {
            "capture-middleware",
            "exception-handlers",
            "log-handler",
            "mail",
            "runtime-journal",
            "security-log",
            "sqla-listeners",
            "sqlite-listeners",
            "traces",
            "transactions",
        }


def _hook(handle: SharpitHandle, name: str) -> Suspendable:
    return next(h for h in handle.context.capture.hooks.hooks() if h.name == name)


def test_each_capture_hook_suspends_only_itself():
    app = FastAPI()
    app.get("/host")(lambda: {})
    handle = install(app, enabled="ON", show_banner=False)
    ctx = handle.context
    with TestClient(app) as client:
        client.get("/host")
        wiring = wiring_of(ctx)
        assert wiring is not None
        routed = sqla.routed(ctx)

        _hook(handle, "log-handler").suspend()
        client.get("/host")
        assert len(_rows(handle)) == 2  # the middleware still records
        assert not wiring.log_handler_on_root()
        _hook(handle, "log-handler").resume()
        assert wiring.log_handler_on_root()

        _hook(handle, "capture-middleware").suspend()
        client.get("/host")
        assert len(_rows(handle)) == 2  # this request was not recorded
        assert wiring.log_handler_on_root()  # the log handler stays
        assert sqla.routed(ctx) == routed  # SQL routing stays
        _hook(handle, "capture-middleware").resume()
        client.get("/host")
        assert len(_rows(handle)) == 3


def test_each_lane_and_sqla_hook_suspends_only_itself():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    ctx = handle.context
    wiring = wiring_of(ctx)
    assert wiring is not None
    calls: list[str] = []

    def lane(name: str) -> Callable[[], Callable[[], None]]:
        def attacher() -> Callable[[], None]:
            calls.append(f"arm {name}")
            return lambda: calls.append(f"disarm {name}")

        return attacher

    wiring.add_lane(ctx, "lane-a", lane("a"))
    wiring.add_lane(ctx, "lane-b", lane("b"))
    with TestClient(app):
        assert calls == ["arm a", "arm b"]
        teardowns = len(ctx.capture.teardowns)
        _hook(handle, "lane-a").suspend()
        _hook(handle, "lane-a").suspend()  # idempotent
        assert calls == ["arm a", "arm b", "disarm a"]
        assert len(ctx.capture.teardowns) == teardowns - 1
        _hook(handle, "lane-a").resume()
        _hook(handle, "lane-a").resume()  # idempotent
        assert calls == ["arm a", "arm b", "disarm a", "arm a"]


@pytest.mark.needs_sqlalchemy
def test_sqla_hook_suspends_only_sqlalchemy_routing():
    pytest.importorskip("sqlalchemy")
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    handle = install(FastAPI(), enabled="ON", show_banner=False)
    ctx = handle.context
    assert sqla.routed(ctx) == (True, True)
    _hook(handle, "sqla-listeners").suspend()
    assert sqla.routed(ctx) == (False, False)
    assert "sqlalchemy" in ctx.capture.suspended_sources
    _hook(handle, "sqla-listeners").resume()
    assert sqla.routed(ctx) == (True, True)
    assert "sqlalchemy" not in ctx.capture.suspended_sources
    handle.uninstall_capture()


def test_low_footprint_suspends_and_resumes_registered_capture_hooks():
    app = FastAPI()
    app.get("/host")(lambda: {})
    handle = install(app, enabled="ON", show_banner=False)
    with TestClient(app) as client:
        client.get("/host")
        assert len(_rows(handle)) == 1
        service = LowFootprintService(handle.context.capture.hooks)
        service.suspend()
        client.get("/host")
        assert len(_rows(handle)) == 0
        service.resume()
        client.get("/host")
        assert len(_rows(handle)) == 1
        assert _rows(handle)[0]["path"] == "/host"
        service.suspend()
        client.get("/host")
        assert len(_rows(handle)) == 0
        service.resume()
        client.get("/host")
        assert len(_rows(handle)) == 1
        assert _rows(handle)[0]["path"] == "/host"


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


@pytest.mark.parametrize("shutdown", ["uninstall", "lifespan"])
def test_suspending_sqla_on_a_detached_context_keeps_it_out_of_dispatch(shutdown: str):
    """Review R1: after a shutdown, suspending sqla-listeners alone must not route raw sqlite3 here again."""
    from sharpit.engine.sources import dispatch

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    ctx = handle.context
    if shutdown == "uninstall":
        handle.uninstall_capture()
    else:
        with TestClient(app):
            pass
    assert ctx.context_id not in dispatch._contexts  # pyright: ignore[reportPrivateUsage]
    _hook(handle, "sqla-listeners").suspend()
    assert ctx.context_id not in dispatch._contexts, "a detached context was re-added to dispatch"  # pyright: ignore[reportPrivateUsage]


def test_every_registered_hook_name_is_a_named_constant():
    """Review R2: hook names are spelled once, as constants; registration, actions and call sites use them."""
    import sharpit.fastapi.capture as capture_module

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    with TestClient(app):
        names = {hook.name for hook in handle.context.capture.hooks.hooks()}
    known = getattr(capture_module, "HOOK_NAMES", frozenset[str]())
    assert names <= known, f"hook names without a constant: {sorted(names - known)}"


class _Teapot(Exception):
    pass


def _probe_app() -> tuple[FastAPI, SharpitHandle]:
    import sqlite3

    import sqlalchemy as sa
    from fastapi.responses import JSONResponse

    app = FastAPI()
    engine = sa.create_engine("sqlite://")
    app.get("/host")(lambda: {})

    @app.get("/denied")
    async def denied() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({}, status_code=401)

    @app.get("/teapot")
    async def teapot() -> None:  # pyright: ignore[reportUnusedFunction]
        raise _Teapot

    @app.get("/sql")
    def sql() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        connection = sqlite3.connect(":memory:")  # in a request: only this app's context records it
        connection.execute("select 1 as raw_probe")
        connection.close()
        with engine.connect() as orm:
            orm.execute(sa.text("select 1 as sqla_probe"))
        return {}

    @app.exception_handler(_Teapot)
    async def on_teapot(_request: Request, _exc: _Teapot) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({}, status_code=418)

    return app, install(app, enabled="ON", show_banner=False, engines=[engine])


def _mail_records(capture: Any) -> bool:
    """Whether the context's mail recorder still stores a message (a paused one does not); no socket is opened."""
    recorder = capture.mail
    before = len(recorder.entries())
    recorder.record("probe@example.test", ["probe@example.test"], "Subject: probe\n\nbody\n")
    return len(recorder.entries()) > before


def _recording(handle: SharpitHandle, client: TestClient) -> dict[str, bool]:
    """Hook name -> whether that hook still records, each probed by what it captures (lanes: armed)."""
    from sharpit.engine import tools
    from sharpit.engine.capture.securitylogs import SecurityEventBuffer

    ctx = handle.context
    capture = ctx.capture
    wiring = wiring_of(ctx)
    assert wiring is not None
    assert capture.exceptions is not None
    assert isinstance(capture.security_logs, SecurityEventBuffer)

    rows, events = len(_rows(handle)), len(capture.security_logs.snapshot())
    raised = capture.exceptions.report()["totalExceptions"]

    def traced(alias: str) -> int:
        return sum(alias in entry["sql"] for entry in tools.sql_trace_report(ctx)["entries"])

    raw, orm = traced("raw_probe"), traced("sqla_probe")
    client.get("/denied")
    client.get("/teapot")
    client.get("/sql")
    armed = {wiring._lane_of[id(a)] for a in capture.attachers if id(a) in wiring._armed and id(a) in wiring._lane_of}  # pyright: ignore[reportPrivateUsage]
    return {
        "capture-middleware": len(_rows(handle)) > rows,
        "security-log": len(capture.security_logs.snapshot()) > events,
        "exception-handlers": capture.exceptions.report()["totalExceptions"] > raised,
        "log-handler": wiring.log_handler_on_root(),
        "sqla-listeners": traced("sqla_probe") > orm,
        "sqlite-listeners": traced("raw_probe") > raw,
        "traces": "traces" in armed,
        "transactions": "transactions" in armed,
        "runtime-journal": capture.journal is not None and capture.journal.offer({"source": "http", "probe": True}),
        "mail": _mail_records(capture),
    }


# the 401/403 hook is called by the capture middleware: a suspended middleware sees no exchange to report
RIDES_ON = {"capture-middleware": ("security-log",)}


class _Provider:
    def add_span_processor(self, _processor: object) -> None:
        return None


@pytest.fixture
def _probe_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A planted OpenTelemetry SDK provider (the traces lane arms on it) and a clean SQL slate."""
    import sqlite3
    import sys
    from types import ModuleType

    from sharpit.engine import otel
    from sharpit.engine.sources import sqlite

    planted = _Provider()
    trace = ModuleType("opentelemetry.trace")
    trace.get_tracer_provider = lambda: planted  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", ModuleType("opentelemetry.sdk.trace"))
    monkeypatch.setattr(otel, "PROCESSOR", otel.SharpitSpanProcessor())
    real = sqlite3.connect
    sqla.detach_all()  # earlier tests in this worker may have left contexts behind
    yield
    sqlite.detach_all(keep_scan=True)
    sqlite3.connect = real
    sqla.detach_all()


@pytest.mark.needs_sqlalchemy
@pytest.mark.usefixtures("_probe_env")
@pytest.mark.parametrize("name", sorted(HOOK_NAMES))
def test_a_suspended_hook_stays_off_across_a_restart_and_its_siblings_keep_recording(name: str):
    """Review R4: suspending one hook leaves every sibling recording, and a lifespan restart keeps it off."""
    pytest.importorskip("sqlalchemy")
    app, handle = _probe_app()
    everything = dict.fromkeys(HOOK_NAMES, True)
    expected = everything | dict.fromkeys({name, *RIDES_ON.get(name, ())}, False)
    with TestClient(app) as client:
        assert _recording(handle, client) == everything
        _hook(handle, name).suspend()
        assert _recording(handle, client) == expected
    with TestClient(app) as client:  # a lifespan restart
        assert _recording(handle, client) == expected
        _hook(handle, name).resume()
        assert _recording(handle, client) == everything
    handle.uninstall_capture()


@pytest.mark.needs_sqlalchemy
@pytest.mark.usefixtures("_probe_env")
@pytest.mark.parametrize("name", sorted(HOOK_NAMES))
def test_suspending_a_hook_in_one_context_leaves_another_recording(name: str):
    """Review R4: hooks share process-wide state (root logger, sqlite3.connect, Engine listeners, the span processor);
    suspending one context's hook never silences another context."""
    pytest.importorskip("sqlalchemy")
    (first_app, first), (second_app, second) = _probe_app(), _probe_app()
    everything = dict.fromkeys(HOOK_NAMES, True)
    with TestClient(first_app) as first_client, TestClient(second_app) as second_client:
        _hook(first, name).suspend()
        mine = _recording(first, first_client)
        # the middleware also feeds the security log, and an untagged request's raw sqlite3 has two candidate
        # contexts (so none records); every other hook is independent of it
        silenced = {name, "security-log", "sqlite-listeners"} if name == "capture-middleware" else {name}
        assert mine == everything | dict.fromkeys(silenced, False)
        assert _recording(second, second_client) == everything
    first.uninstall_capture()
    second.uninstall_capture()


def test_shutting_down_after_suspending_sqla_takes_the_context_out_of_dispatch():
    """Review R1, the other order: suspend sqla-listeners while live (raw sqlite3 keeps routing), then shut down."""
    from sharpit.engine.sources import dispatch

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    ctx = handle.context
    with TestClient(app):
        _hook(handle, "sqla-listeners").suspend()
        assert ctx.context_id in dispatch._contexts  # pyright: ignore[reportPrivateUsage]
    assert ctx.context_id not in dispatch._contexts, "a shut-down context is still in dispatch"  # pyright: ignore[reportPrivateUsage]
    handle.uninstall_capture()


@pytest.mark.needs_sqlalchemy
def test_a_suspended_transactions_hook_records_nothing_while_another_context_keeps_the_listeners():
    """Found by the suspended transactions budget under xdist: the SQL Trace fallback still routed to a context
    whose transactions hook was suspended, once another context kept the shared listeners attached."""
    sa = pytest.importorskip("sqlalchemy")
    from sharpit.engine.capture.transactions import TransactionRecorder

    engine = sa.create_engine("sqlite://")
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    other = install(FastAPI(), enabled="ON", show_banner=False)  # keeps the class listeners attached
    recorder = handle.context.capture.transactions
    assert isinstance(recorder, TransactionRecorder)
    _hook(handle, "transactions").suspend()
    with engine.connect() as connection, connection.begin():
        pass
    recorded = recorder.report([])["totalCaptured"]
    handle.uninstall_capture()
    other.uninstall_capture()
    engine.dispose()
    assert recorded == 0, "a suspended transactions hook still recorded"
