"""REST API pagination rule checks."""

from __future__ import annotations

from sharpit.engine.collectors.restapi.rules_common import PAGING_PARAMS, Check, each, shared_is_collection
from sharpit.engine.spi import ApiRouteInfo


def _page001(route: ApiRouteInfo) -> str | None:
    if "GET" not in route.methods or not shared_is_collection(route):
        return None
    if PAGING_PARAMS & {p.lower() for p in route.query_params}:
        return None
    return "collection response without limit/offset/page/cursor parameters"


CHECKS: dict[str, Check] = {
    "RAPI-PAGE-001": each(_page001),
}
