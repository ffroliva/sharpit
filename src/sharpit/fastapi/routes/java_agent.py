from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.sensors.floor import SensorRefusal, body_field, java_agent_report, switch_sensor
from sharpit.fastapi import adapter
from sharpit.fastapi.http import error, json_response

PAYLOAD_TOO_LARGE = "Request payload exceeds limit"


def answer(build: Callable[[], dict[str, Any]]) -> Response:
    """The DTO, or BootUI's refusal as ``{"error": message}`` with its status."""
    try:
        return json_response(build())
    except SensorRefusal as refusal:
        return error(refusal.status, refusal.message)


async def read_body(ctx: Any, request: Request) -> bytes | None:
    return await adapter._read_capped(request, ctx.settings.mcp_max_payload_bytes)  # pyright: ignore[reportPrivateUsage]


def build_routes(ctx: Any, _host_app: Any = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def report(_request: Request) -> Response:
        return json_response(java_agent_report())

    async def switch(request: Request) -> Response:
        raw = await read_body(ctx, request)
        if raw is None:
            return error(413, PAYLOAD_TOO_LARGE)
        return answer(
            lambda: switch_sensor(request.path_params["sensor"], body_field(raw, "enabled"), ctx.capture.sensors)
        )

    return [
        Route(f"{api}/java-agent", report, methods=["GET"]),
        Route(f"{api}/java-agent/sensors/{{sensor}}", switch, methods=["POST"]),
    ]
