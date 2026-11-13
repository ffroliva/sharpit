"""Cache panel routes: POST /cache/clear."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from sharpit.engine.collectors.cache.clear import CacheClearRequest, CacheService

if TYPE_CHECKING:
    from starlette.requests import Request

    from sharpit.engine.context import SharpitContext


def build_routes(ctx: SharpitContext, _host_app: object = None) -> list[BaseRoute]:
    api = ctx.settings.api_path[len(ctx.settings.path) :]

    def build() -> CacheService:
        return CacheService(None, clear_enabled=ctx.settings.cache_clear_enabled, masker=ctx.masker)

    async def clear_cache(request: Request) -> Response:
        raw = await request.body()
        data: dict[str, Any] | None = None
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data = cast(dict[str, Any], parsed)
            except (ValueError, RecursionError):
                data = None
        clear_req = CacheClearRequest.from_dict(data)

        provider: Any = getattr(ctx, "cache_provider", None) or ctx.peek("cache_provider")
        service = ctx.lazy("cache_service", build)  # one service, so its lock serialises every clear
        service.provider = provider  # resolved per call: a provider registered later is still picked up
        response = await run_in_threadpool(service.clear, clear_req)
        return JSONResponse(status_code=response.status, content=response.body.to_dict())

    return [Route(f"{api}/cache/clear", clear_cache, methods=["POST"])]
