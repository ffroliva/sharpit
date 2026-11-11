from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.startup import startup_report
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(startup_report(ctx))

    return [Route(f"{api}/startup", report, methods=["GET"])]
