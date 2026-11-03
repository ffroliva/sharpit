from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.tools04.sql_trace import insights
from sharpit.fastapi.http import json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def sql_trace_insights(_request: Request) -> Response:
        return json_response(insights(ctx))

    return [Route(f"{api}/sql-trace/insights", sql_trace_insights, methods=["GET"])]
