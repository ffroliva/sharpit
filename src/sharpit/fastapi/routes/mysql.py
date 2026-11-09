"""``GET {api}/mysql`` (the last read, never connects) and ``POST {api}/mysql/read`` (BootUI contract §6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.mysql.service import mysql_report, refresh_mysql
from sharpit.engine.singleflight import ActionBusy
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(mysql_report(ctx))

    async def read(_request: Request) -> Response:
        try:
            return json_response(await refresh_mysql(ctx))
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    return [
        Route(f"{api}/mysql", report, methods=["GET"]),
        Route(f"{api}/mysql/read", read, methods=["POST"]),
    ]
