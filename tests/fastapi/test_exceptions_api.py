"""Exceptions endpoints, MCP tools and the three capture sources (F2, spec §6.1 step 2, §7.2, §13.2, §13.3)."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient
from starlette._utils import is_async_callable  # pyright: ignore[reportPrivateUsage]
from starlette.background import BackgroundTasks
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.exceptions import GROUP_KEYS, ExceptionStore
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import WrappingHandlers

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/exceptions"
INVALID = "Invalid status '{}'; expected one of OPEN, ACKNOWLEDGED, RESOLVED"
log = logging.getLogger("host.app")


class MyError(Exception):
    pass


class OtherError(Exception):
    pass


class ThirdError(Exception):
    pass


_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _install(app: FastAPI, **options: Any) -> SharpitHandle:
    handle = install(app, **{"enabled": "ON", "show_banner": False, "stream_max_seconds": 0.05, **options})
    _HANDLES.append(handle)
    return handle


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)


def _store(handle: SharpitHandle) -> ExceptionStore:
    store = handle.context.capture.exceptions
    assert store is not None
    return store


def _groups(client: TestClient) -> list[dict[str, Any]]:
    return client.get(API).json()["groups"]


def _failing_app() -> FastAPI:
    app = FastAPI()

    @app.get("/fail")
    def fail() -> None:  # pyright: ignore[reportUnusedFunction]
        raise MyError("boom")

    return app


# --- sources and dedup ---------------------------------------------------------------------------------------------


def test_unhandled_exception_recorded_from_request():
    app = _failing_app()
    _install(app)
    with _client(app) as client:
        assert client.get("/fail").status_code == 500
        group = _groups(client)[0]
    assert (group["exceptionClassName"], group["message"], group["count"]) == (f"{__name__}.MyError", "boom", 1)
    assert (group["lastSource"], group["lastRequestMethod"], group["lastRequestPath"]) == ("request", "GET", "/fail")
    assert group["lastHandler"] == f"{__name__}:_failing_app.<locals>.fail"
    assert group["applicationException"] is True


def test_three_sources_record_once():
    app = _failing_app()
    seen: list[BaseException] = []

    @app.exception_handler(Exception)
    async def on_error(_request: Request, exc: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        seen.append(exc)
        log.exception("handled", exc_info=exc)  # the log source
        return JSONResponse({"error": "x"}, 500)

    _install(app)
    with _client(app) as client:
        assert client.get("/fail").status_code == 500
        logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=seen[0])  # the server
        groups = _groups(client)
    assert [(g["count"], g["lastSource"]) for g in groups] == [(1, "request")]


def test_handled_exception_recorded_from_handler():
    app = _failing_app()

    @app.exception_handler(MyError)
    def on_my_error(_request: Request, exc: MyError) -> PlainTextResponse:  # pyright: ignore[reportUnusedFunction]
        return PlainTextResponse("handled", 418)

    _install(app)
    with _client(app) as client:
        assert client.get("/fail").status_code == 418
        group = _groups(client)[0]
    assert (group["lastSource"], group["lastRequestPath"], group["count"]) == ("handler", "/fail", 1)
    assert group["lastHandler"] == f"{__name__}:_failing_app.<locals>.fail"


def test_logged_exception_in_request_recorded_from_log():
    app = FastAPI()

    @app.get("/logs")
    def logs() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        try:
            raise OtherError("logged")
        except OtherError:
            log.exception("it failed")
        return {"ok": True}

    handle = _install(app)
    with _client(app) as client:
        assert client.get("/logs").status_code == 200
        group = _groups(client)[0]
        exchange = client.get("/sharpit/api/http-exchanges").json()["exchanges"][0]
    assert (group["lastSource"], group["lastRequestPath"], group["message"]) == ("log", "/logs", "logged")
    assert group["lastTraceId"] == exchange["id"]
    assert _store(handle).report()["totalExceptions"] == 1


def test_wrap_sync_async_partial_handlers():
    app = FastAPI()

    def sync_handler(_request: Request, _exc: Exception) -> PlainTextResponse:
        return PlainTextResponse("sync", 418)

    async def async_handler(_request: Request, _exc: Exception) -> PlainTextResponse:
        return PlainTextResponse("async", 418)

    async def tagged(tag: str, _request: Request, _exc: Exception) -> PlainTextResponse:
        return PlainTextResponse(tag, 418)

    handlers = {MyError: sync_handler, OtherError: async_handler, ThirdError: functools.partial(tagged, "partial")}
    for cls, handler in handlers.items():
        app.add_exception_handler(cls, handler)

        def raiser(cls: type[Exception] = cls) -> None:
            raise cls(cls.__name__)

        app.get(f"/{cls.__name__}")(raiser)
    _install(app)
    wrapped = app.exception_handlers
    assert isinstance(wrapped, WrappingHandlers)
    for cls, original in handlers.items():
        assert wrapped[cls] is not original and is_async_callable(wrapped[cls]) == is_async_callable(original)
    with _client(app) as client:
        bodies = [client.get(f"/{cls.__name__}").text for cls in handlers]
        groups = _groups(client)
    assert bodies == ["sync", "async", "partial"]
    assert sorted(g["message"] for g in groups) == ["MyError", "OtherError", "ThirdError"]
    assert {g["lastSource"] for g in groups} == {"handler"}


def test_handler_registered_after_install_wrapped():
    app = _failing_app()
    _install(app)

    @app.exception_handler(MyError)
    async def late(_request: Request, _exc: MyError) -> PlainTextResponse:  # pyright: ignore[reportUnusedFunction]
        return PlainTextResponse("late", 418)

    with _client(app) as client:
        assert client.get("/fail").text == "late"
        assert [g["lastSource"] for g in _groups(client)] == ["handler"]


def test_uninstall_restores_plain_handlers_dict():
    app = _failing_app()

    async def original(_request: Request, _exc: Exception) -> PlainTextResponse:
        return PlainTextResponse("original", 418)

    app.add_exception_handler(MyError, original)
    handle = _install(app)
    with _client(app) as client:
        client.get("/fail")
        handle.uninstall_capture()
        assert type(app.exception_handlers) is dict and app.exception_handlers[MyError] is original
        assert client.get("/fail").text == "original"  # the built stack keeps the wrapper: it passes through
    assert _store(handle).report()["totalExceptions"] == 1


def test_handler_wrapper_failure_still_calls_original(caplog: pytest.LogCaptureFixture):
    app = _failing_app()
    app.add_exception_handler(MyError, lambda _r, _e: PlainTextResponse("still handled", 418))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    handle = _install(app)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("store failed")

    _store(handle).record = broken  # type: ignore[method-assign]
    with _client(app) as client:
        assert [client.get("/fail").text for _ in range(2)] == ["still handled"] * 2
    warnings = [r.getMessage() for r in caplog.records if r.name == "sharpit" and r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "exception handler" in warnings[0], warnings


def test_custom_404_handler_unwrapped():
    app = FastAPI()

    async def not_found(_request: Request, _exc: Exception) -> PlainTextResponse:
        return PlainTextResponse("custom 404", 404)

    app.add_exception_handler(404, not_found)
    _install(app)
    assert app.exception_handlers[404] is not_found
    with _client(app) as client:
        assert client.get("/missing").text == "custom 404"
        assert _groups(client) == []


def test_http_exception_handler_unwrapped():
    app = FastAPI()
    before = dict(app.exception_handlers)

    @app.get("/teapot")
    def teapot() -> None:  # pyright: ignore[reportUnusedFunction]
        raise HTTPException(418)

    @app.get("/invalid")
    def invalid(n: int) -> int:  # pyright: ignore[reportUnusedFunction]
        return n

    _install(app)
    assert all(app.exception_handlers[k] is v for k, v in before.items())  # HTTPException, validation errors
    with _client(app) as client:
        assert client.get("/teapot").status_code == 418
        assert client.get("/invalid?n=x").status_code == 422
        assert _groups(client) == []


def test_cancelled_error_never_recorded():
    app = FastAPI()

    @app.get("/cancel")
    async def cancel() -> None:  # pyright: ignore[reportUnusedFunction]
        raise asyncio.CancelledError

    handle = _install(app)
    with _client(app) as client, contextlib.suppress(asyncio.CancelledError):  # the transport may re-raise it
        client.get("/cancel")
    assert _store(handle).report()["totalExceptions"] == 0


def _as_uvicorn(app: Any) -> Any:
    """Log an escaped exception as uvicorn's ``run_asgi`` does: outside the request, after the middleware is done."""

    async def server(scope: Any, receive: Any, send: Any) -> None:
        try:
            await app(scope, receive, send)
        except Exception as exc:
            logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=exc)
            raise

    return server


