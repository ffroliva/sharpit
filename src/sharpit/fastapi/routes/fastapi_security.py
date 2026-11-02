from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.appsecurity import endpoints_report, explain, model_of, security_report
from sharpit.fastapi.http import error, json_response

MAX_PATH = 2048


def build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(security_report(model_of(ctx)))

    def endpoints(_request: Request) -> Response:
        return json_response(endpoints_report(model_of(ctx)))

    def explain_route(request: Request) -> Response:
        method = request.query_params.get("method") or "GET"
        path = request.query_params.get("path") or "/"
        if not path.startswith("/") or len(path) > MAX_PATH:
            return error(400, "Invalid request")
        return json_response(explain(model_of(ctx), method.upper(), path, settings.path))

    return [
        Route(f"{api}/fastapi-security", report, methods=["GET"]),
        Route(f"{api}/fastapi-security/explain", explain_route, methods=["GET"]),
        Route(f"{api}/fastapi-security/endpoints", endpoints, methods=["GET"]),
    ]
