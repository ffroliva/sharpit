"""Log Tail endpoints, SSE streams and the log-handler wiring (F5, spec §6.1, §7.5, §10, §13.2, §13.3).

Stream cases that need several open streams at once call the ASGI app directly (``TestClient`` buffers a body until
the stream ends); the rest go through ``TestClient`` with ``stream_max_seconds=0.05``.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import logging.config
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient
from uvicorn.config import LOGGING_CONFIG

from conftest import OpenStream, SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.logtail import LINE_KEYS, LogTailBuffer, SharpitLogHandler
from sharpit.engine.capture.streams import StreamSlots
from sharpit.engine.headers import NO_STORE
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import LOG_TAIL_DETACHED_REASON, several_workers
from sharpit.fastapi.sse import TOO_MANY_STREAMS, sse_response

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/log-tail"
STREAM = f"{API}/stream"
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    """A request without lifespan attaches the root handler for good: detach every handle a test made."""
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _handle(app: FastAPI | None = None, **options: Any) -> tuple[FastAPI, SharpitHandle]:
    app = app or FastAPI()
    app.get("/host")(lambda: {})
    handle = install(app, **{"enabled": "ON", "show_banner": False, "stream_max_seconds": 0.05, **options})
    _HANDLES.append(handle)
    return app, handle


def _buffer(handle: SharpitHandle) -> LogTailBuffer:
    buffer = handle.context.capture.log_tail
    assert buffer is not None
    return buffer


def _slots(handle: SharpitHandle) -> StreamSlots:
    slots = handle.context.capture.stream_slots
    assert slots is not None
    return slots


def _log_handler(handle: SharpitHandle) -> SharpitLogHandler:
    wiring = handle.context.capture.wiring
    assert wiring is not None and wiring.log_handler is not None
    return wiring.log_handler


def _attached(handler: logging.Handler) -> list[str]:
    loggers = [logging.root, *(lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger))]
    return sorted(lg.name for lg in loggers if handler in lg.handlers)


def _events(body: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for block in body.split("\n\n"):
        if block.strip():
            fields = dict(line.split(": ", 1) for line in block.split("\n"))
            events.append(fields)
    return events


@contextlib.contextmanager
def bare_root() -> Iterator[logging.Logger]:
    """Root without pytest's handlers meanwhile (``basicConfig`` would be a no-op), put back afterwards.

    Used inside the test body: pytest adds its root handlers per test phase, after fixtures are set up."""
    root = logging.getLogger()
    saved, level = list(root.handlers), root.level
    root.handlers[:] = []
    try:
        yield root
    finally:
        for handler in root.handlers:
            if handler not in saved:
                handler.close()
        root.handlers[:] = saved
        root.setLevel(level)


@pytest.fixture
def uvicorn_logging() -> Iterator[None]:
    """uvicorn's own ``dictConfig``, undone afterwards (every other test sees unconfigured uvicorn loggers)."""
    loggers = [logging.getLogger(n) for n in UVICORN_LOGGERS]
    saved = {lg.name: (list(lg.handlers), lg.propagate, lg.level, lg.disabled) for lg in loggers}
    root = logging.getLogger()
    root_saved = list(root.handlers)
    logging.config.dictConfig(LOGGING_CONFIG)
    try:
        yield
    finally:
        for name, (handlers, propagate, level, disabled) in saved.items():
            lg = logging.getLogger(name)
            lg.handlers[:] = handlers
            lg.propagate, lg.disabled = propagate, disabled
            lg.setLevel(level)
        root.handlers[:] = root_saved


# --- endpoints -----------------------------------------------------------------------------------------------------


def test_shape_keys_match_bootui():
    # BootUI LogLineDto(long timestamp, String level, String logger, String message, String thread)
    app, _ = _handle()
    with _client(app) as client:
        logging.getLogger("host.app").warning("hello %s", "log tail")
        lines = client.get(f"{API}/recent").json()
    line = next(line for line in lines if line["message"] == "hello log tail")
    assert tuple(line) == LINE_KEYS == ("timestamp", "level", "logger", "message", "thread")
    assert (line["level"], line["logger"]) == ("WARNING", "host.app")


def test_recent_oldest_first():
    app, handle = _handle()
    with _client(app) as client:
        for i in range(3):
            logging.getLogger("host.app").warning("line %d", i)
        messages = [line["message"] for line in client.get(f"{API}/recent").json()]
    assert [m for m in messages if m and m.startswith("line ")] == ["line 0", "line 1", "line 2"]
    assert _buffer(handle).recent()[-1]["message"] == "line 2"