def test_mid_stream_exception_recorded_once():
    app = FastAPI()

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first"
        raise MyError("mid-stream")

    @app.get("/stream")
    def stream() -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        return StreamingResponse(chunks())

    handle = _install(app)
    with _client(_as_uvicorn(app)) as client:
        with contextlib.suppress(Exception):  # the transport may surface the broken body; recording is what counts
            client.get("/stream")
        group = _groups(client)[0]
        exchange = client.get("/sharpit/api/http-exchanges").json()["exchanges"][0]
    assert (group["count"], group["lastSource"], group["lastTraceId"]) == (1, "request", exchange["id"])
    assert exchange["status"] == 200  # the status that went out stays
    assert _store(handle).report()["totalExceptions"] == 1


def test_background_task_exception_recorded_with_request_id():
    app = FastAPI()

    def job() -> None:
        raise OtherError("in the background")

    @app.get("/later")
    def later(tasks: BackgroundTasks) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        tasks.add_task(job)
        return {"ok": True}

    _install(app)
    with _client(app) as client:
        client.get("/later")
        group = _groups(client)[0]
        exchange = client.get("/sharpit/api/http-exchanges").json()["exchanges"][0]
    assert (group["message"], group["lastTraceId"], group["lastRequestPath"]) == (
        "in the background",
        exchange["id"],
        "/later",
    )


