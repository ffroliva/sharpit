"""``GET {api}/mappings/flat`` (port of BootUI ``MappingsService``; contract section 4, spec 8 Mappings)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.context import SharpitContext
from sharpit.engine.paging import paged
from sharpit.engine.spi import RouteInfo


def _rows(route: RouteInfo) -> list[dict[str, Any]]:
    return [
        {
            "method": method,
            "pattern": route.path,
            "handler": route.handler,
            "produces": route.produces,
            "consumes": route.consumes,
        }
        for method in (route.methods or ("ANY",))
    ]


def _normalized_base_path(raw: str) -> str:
    """BootUI's base path: segments joined by single slashes; a root or empty prefix is no prefix."""
    parts = [part for part in raw.strip().split("/") if part]
    return "/" + "/".join(parts) if parts else ""


def _composed_path(base_path: str, pattern: str) -> str:
    if not base_path:
        return pattern
    return base_path if pattern == "/" else base_path + pattern


def mappings_flat(ctx: SharpitContext, q: str | None, offset: int | None, limit: int | None) -> dict[str, Any]:
    # Not memoised: the host may add routes after install, and listing them is cheap and read-only.
    base_path = _normalized_base_path(ctx.introspector.app_info().base_path)
    rows = [row for route in ctx.introspector.routes() for row in _rows(route)]
    rows.sort(key=lambda r: (r["pattern"], r["method"], r["handler"]))
    page, meta = paged(
        rows,
        q,
        offset,
        limit,
        lambda r: (
            r["method"],
            r["pattern"],
            _composed_path(base_path, r["pattern"]),
            r["handler"],
            r["produces"],
            r["consumes"],
        ),
    )
    return {"total": len(rows), "basePath": base_path, "mappings": page, "page": meta}
