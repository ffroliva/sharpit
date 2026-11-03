"""``database-advisor`` routes, exactly BootUI 2.2.0's ``DatabaseAdvisorController``: ``GET`` (the cached report, never
connects), ``POST /scan`` and ``GET /rules/{id}/violations`` (``AdvisorViolationsEndpoint``). BootUI has no changes or
rule-detail route: changes ride in ``violationDetails.changes``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute, Route

from sharpit.engine.advisors.retention import MAX_PAGE_LIMIT, AdvisorViolationError, parse_integer
from sharpit.engine.collectors.database_advisor.report import run_scan
from sharpit.engine.singleflight import ActionBusy
from sharpit.engine.tools04.database_advisor import database_advisor_service
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]
    base = f"{api}/database-advisor"

    def report(_request: Request) -> Response:
        return json_response(database_advisor_service(ctx).report())

    async def scan(_request: Request) -> Response:
        try:
            return json_response(await run_scan(ctx, database_advisor_service(ctx)))
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    def violations(request: Request) -> Response:
        params = request.query_params
        try:
            offset = parse_integer(params.get("offset"), "offset")
            limit = parse_integer(params.get("limit"), "limit")
            page = database_advisor_service(ctx).violations(
                request.path_params["rule_id"], params.get("scanId"), offset, limit, MAX_PAGE_LIMIT
            )
        except AdvisorViolationError as exc:  # BootUI AdvisorViolationExceptionHandler
            return json_response({"error": exc.message}, exc.status)
        return json_response(page)

    return [
        Route(base, report, methods=["GET"]),
        Route(f"{base}/scan", scan, methods=["POST"]),
        Route(f"{base}/rules/{{rule_id}}/violations", violations, methods=["GET"]),
    ]
