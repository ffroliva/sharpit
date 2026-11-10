"""Low-footprint status and controls."""

from __future__ import annotations

from typing import Any, cast

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from sharpit.engine.tools import CallContext, cli_invoke
from sharpit.fastapi.routes import error, json_response


def build_routes(ctx: Any) -> list[Route]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def status(_request: Request) -> Response:
        status_code, body = cli_invoke(CallContext(ctx, _request.scope), "get_low_footprint", {})
        return json_response(body) if status_code == 200 else error(status_code, body["error"])

    async def toggle(request: Request) -> Response:
        try:
            raw_body = await request.json()
        except (ValueError, UnicodeDecodeError):
            return error(400, "Invalid request body")
        if not isinstance(raw_body, dict):
            return error(400, "enabled must be a boolean")
        body = cast(dict[str, object], raw_body)
        if not isinstance(body.get("enabled"), bool):
            return error(400, "enabled must be a boolean")
        name = "enable_low_footprint" if body["enabled"] else "disable_low_footprint"
        call_status, result = cli_invoke(CallContext(ctx, request.scope), name, {})
        if call_status != 200:
            return error(call_status, result["error"])
        status_code, result = cli_invoke(CallContext(ctx, request.scope), "get_low_footprint", {})
        return json_response(result) if status_code == 200 else error(status_code, result["error"])

    return [
        Route(f"{api}/live-memory/footprint", status, methods=["GET"]),
        Route(f"{api}/live-memory/footprint", toggle, methods=["POST"]),
    ]
