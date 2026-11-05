"""``http-exchanges`` 2.2.0 routes (lane D2): the feed with its ``route`` filter and ``GET /http-exchanges/routes``."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine import tools
from sharpit.engine.capture.routes import summarize_http_routes
from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.http import json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def http_exchanges(request: Request) -> Response:
        params = request.query_params
        offset = parse_int_param(params.get("offset"), "offset")
        limit = parse_int_param(params.get("limit"), "limit")
        report = tools.http_exchanges_report(
            ctx, params.get("q"), params.get("method"), params.get("statusClass"), offset, limit, params.get("route")
        )
        return json_response(report)

    def http_routes(request: Request) -> Response:
        params = request.query_params
        limit = parse_int_param(params.get("limit"), "limit")
        return json_response(summarize_http_routes(ctx.capture.exchanges, limit=limit, route=params.get("route")))

    return [
        Route(f"{api}/http-exchanges", http_exchanges, methods=["GET"]),
        Route(f"{api}/http-exchanges/routes", http_routes, methods=["GET"]),
    ]
