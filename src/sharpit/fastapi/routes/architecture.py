from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.advisors.retention import MAX_PAGE_LIMIT, AdvisorViolationError, parse_integer
from sharpit.engine.collectors.architecture.report import architecture_service
from sharpit.engine.context import SharpitContext
from sharpit.engine.singleflight import ActionBusy
from sharpit.fastapi.routes import json_response


def build_routes(ctx: SharpitContext, host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def architecture_report(_request: Request) -> Response:
        return json_response(architecture_service(ctx, host_app).report())

    def architecture_scan(_request: Request) -> Response:
        try:
            return json_response(architecture_service(ctx, host_app).scan())
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    def architecture_violations(request: Request) -> Response:
        params = request.query_params
        try:
            offset = parse_integer(params.get("offset"), "offset")
            limit = parse_integer(params.get("limit"), "limit")
            page = architecture_service(ctx, host_app).violations(
                request.path_params["rule_id"], params.get("scanId"), offset, limit, MAX_PAGE_LIMIT
            )
        except AdvisorViolationError as exc:
            return json_response({"error": exc.message}, exc.status)
        return json_response(page)

    return [
        Route(f"{api}/architecture", architecture_report, methods=["GET"]),
        Route(f"{api}/architecture/scan", architecture_scan, methods=["POST"]),
        Route(f"{api}/architecture/rules/{{rule_id}}/violations", architecture_violations, methods=["GET"]),
    ]
