from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.config.profiles import profiles_report
from sharpit.fastapi.routes import json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def profile_diff(_request: Request) -> Response:
        return json_response(profiles_report(ctx))

    return [
        Route(f"{api}/profile-diff", profile_diff, methods=["GET"]),
    ]
