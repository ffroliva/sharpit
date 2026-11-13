"""``GET {api}/runtime-insights``, ``/insights/{id}`` and ``/resource-profile`` with its two POSTs (BootUI
``RuntimeInsightsController``). The GETs read what the journal holds; the POSTs are the panel's only actions and, behind
the guard chain's panel gates (read-only is refused before a handler runs), answer the floor, which starts nothing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.insights.profile import resource_profile
from sharpit.engine.collectors.insights.service import insights_service
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :] + "/runtime-insights"

    def report(_request: Request) -> Response:
        return json_response(insights_service(ctx).report())

    def insight(request: Request) -> Response:
        return json_response(insights_service(ctx).insight(request.path_params["observation_id"]))

    def status(_request: Request) -> Response:
        return json_response(resource_profile(ctx).status())

    def start(_request: Request) -> Response:
        return json_response(resource_profile(ctx).start())

    def stop(_request: Request) -> Response:
        return json_response(resource_profile(ctx).stop())

    return [
        Route(api, report, methods=["GET"]),
        Route(f"{api}/insights/{{observation_id}}", insight, methods=["GET"]),
        Route(f"{api}/resource-profile", status, methods=["GET"]),
        Route(f"{api}/resource-profile", start, methods=["POST"]),
        Route(f"{api}/resource-profile/stop", stop, methods=["POST"]),
    ]
