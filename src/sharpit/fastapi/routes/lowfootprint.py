"""Low-footprint status and controls."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from sharpit.engine.tools import CallContext, ToolCallError, call_tool
from sharpit.fastapi.routes import error, json_response


def build_routes(ctx: Any) -> list[Route]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def status(_request: Request) -> Response:
        try:
            body = call_tool(CallContext(ctx, _request.scope), "get_low_footprint", {}, via="cli")
        except ToolCallError as exc:
            return error(exc.status, exc.message)
        return json_response(body)

    async def toggle(request: Request) -> Response:
        action = request.path_params["action"]
        if action not in {"enable", "disable"}:
            return error(404, "Not found")
        name = "enable_low_footprint" if action == "enable" else "disable_low_footprint"
        try:
            result = call_tool(CallContext(ctx, request.scope), name, {}, via="cli")
        except ToolCallError as exc:
            return error(exc.status, exc.message)
        return json_response(result)

    return [
        Route(f"{api}/low-footprint", status, methods=["GET"]),
        Route(f"{api}/low-footprint/{{action}}", toggle, methods=["POST"]),
    ]
