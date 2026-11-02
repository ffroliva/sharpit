from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.sqlastats import statistics_report
from sharpit.fastapi.http import json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(statistics_report(ctx))

    return [
        Route(f"{api}/sqlalchemy-statistics", report, methods=["GET"]),
        Route(f"{api}/sqlalchemy-statistics/enable", report, methods=["POST"]),  # always on: nothing to enable
    ]
