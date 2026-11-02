from __future__ import annotations

import json
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.capture.streams import change_events
from sharpit.engine.capture.transactions import TransactionRecorder, context_report
from sharpit.engine.panels import disabled_reason
from sharpit.fastapi.http import error, json_response
from sharpit.fastapi.sse import sse_response

_INVALID_RECORDING_BODY = "Request body must be a JSON object with a boolean or null 'enabled'"


async def _read_body(request: Request, max_bytes: int) -> bytes | None:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _recording_value(raw: bytes) -> tuple[bool | None, Response | None]:
    if not raw.strip():
        return None, None
    try:
        parsed: object = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None, error(400, _INVALID_RECORDING_BODY)
    if not isinstance(parsed, dict):
        return None, error(400, _INVALID_RECORDING_BODY)
    value = cast("dict[str, object]", parsed).get("enabled")
    if value is not None and not isinstance(value, bool):
        return None, error(400, _INVALID_RECORDING_BODY)
    return value, None


def build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]
    max_bytes = ctx.settings.mcp_max_payload_bytes

    def transactions(_request: Request) -> Response:
        return json_response(context_report(ctx))

    def clear_transactions(_request: Request) -> Response:
        recorder = ctx.capture.transactions
        if isinstance(recorder, TransactionRecorder):
            recorder.clear()
        return json_response(context_report(ctx))

    async def recording(request: Request) -> Response:
        raw = await _read_body(request, max_bytes)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        enabled, invalid = _recording_value(raw)
        if invalid is not None:
            return invalid
        recorder = ctx.capture.transactions
        if isinstance(recorder, TransactionRecorder):
            recorder.set_recording(not recorder.recording if enabled is None else enabled)
        return json_response(context_report(ctx))

    def stream(_request: Request) -> Response:
        recorder = ctx.capture.transactions
        if not isinstance(recorder, TransactionRecorder):
            return error(404, disabled_reason("transactions"))
        return sse_response(ctx, change_events(recorder.changes))

    return [
        Route(f"{api}/transactions", transactions, methods=["GET"]),
        Route(f"{api}/transactions/clear", clear_transactions, methods=["POST"]),
        Route(f"{api}/transactions/recording", recording, methods=["POST"]),
        Route(f"{api}/transactions/stream", stream, methods=["GET"]),
    ]
