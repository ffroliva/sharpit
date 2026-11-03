"""``security`` advisor routes (BootUI ``SecurityController`` + ``AdvisorViolationsEndpoint``)."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.advisors.retention import MAX_PAGE_LIMIT, AdvisorViolationError, parse_integer
from sharpit.engine.singleflight import ActionBusy
from sharpit.engine.tools04.security import security_service
from sharpit.fastapi.http import json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(security_service(ctx).report())

    def scan(_request: Request) -> Response:
        try:
            return json_response(security_service(ctx).scan())
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    def violations(request: Request) -> Response:
        params = request.query_params
        try:
            offset = parse_integer(params.get("offset"), "offset")
            limit = parse_integer(params.get("limit"), "limit")
            page = security_service(ctx).violations(
                request.path_params["rule_id"], params.get("scanId"), offset, limit, MAX_PAGE_LIMIT
            )
        except AdvisorViolationError as exc:  # BootUI AdvisorViolationExceptionHandler
            return json_response({"error": exc.message}, exc.status)
        return json_response(page)

    return [
        Route(f"{api}/security", report, methods=["GET"]),
        Route(f"{api}/security/scan", scan, methods=["POST"]),
        Route(f"{api}/security/rules/{{rule_id}}/violations", violations, methods=["GET"]),
    ]
