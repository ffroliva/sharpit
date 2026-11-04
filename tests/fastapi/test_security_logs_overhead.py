"""Security-logs hook cost on a 200 request: none, by construction. The hook is reached only for a 401 or 403.

The wall-clock budget that used to live here measured zero (docs/development/overhead-budgets.md, "Removed budgets"),
so this file keeps the structural guarantee: a 200 enters no security-logs code, a 401 does.
"""

from __future__ import annotations

import asyncio
import sys
import types

from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.types import Message

from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.adapter import SharpitHandle

REQUESTS = 10
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


def _lane_calls(app: FastAPI, loop: asyncio.AbstractEventLoop, path: str) -> list[str]:
    """Every function entered in engine/capture/securitylogs.py during one round of requests to ``path``."""
    seen: list[str] = []

    def profile(frame: types.FrameType, event: str, _arg: object) -> None:
        if event == "call" and frame.f_code.co_filename.endswith("securitylogs.py"):
            seen.append(frame.f_code.co_name)

    scope = {**SCOPE, "path": path, "raw_path": path.encode()}

    async def one_round() -> None:
        for _ in range(REQUESTS):
            await app(dict(scope), _receive, _send)

    sys.setprofile(profile)
    try:
        loop.run_until_complete(one_round())
    finally:
        sys.setprofile(None)
    return seen


def test_200_request_runs_no_security_logs_code() -> None:
    app, handle = _app(True)

    @app.get("/denied")
    async def denied() -> None:  # pyright: ignore[reportUnusedFunction]
        raise HTTPException(401)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(app(dict(SCOPE), _receive, _send))  # builds the middleware stack first
        on_200 = _lane_calls(app, loop, "/bare")
        on_401 = _lane_calls(app, loop, "/denied")
    finally:
        loop.close()
        handle.uninstall_capture()
    assert on_200 == [], "a 200 runs no security-logs code (only the capture middleware's status compare)"
    assert "hook" in on_401, "a 401 enters the security-logs hook, so the counter sees lane code"