# --- endpoints -------------------------------------------------------------------------------------------------------


def _one_group() -> tuple[FastAPI, SharpitHandle, TestClient, str]:
    app = _failing_app()
    handle = _install(app)
    client = _client(app)
    client.get("/fail")
    return app, handle, client, _groups(client)[0]["id"]


def test_shape_keys_match_bootui():
    # ported: ExceptionsReport, ExceptionGroupDto, ExceptionDetailDto, ExceptionFrameDto, ExceptionOccurrenceDto
    _, _, client, gid = _one_group()
    report = client.get(API).json()
    assert tuple(report) == ("available", "unavailableReason", "maxGroups", "totalExceptions", "groups")
    assert (report["available"], report["unavailableReason"], report["maxGroups"]) == (True, None, 100)
    assert tuple(report["groups"][0]) == GROUP_KEYS == (
        "id", "exceptionClassName", "message", "count", "firstSeen", "lastSeen", "location", "applicationException",
        "lastThread", "lastRequestMethod", "lastRequestPath", "lastHandler", "lastSource", "lastTraceId", "status",
        "regressionCount", "errorContract",
    )  # fmt: skip
    detail = client.get(f"{API}/{gid}").json()
    assert tuple(detail) == ("group", "frames", "causes", "occurrences")
    assert tuple(detail["group"]) == GROUP_KEYS
    assert tuple(detail["frames"][0]) == ("declaringClass", "methodName", "fileName", "lineNumber", "applicationFrame")
    assert tuple(detail["occurrences"][0]) == (
        "timestamp", "thread", "requestMethod", "requestPath", "handler", "source", "traceId",
    )  # fmt: skip


def test_unknown_id_404():
    _, _, client, _ = _one_group()
    for resp in (client.get(f"{API}/nope"), client.post(f"{API}/nope/status", json={"status": "RESOLVED"})):
        assert (resp.status_code, resp.json()) == (404, {"error": "Unknown exception group 'nope'"})


@pytest.mark.parametrize(
    ("content", "shown"),
    [(b"", "null"), (b'{"status": "CLOSED"}', "CLOSED"), (b"{}", "null"), (b"not json", "null"), (b"[1]", "null")],
    ids=["empty", "unknown", "missing", "not-json", "not-object"],
)
def test_empty_status_body_400(content: bytes, shown: str):
    _, _, client, gid = _one_group()
    resp = client.post(f"{API}/{gid}/status", content=content, headers={"content-type": "application/json"})
    assert (resp.status_code, resp.json()) == (400, {"error": INVALID.format(shown)})
    assert client.post(f"{API}/nope/status", content=content).status_code == 400  # checked before the group


