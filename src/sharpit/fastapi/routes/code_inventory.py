from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.paging import parse_int_param
from sharpit.engine.sensors.floor import (
    code_inventory_changes,
    code_inventory_dependencies,
    code_inventory_methods,
    code_inventory_report,
)
from sharpit.fastapi.http import json_response


def _limit(request: Request) -> int | None:
    parse_int_param(request.query_params.get("offset"), "offset")  # validated as BootUI's Integer binding does
    return parse_int_param(request.query_params.get("limit"), "limit")


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(code_inventory_report())

    def changes(request: Request) -> Response:
        return json_response(code_inventory_changes(_limit(request)))

    def methods(request: Request) -> Response:
        return json_response(code_inventory_methods(_limit(request)))

    def dependencies(request: Request) -> Response:
        return json_response(code_inventory_dependencies(_limit(request)))

    return [
        Route(f"{api}/code-inventory", report, methods=["GET"]),
        Route(f"{api}/code-inventory/changes", changes, methods=["GET"]),
        Route(f"{api}/code-inventory/methods", methods, methods=["GET"]),
        Route(f"{api}/code-inventory/dependencies", dependencies, methods=["GET"]),
    ]
