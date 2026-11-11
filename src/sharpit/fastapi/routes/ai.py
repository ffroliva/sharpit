from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.capture.traces import span_buffer
from sharpit.engine.collectors.ai import ai_chat_detail, ai_chats, ai_overview, ai_settings, ai_tokens
from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.http import error, json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]
    buffer = span_buffer(ctx)
    ai = ai_settings(settings)

    def overview(_request: Request) -> Response:
        return json_response(ai_overview(buffer, ai))

    def chats(request: Request) -> Response:
        limit = parse_int_param(request.query_params.get("limit"), "limit")
        return json_response(ai_chats(buffer, limit))

    def chat_detail(request: Request) -> Response:
        span_id = request.path_params["spanId"]
        detail = ai_chat_detail(buffer, span_id, ctx.masker, ai)
        return json_response(detail) if detail is not None else error(404, f"chat span {span_id} not found")

    def tokens(request: Request) -> Response:
        minutes = parse_int_param(request.query_params.get("minutes"), "minutes")
        return json_response(ai_tokens(buffer, minutes, ai, time.time_ns()))

    return [
        Route(f"{api}/ai/overview", overview, methods=["GET"]),
        Route(f"{api}/ai/chats", chats, methods=["GET"]),
        Route(f"{api}/ai/chats/{{spanId}}", chat_detail, methods=["GET"]),
        Route(f"{api}/ai/tokens", tokens, methods=["GET"]),
    ]
