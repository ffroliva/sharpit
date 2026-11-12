"""``POST {api}/config/overrides`` and ``DELETE {api}/config/overrides/{name}`` (BootUI ``ConfigController``).

The guard has already applied activation, the guard chain, the panel gate and read-only (``config`` is
action-capable). REST only: BootUI has no MCP or CLI tool for these. Every refusal of the override layer is a 400
with its own fixed message (never the offending text); a write failure is BootUI's 500 message; nothing else escapes.
"""

from __future__ import annotations

import json
import logging
from importlib import import_module
from typing import Any, cast

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.config.overrides import ConfigOverrideResult, override_service
from sharpit.engine.context import SharpitContext
from sharpit.fastapi.http import error, json_response

logger = logging.getLogger("sharpit.config.overrides")

BODY_CAP = 128 * 1024  # a 64 KiB value, JSON-escaped, plus the name; larger is a 413 before any parsing
_NOT_OBJECT = "Request body must be a JSON object"


def _checked(raw: bytes) -> tuple[str, object] | str:
    """``(name, value)`` of a valid body, else the 400 message. Strict JSON types: no truthiness, no coercion."""
    try:
        body: object = json.loads(raw) if raw.strip() else None
    except (ValueError, RecursionError):
        return _NOT_OBJECT
    if not isinstance(body, dict):
        return _NOT_OBJECT
    fields = cast("dict[str, object]", body)
    name, value, persist = fields.get("name"), fields.get("value"), fields.get("persist")
    if name is None:
        return "'name' must be provided"
    if not isinstance(name, str):
        return "'name' must be a string"
    if not isinstance(value, str | None):
        return "'value' must be a string"
    if not isinstance(persist, bool | None):
        return "'persist' must be a boolean"
    return name, value


def build_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]
    adapter = cast(Any, import_module("sharpit.fastapi.adapter"))  # resolved per call: tests patch _read_capped

    async def apply(change: Any) -> Response:
        try:
            result: ConfigOverrideResult = await run_in_threadpool(change)
        except ValueError as exc:  # the layer's refusals (RefusedNameError included); their messages quote no input
            return error(400, str(exc))
        except RuntimeError as exc:  # the write failure: BootUI's fixed "Unable to write ..." message
            return error(500, str(exc))
        except Exception:
            logger.exception("config override failed")
            return error(500, "Unable to apply the configuration override")
        return json_response(result.to_dto())

    async def put(request: Request) -> Response:
        content_type = request.headers.get("content-type", "")
        if content_type.partition(";")[0].strip().lower() != "application/json":
            return error(415, "Unsupported Media Type")
        raw = await adapter._read_capped(request, BODY_CAP)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        checked = _checked(raw)
        if isinstance(checked, str):
            return error(400, checked)
        name, value = checked
        return await apply(lambda: override_service(ctx).put(name, value))

    async def delete(request: Request) -> Response:
        name = request.path_params["name"]
        return await apply(lambda: override_service(ctx).remove(name))

    return [
        Route(f"{api}/config/overrides", put, methods=["POST"]),
        Route(f"{api}/config/overrides/{{name}}", delete, methods=["DELETE"]),
    ]
