"""Security-logs hook overhead: what the enabled panel adds to a 200 request (only a status compare on the hot path).

Both sides install the capture middleware; only the ``security-logs`` panel differs, so the difference is the hook.
How to read a failure: docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import asyncio
import time

from starlette.responses import PlainTextResponse
from starlette.types import Message
from tests.overhead import check_budget, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.securitylogs import SecurityEventBuffer
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import wiring_of

BUDGET_NS = 2_000
ROUNDS, REQUESTS = 10, 1000
SCOPE = {
    "type": "http",
    "asgi": {"version": "3.0"},
    "http_version": "1.1",
    "method": "GET",
    "scheme": "http",
    "path": "/bare",
    "raw_path": b"/bare",
    "root_path": "",
    "query_string": b"",
    "headers": [(b"host", b"localhost"), (b"user-agent", b"bench"), (b"accept", b"*/*")],
    "client": ("127.0.0.1", 50000),
    "server": ("localhost", 80),
}


def _app(security_logs: bool) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()

    @app.get("/bare")
    async def bare() -> PlainTextResponse:  # pyright: ignore[reportUnusedFunction]
        return PlainTextResponse("ok")

    panels = {} if security_logs else {"security-logs": {"enabled": False}}
    return app, install(app, enabled="ON", show_banner=False, config_scan=False, panels=panels)


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(_message: Message) -> None:
    return None


async def _round_ns(app: FastAPI) -> float:
    started = time.perf_counter_ns()
    for _ in range(REQUESTS):
        await app(dict(SCOPE), _receive, _send)
    return (time.perf_counter_ns() - started) / REQUESTS


def test_security_logs_hook_overhead_budget() -> None:
    (off_app, off_handle), (on_app, on_handle) = _app(False), _app(True)
    loop = asyncio.new_event_loop()
    try:
        for app in (off_app, on_app):
            loop.run_until_complete(app(dict(SCOPE), _receive, _send))  # builds the middleware stack outside the timing
        result = paired(
            lambda: loop.run_until_complete(_round_ns(off_app)),
            lambda: loop.run_until_complete(_round_ns(on_app)),
            ROUNDS,
        )
    finally:
        loop.close()
        off_handle.uninstall_capture()
        on_handle.uninstall_capture()
    on_wiring, off_wiring = wiring_of(on_handle.context), wiring_of(off_handle.context)
    assert on_wiring is not None, "the on side has capture wiring"
    assert off_wiring is not None, "the off side has capture wiring"
    assert on_wiring.on_security_event is not None, "the on side measures the attached hook"
    assert off_wiring.on_security_event is None, "the off side runs without the hook"
    assert isinstance(on_handle.context.capture.security_logs, SecurityEventBuffer), "the on side has the buffer"
    check_budget("security-logs hook per request", result, BUDGET_NS, "µs", 1000)
