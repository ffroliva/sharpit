"""Read-only ``GET {api}/github`` route."""

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

    return [Route(f"{api}/github", report, methods=["GET"])]
