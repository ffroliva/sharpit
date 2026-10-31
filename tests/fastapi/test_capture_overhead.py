"""Per-request capture overhead (spec §4, §14.1): rounds of 1 000 requests to a bare route, capture on (every panel
enabled) against the same install with the four capture panels disabled (no middleware). The two sides alternate
(`tests/overhead.py`), so a busy machine slows both alike. How to read a failure: docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import asyncio
import time

from starlette.responses import PlainTextResponse
from starlette.types import Message
from tests.overhead import check_budget, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.adapter import SharpitHandle

BUDGET_MS = 0.2
ROUNDS, REQUESTS = 10, 1000
CAPTURE_PANELS = ("http-exchanges", "exceptions", "sql-trace", "activity")
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


def _app(capture: bool) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()

    @app.get("/bare")
    async def bare() -> PlainTextResponse:  # pyright: ignore[reportUnusedFunction]
        return PlainTextResponse("ok")

    panels = {} if capture else {p: {"enabled": False} for p in CAPTURE_PANELS}
    return app, install(app, enabled="ON", show_banner=False, panels=panels)


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(_message: Message) -> None:
    return None


async def _round_ns(app: FastAPI) -> float:
    started = time.perf_counter_ns()
    for _ in range(REQUESTS):
        await app(dict(SCOPE), _receive, _send)
    return (time.perf_counter_ns() - started) / REQUESTS


def test_request_overhead_budget():
    (off_app, _), (on_app, on_handle) = _app(False), _app(True)
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
    exchanges = on_handle.context.capture.exchanges
    assert exchanges is not None
    assert exchanges.report(None, None, None, None, None)["total"] > 0, "capture never ran: the number means nothing"
    check_budget("capture per request", result, BUDGET_MS * 1e6, "ms", 1e6)
