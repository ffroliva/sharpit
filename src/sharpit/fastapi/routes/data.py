from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.data import repositories_report, repository_detail
from sharpit.fastapi.routes import json_response, security_headers


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def repositories(_request: Request) -> Response:
        return json_response(repositories_report(ctx))

    def detail(request: Request) -> Response:
        found = repository_detail(ctx, request.path_params["name"])
        if found is None:
            return Response(status_code=404, headers=dict(security_headers("api")))
        return json_response(found)

    return [
        Route(f"{api}/data/repositories", repositories, methods=["GET"]),
        Route(f"{api}/data/repositories/{{name:path}}", detail, methods=["GET"]),
    ]
