from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine import otel
from sharpit.engine.capture.traces import span_buffer
from sharpit.engine.headers import security_headers
from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.capture import HOOK_TRACES
from sharpit.fastapi.http import error, json_response

DEFAULT_LIMIT = 100


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]
    buffer = span_buffer(ctx)
    if settings.panels["traces"].enabled:
        # armed at lifespan startup (or the first request without a lifespan), disarmed by its teardown at shutdown;
        # install's own attach pass ran before the routes were built, so this is the earliest chance
        if ctx.capture.wiring is not None:
            ctx.capture.wiring.add_lane(ctx, HOOK_TRACES, buffer.arm)
            ctx.capture.wiring.span_processor = otel.PROCESSOR
        else:
            ctx.capture.attachers.append(buffer.arm)

    def traces(request: Request) -> Response:
        buffer.root_path = request.scope.get("root_path", "")
        if request.method == "DELETE":
            buffer.clear()
            return Response(status_code=204, headers=dict(security_headers("api")))
        limit = parse_int_param(request.query_params.get("limit"), "limit")
        return json_response(buffer.list(DEFAULT_LIMIT if limit is None else limit))

    def trace_detail(request: Request) -> Response:
        buffer.root_path = request.scope.get("root_path", "")
        trace_id: str = request.path_params["id"]
        detail = buffer.detail(trace_id)
        return json_response(detail) if detail is not None else error(404, f"trace {trace_id} not found")

    return [
        Route(f"{api}/traces", traces, methods=["GET", "DELETE"]),
        Route(f"{api}/traces/{{id}}", trace_detail, methods=["GET"]),
    ]
