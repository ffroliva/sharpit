"""Per-request capture overhead (spec §4, §14.1): the minimum of 5 batches of 2 000 requests to a bare route, capture
on (every panel enabled) against the same install with the four capture panels disabled (no middleware)."""

from __future__ import annotations

import asyncio
import time

from starlette.responses import PlainTextResponse
from starlette.types import Message

from fastapi import FastAPI
from sharpit import install

BATCHES, REQUESTS = 5, 2000
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


def _app(capture: bool) -> FastAPI:
    app = FastAPI()

    @app.get("/bare")
    async def bare() -> PlainTextResponse:  # pyright: ignore[reportUnusedFunction]
        return PlainTextResponse("ok")

    panels = {} if capture else {p: {"enabled": False} for p in CAPTURE_PANELS}
    install(app, enabled="ON", show_banner=False, panels=panels)
    return app


async def _per_request_ns(app: FastAPI) -> float:
    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: Message) -> None:
        return None

    await app(dict(SCOPE), receive, send)  # builds the middleware stack outside the timing
    best = float("inf")
    for _ in range(BATCHES):
        started = time.perf_counter_ns()
        for _ in range(REQUESTS):
            await app(dict(SCOPE), receive, send)
        best = min(best, (time.perf_counter_ns() - started) / REQUESTS)
    return best


def test_request_overhead_budget():
    off, on = (asyncio.run(_per_request_ns(_app(capture))) for capture in (False, True))
    overhead_ms = (on - off) / 1e6
    assert overhead_ms <= 0.2, f"capture adds {overhead_ms:.3f} ms per request (off {off / 1e6:.3f} ms)"