def test_stream_replays_then_ends_with_retry():
    app, handle = _handle()
    with _client(app) as client:
        logging.getLogger("host.app").warning("streamed")
        resp = client.get(f"{API}/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert (resp.headers["x-accel-buffering"], resp.headers["cache-control"]) == ("no", NO_STORE)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.text.endswith("retry: 1000\n\n")
    logs = [e for e in _events(resp.text) if e.get("event") == "log"]
    streamed = next(e for e in logs if json.loads(e["data"])["message"] == "streamed")
    nonce = _buffer(handle).boot_nonce
    assert streamed["id"].startswith(f"{nonce}-")
    assert _slots(handle).count == 0


def _ids(client: TestClient, **kw: Any) -> list[str]:
    return [e["id"] for e in _events(client.get(f"{API}/stream", **kw).text) if e.get("event") == "log"]


def test_resume_after_id():
    app, handle = _handle()
    with _client(app) as client:
        for i in range(3):
            logging.getLogger("host.app").warning("resume %d", i)
        ids = _ids(client)
        assert len(ids) >= 3
        assert _ids(client, headers={"Last-Event-ID": ids[-2]}) == ids[-1:]
        assert _ids(client, params={"after": ids[-3]}) == ids[-2:]
        # an automatic reconnect sends Last-Event-ID while the URL still carries the manual ?after=: the header wins
        assert _ids(client, params={"after": ids[0]}, headers={"Last-Event-ID": ids[-1]}) == []
    assert _buffer(handle).boot_nonce in ids[0]


@pytest.mark.parametrize("last", ["0123abcd-2", "garbage", "-", "x-y"])
def test_foreign_nonce_full_replay(last: str):
    app, _ = _handle()
    with _client(app) as client:
        logging.getLogger("host.app").warning("before restart")
        assert _ids(client, headers={"Last-Event-ID": last}) == _ids(client)


def test_21st_stream_503():
    app, handle = _handle()
    slots = _slots(handle)
    assert all(slots.acquire() for _ in range(20))
    client = _client(app)
    resp = client.get(f"{API}/stream")
    assert (resp.status_code, resp.json()) == (503, {"error": TOO_MANY_STREAMS})
    assert resp.headers["cache-control"] == NO_STORE
    slots.release()
    assert client.get(f"{API}/stream").status_code == 200
    assert slots.count == 19


def test_global_cap_mixed_streams():
    app, handle = _handle(stream_max_seconds=30)
    slots = _slots(handle)

    async def ticks() -> AsyncIterator[tuple[str, str | None, str]]:
        while True:
            await asyncio.sleep(1)
            yield "update", None, "{}"

    async def main() -> None:
        logs = [OpenStream(app, STREAM) for _ in range(10)]
        others = [
            OpenStream(sse_response(handle.context, ticks()), STREAM) for _ in range(10)
        ]  # a second panel's streams
        await asyncio.wait_for(asyncio.gather(*(s.started.wait() for s in logs + others)), 5)
        assert slots.count == 20 and {s.status for s in logs + others} == {200}
        extra = OpenStream(app, STREAM)
        await asyncio.wait_for(extra.task, 5)
        assert extra.status == 503
        assert json.loads(b"".join(m.get("body", b"") for m in extra.sent)) == {"error": TOO_MANY_STREAMS}
        others[0].task.cancel()
        await asyncio.gather(others[0].task, return_exceptions=True)
        again = OpenStream(app, STREAM)
        await asyncio.wait_for(again.started.wait(), 5)
        assert again.status == 200
        for stream in [*logs, *others[1:], again]:
            stream.task.cancel()
        await asyncio.gather(*(s.task for s in [*logs, *others, again]), return_exceptions=True)

    asyncio.run(main())
    assert slots.count == 0


def test_slot_released_on_disconnect():
    app, handle = _handle(stream_max_seconds=30)
    buffer = _buffer(handle)

    async def main() -> None:
        stream = OpenStream(app, STREAM)
        await asyncio.wait_for(stream.started.wait(), 5)
        await asyncio.sleep(0.05)
        assert _slots(handle).count == 1 and buffer.stream.subscriber_count == 1
        stream.task.cancel()  # a client disconnect arrives as CancelledError
        await asyncio.gather(stream.task, return_exceptions=True)

    asyncio.run(main())
    assert _slots(handle).count == 0 and buffer.stream.subscriber_count == 0


def test_stream_live_line_delivered():
    app, handle = _handle(stream_max_seconds=30)

    async def main() -> None:
        stream = OpenStream(app, STREAM)
        await asyncio.wait_for(stream.started.wait(), 5)
        _buffer(handle).append({"timestamp": 0, "level": "WARNING", "logger": "x", "message": "live", "thread": "t"})
        for _ in range(100):
            if any(b"live" in m.get("body", b"") for m in stream.sent):
                break
            await asyncio.sleep(0.02)
        stream.task.cancel()
        await asyncio.gather(stream.task, return_exceptions=True)
        body = b"".join(m.get("body", b"") for m in stream.sent).decode()
        assert '"message":"live"' in body and "event: log" in body

    asyncio.run(main())


def test_panel_disabled_stream_403():
    app, _ = _handle(panels={"log-tail": {"enabled": False}})
    assert _client(app).get(f"{API}/stream").status_code == 403


# --- wiring --------------------------------------------------------------------------------------------------------


def test_log_tail_panel_available():
    app, _ = _handle()
    with _client(app) as client:
        panel = next(p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "log-tail")
    assert (panel["available"], panel["unavailableReason"]) == (True, None)


def test_no_lifespan_first_request_attaches_root_handler():
    app, handle = _handle()
    handler = _log_handler(handle)
    assert handler not in logging.root.handlers  # install() leaves root alone
    _client(app).get("/host")
    assert handler in logging.root.handlers
    handle.uninstall_capture()
    assert _attached(handler) == []


def test_shutdown_removes_handler():
    app, handle = _handle()
    handler = _log_handler(handle)
    with _client(app):
        assert handler in logging.root.handlers
    assert _attached(handler) == []


def test_basicconfig_in_startup_still_configures_root():
    stream = io.StringIO()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(stream=stream, format="%(message)s")  # a no-op if root already had a handler
        yield

    app, handle = _handle(FastAPI(lifespan=lifespan))
    with bare_root() as root, _client(app):
        logging.getLogger("host.app").warning("configured")
        assert [type(h).__name__ for h in root.handlers] == ["StreamHandler", "SharpitLogHandler"]
    assert stream.getvalue() == "configured\n"
    assert [line["message"] for line in _buffer(handle).recent()] == ["configured"]


def test_dictconfig_later_marks_unavailable():
    app, handle = _handle()
    with bare_root(), _client(app) as client:
        logging.config.dictConfig({"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}})
        panel = next(p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "log-tail")
        assert (panel["available"], panel["unavailableReason"]) == (False, LOG_TAIL_DETACHED_REASON)
    assert _attached(_log_handler(handle)) == []


@pytest.mark.usefixtures("uvicorn_logging")
def test_handler_added_to_non_propagating_uvicorn_loggers():
    app, handle = _handle()
    handler = _log_handler(handle)
    assert _attached(handler) == ["uvicorn", "uvicorn.access"]  # at install, before any startup
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", "/owners", "1.1", 200)
    assert _buffer(handle).recent()[-1]["message"] == '127.0.0.1:5000 - "GET /owners HTTP/1.1" 200'
    handle.uninstall_capture()
    assert _attached(handler) == []


@pytest.mark.usefixtures("uvicorn_logging")
def test_dictconfig_after_install_reattached_at_startup():
    app, handle = _handle()
    handler = _log_handler(handle)
    logging.config.dictConfig(LOGGING_CONFIG)  # uvicorn.run(app) in the app's module: after install()
    assert _attached(handler) == []
    with _client(app):
        assert _attached(handler) == ["root", "uvicorn", "uvicorn.access"]
    assert _attached(handler) == []


def test_worker_warning_once(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    app, _ = _handle()
    with caplog.at_level(logging.WARNING, logger="sharpit"):
        for _ in range(2):
            with _client(app) as client:
                client.get("/host")
    warnings = [r.getMessage() for r in caplog.records if "several worker processes" in r.getMessage()]
    assert len(warnings) == 1 and "SHARPIT_AUTHENTICATION_TOKEN" in warnings[0], warnings


@pytest.mark.parametrize(
    ("environ", "argv", "expected"),
    [
        ({}, ["uvicorn", "app:app", "--reload"], False),
        ({"WEB_CONCURRENCY": "1"}, ["uvicorn", "app:app"], False),
        ({"WEB_CONCURRENCY": "4"}, ["uvicorn", "app:app"], True),
        ({"WEB_CONCURRENCY": "lots"}, ["uvicorn", "app:app"], False),
        ({"WEB_CONCURRENCY": "²"}, ["uvicorn", "app:app"], False),  # isdigit() but not int()
        ({}, ["uvicorn", "app:app", "--workers", "4"], True),
        ({}, ["uvicorn", "app:app", "--workers=2"], True),
        ({}, ["gunicorn", "-w", "3", "app:app"], True),
        ({}, ["gunicorn", "-w", "1", "app:app"], False),
    ],
)
def test_several_workers(environ: dict[str, str], argv: list[str], expected: bool):
    assert several_workers(environ, argv) is expected


def test_get_log_tail_mcp(no_side_effects: SideEffectGuard):
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        no_side_effects.block_network()
        logging.getLogger("host.app").warning("for the agent password=hunter2")
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_log_tail", "arguments": {}}}
        result = client.post("/sharpit/api/mcp", json=call).json()["result"]
    assert result["isError"] is False, result
    entries = result["structuredContent"]["entries"]
    assert [e["message"] for e in entries if e["logger"] == "host.app"] == ["for the agent password=******"]
    assert no_side_effects.violations == []
