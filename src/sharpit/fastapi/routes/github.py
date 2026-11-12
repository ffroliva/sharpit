"""``GET {api}/github`` (local state only) and the REST-only ``POST {api}/github/refresh`` action.

The guard refuses the POST when the panel is disabled or read-only before this handler runs. The handler is sync, so
Starlette runs the bounded network refresh in its threadpool. BootUI has no single-flight on this action.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute, Route

from sharpit.engine.tools04.github import github_dashboard
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request):
        return json_response(github_dashboard(ctx).dashboard())

    def refresh(_request: Request):
        return json_response(github_dashboard(ctx).refresh())

    return [
        Route(f"{api}/github", report, methods=["GET"]),
        Route(f"{api}/github/refresh", refresh, methods=["POST"]),
    ]
