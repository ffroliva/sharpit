from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.http import json_response
from sharpit.fastapi.routes.java_agent import answer


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        service = getattr(ctx.capture, "side_effects", None)
        return json_response(
            service.report()
            if service is not None
            else ctx.lazy("side-effects-service", lambda: _unavailable_service(ctx)).report()
        )

    def sensor(request: Request) -> Response:
        query = request.query_params
        offset = parse_int_param(query.get("offset"), "offset")
        limit = parse_int_param(query.get("limit"), "limit")
        service = getattr(ctx.capture, "side_effects", None)
        if service is None:
            service = ctx.lazy("side-effects-service", lambda: _unavailable_service(ctx))
        return answer(lambda: service.sensor(query.get("sensor"), offset, limit))

    return [
        Route(f"{api}/side-effects", report, methods=["GET"]),
        Route(f"{api}/side-effects/sensor", sensor, methods=["GET"]),
    ]


def _unavailable_service(ctx: Any) -> Any:
    from sharpit.engine.collectors.sideeffects.service import SideEffectsService

    return SideEffectsService(ctx.capture, ctx.masker)