def test_status_update_and_case():
    _, _, client, gid = _one_group()
    resp = client.post(f"{API}/{gid}/status", json={"status": "resolved"})
    assert resp.status_code == 200 and tuple(resp.json()) == GROUP_KEYS
    assert resp.json()["status"] == "RESOLVED" and _groups(client)[0]["status"] == "RESOLVED"


def test_delete_204():
    _, _, client, _ = _one_group()
    resp = client.delete(API)
    assert (resp.status_code, resp.content) == (204, b"")
    assert resp.headers["cache-control"] == "no-store, must-revalidate"
    assert _groups(client) == []


@pytest.mark.parametrize("scope", ["global", "panel"])
def test_status_post_refused_read_only(scope: str):
    app = _failing_app()
    options = {"read_only": True} if scope == "global" else {"panels": {"exceptions": {"read_only": True}}}
    handle = _install(app, **options)
    client = _client(app)
    client.get("/fail")
    gid = _groups(client)[0]["id"]
    assert client.post(f"{API}/{gid}/status", json={"status": "RESOLVED"}).status_code == 403
    assert client.delete(API).status_code == 403
    assert _store(handle).report()["groups"][0]["status"] == "OPEN"


def test_exceptions_stream_route_not_shadowed():
    _, _, client, _ = _one_group()
    resp = client.get(f"{API}/stream")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
    assert resp.text.endswith("retry: 1000\n\n")


def test_exceptions_panel_available():
    _, _, client, _ = _one_group()
    panel = next(p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "exceptions")
    assert (panel["available"], panel["unavailableReason"]) == (True, None)


def test_disabled_panel_has_no_store_and_wraps_nothing():
    app = _failing_app()
    before = app.exception_handlers
    handle = _install(app, panels={"exceptions": {"enabled": False}})
    assert handle.context.capture.exceptions is None and app.exception_handlers is before
    assert _client(app).get(API).status_code == 403


# --- MCP and CLI ---------------------------------------------------------------------------------------------------


def _rpc(client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return client.post("/sharpit/api/mcp", json=call).json()


def test_get_exceptions_mcp_no_side_effects(no_side_effects: SideEffectGuard):
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        no_side_effects.block_network()
        try:
            raise MyError("for the agent password=hunter2")
        except MyError:
            log.exception("seen by the agent")
        listed = _rpc(client, "get_exceptions", {})["result"]
        gid = listed["structuredContent"]["groups"][0]["id"]
        detail = _rpc(client, "get_exception_detail", {"id": f"  {gid}  "})["result"]
        unknown = _rpc(client, "get_exception_detail", {"id": "does-not-exist"})
        missing = _rpc(client, "get_exception_detail", {})
        wrong = _rpc(client, "get_exception_detail", {"id": 1})
    app.state.sharpit.uninstall_capture()
    assert listed["isError"] is False and listed["structuredContent"]["groups"][0]["message"] == (
        "for the agent password=******"
    )
    assert detail["isError"] is False and detail["structuredContent"]["group"]["id"] == gid
    # ported: AbstractMcpConformanceTest.testMcpToolClientErrorIsReportedInBandInsteadOfInternalError
    assert "error" not in unknown and unknown["result"]["isError"] is True
    assert unknown["result"]["content"][0]["text"] == "Unknown exception group 'does-not-exist'"
    assert missing["error"] == {"code": -32602, "message": "Missing required argument: id"}
    assert wrong["error"] == {"code": -32602, "message": "Argument 'id' must be a string"}
    assert no_side_effects.violations == []


def test_clear_exceptions_cli_only():
    app = _failing_app()
    handle = _install(app, cli_enabled=True, mcp_enabled="ON")
    client = _client(app)
    client.get("/fail")
    tools = client.post("/sharpit/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
    assert "clear_exceptions" not in [t["name"] for t in tools["result"]["tools"]]
    assert _rpc(client, "clear_exceptions", {})["error"]["message"] == "Unknown tool: clear_exceptions"
    resp = client.post("/sharpit/api/cli/tools/clear_exceptions", json={})
    assert (resp.status_code, resp.json()) == (200, {"cleared": True})
    assert _store(handle).report()["totalExceptions"] == 0
