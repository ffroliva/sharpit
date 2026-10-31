"""JSON responses with the sharpit API header policy."""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse, Response

from sharpit.engine.headers import security_headers


def json_response(data: Any, status: int = 200) -> Response:
    """``data`` at the root (no envelope), nulls kept, API security and cache headers."""
    return JSONResponse(data, status_code=status, headers=dict(security_headers("api")))


def error(status: int, message: str, **extra: Any) -> Response:
    return json_response({"error": message, **extra}, status)
