from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.paging import parse_int_param
from sharpit.engine.sensors.floor import side_effects_report, side_effects_sensor
from sharpit.fastapi.http import json_response
from sharpit.fastapi.routes.java_agent import answer


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(side_effects_report())

    def sensor(request: Request) -> Response:
        query = request.query_params
        offset = parse_int_param(query.get("offset"), "offset")
        limit = parse_int_param(query.get("limit"), "limit")
        return answer(lambda: side_effects_sensor(query.get("sensor"), offset, limit))

    return [
        Route(f"{api}/side-effects", report, methods=["GET"]),
        Route(f"{api}/side-effects/sensor", sensor, methods=["GET"]),
    ]
