"""``GET {api}/fastapi`` (cached, never scans), ``POST {api}/fastapi/scan`` and the rule violations page (WAVE-B §1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute, Route

from sharpit.engine.advisors.retention import MAX_PAGE_LIMIT, AdvisorViolationError, parse_integer
from sharpit.engine.singleflight import ActionBusy
from sharpit.engine.tools04.fastapi import fastapi_service
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(fastapi_service(ctx).report())

    def scan(_request: Request) -> Response:  # sync: Starlette runs it on the threadpool, off the event loop
        try:
            return json_response(fastapi_service(ctx).scan())
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    def violations(request: Request) -> Response:
        params = request.query_params
        try:
            offset = parse_integer(params.get("offset"), "offset")
            limit = parse_integer(params.get("limit"), "limit")
            page = fastapi_service(ctx).violations(
                request.path_params["rule_id"], params.get("scanId"), offset, limit, MAX_PAGE_LIMIT
            )
        except AdvisorViolationError as exc:  # BootUI AdvisorViolationExceptionHandler
            return json_response({"error": exc.message}, exc.status)
        return json_response(page)

    return [
        Route(f"{api}/fastapi", report, methods=["GET"]),
        Route(f"{api}/fastapi/scan", scan, methods=["POST"]),
        Route(f"{api}/fastapi/rules/{{rule_id}}/violations", violations, methods=["GET"]),
    ]
