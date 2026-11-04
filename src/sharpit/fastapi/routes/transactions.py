from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.capture.streams import change_events
from sharpit.engine.capture.transactions import TransactionRecorder, context_report
from sharpit.engine.panels import disabled_reason
from sharpit.fastapi import adapter
from sharpit.fastapi.http import error, json_response
from sharpit.fastapi.sse import sse_response

_INVALID_RECORDING_BODY = "Request body must be a JSON object with a boolean or null 'enabled'"


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
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
        raw = await adapter._read_capped(request, max_bytes)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        enabled = adapter._toggle_value(raw)
        if enabled is not None and not isinstance(enabled, bool):
            return error(400, _INVALID_RECORDING_BODY)
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
