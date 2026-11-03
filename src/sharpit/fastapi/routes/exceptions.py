"""``exceptions`` 2.2.0 route (lane D2): ``GET /exceptions/caught``, ahead of ``/exceptions/{id}``."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.capture.exceptions import caught_report
from sharpit.fastapi.http import json_response


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def caught(_request: Request) -> Response:
        return json_response(caught_report())

    return [Route(f"{api}/exceptions/caught", caught, methods=["GET"])]
