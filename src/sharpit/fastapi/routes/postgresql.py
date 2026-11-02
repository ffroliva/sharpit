"""``GET {api}/postgresql`` (the last read, never connects) and ``POST {api}/postgresql/read`` (BootUI contract §5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.postgresql.service import postgresql_report, refresh_postgresql
from sharpit.engine.singleflight import ActionBusy
from sharpit.fastapi.routes import json_response

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(postgresql_report(ctx))

    async def read(_request: Request) -> Response:
        try:
            return json_response(await refresh_postgresql(ctx))
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    return [
        Route(f"{api}/postgresql", report, methods=["GET"]),
        Route(f"{api}/postgresql/read", read, methods=["POST"]),
    ]
