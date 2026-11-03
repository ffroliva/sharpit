from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.capture.securitylogs import (
    INVALID_AFTER,
    PANEL,
    SecurityEventBuffer,
    context_report,
    parse_after,
)
from sharpit.engine.capture.streams import change_events
from sharpit.engine.paging import parse_int_param
from sharpit.engine.panels import disabled_reason
from sharpit.fastapi.http import error, json_response
from sharpit.fastapi.sse import sse_response


def build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(request: Request) -> Response:
        query = request.query_params
        try:
            after_ns = parse_after(query.get("after"))
        except ValueError:
            return error(400, INVALID_AFTER)  # never the value: it is the caller's text
        return json_response(
            context_report(
                ctx,
                principal=query.get("principal"),
                type=query.get("type"),
                after_ns=after_ns,
                offset=parse_int_param(query.get("offset"), "offset"),
                limit=parse_int_param(query.get("limit"), "limit"),
            )
        )

    def stream(_request: Request) -> Response:
        buffer = ctx.capture.security_logs
        if not isinstance(buffer, SecurityEventBuffer):
            return error(404, disabled_reason(PANEL))
        return sse_response(ctx, change_events(buffer.changes))

    return [
        Route(f"{api}/security-logs", report, methods=["GET"]),
        Route(f"{api}/security-logs/stream", stream, methods=["GET"]),
    ]
