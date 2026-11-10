"""Low-footprint status and controls."""

from __future__ import annotations

import gc
from typing import Any, cast

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from sharpit.engine.lowfootprint import LowFootprintService
from sharpit.engine.tools import CallContext
from sharpit.engine.tools_lowfootprint import low_footprint_status
from sharpit.fastapi.routes import error, json_response


def _service(ctx: Any) -> LowFootprintService:
    return ctx.lazy("low-footprint", lambda: LowFootprintService(ctx.capture.hooks))


def _panel_error(ctx: Any, *, action: bool = False) -> Response | None:
    panel = ctx.settings.panels["live-memory"]
    if not panel.enabled:
        return error(404, "Panel is disabled")
    if action and ctx.settings.read_only:
        return error(403, "sharpit is read-only via SHARPIT_READ_ONLY=true")
    if action and panel.read_only:
        return error(403, "Panel is read-only via SHARPIT_PANELS_LIVE_MEMORY_READ_ONLY=true")
    return None


async def _enabled(request: Request) -> bool | Response:
    try:
        raw_body = await request.json()
    except (ValueError, UnicodeDecodeError):
        return error(400, "Invalid request body")
    if not isinstance(raw_body, dict):
        return error(400, "enabled must be a boolean")
    body = cast(dict[str, object], raw_body)
    if not isinstance(body.get("enabled"), bool):
        return error(400, "enabled must be a boolean")
    return cast(bool, body["enabled"])


def _toggle(ctx: Any, request: Request, enabled: bool) -> Response:
    current = _service(ctx)
    call = CallContext(ctx, request.scope)
    if enabled:
        state, changed = current.suspend_with_transition()
        if changed:
            gc.collect()
        result = low_footprint_status(current, state, call, gc_requested=True)
    else:
        result = low_footprint_status(current, current.resume(), call, gc_requested=False)
    return json_response(result)


def build_routes(ctx: Any) -> list[Route]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def status(request: Request) -> Response:
        denied = _panel_error(ctx)
        if denied is not None:
            return denied
        current = _service(ctx)
        return json_response(low_footprint_status(current, current.status(), CallContext(ctx, request.scope)))

    async def toggle(request: Request) -> Response:
        enabled = await _enabled(request)
        if not isinstance(enabled, bool):
            return enabled
        denied = _panel_error(ctx, action=True)
        if denied is not None:
            return denied
        return _toggle(ctx, request, enabled)

    return [
        Route(f"{api}/live-memory/footprint", status, methods=["GET"]),
        Route(f"{api}/live-memory/footprint", toggle, methods=["POST"]),
    ]
