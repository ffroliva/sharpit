"""REST API dto rule checks."""

from __future__ import annotations

from sharpit.engine.collectors.restapi.rules_common import (
    UNTYPED,
    Check,
    each,
    shared_origin,
    shared_persistence_class,
    shared_response_type,
)
from sharpit.engine.spi import ApiRouteInfo


def _dto001(route: ApiRouteInfo) -> str | None:
    cls = shared_persistence_class(route)
    return f"returns persistence class {cls.__name__}" if cls is not None else None


def _dto002(route: ApiRouteInfo) -> str | None:
    if route.dynamic_response or route.status_code in (204, 304):
        return None
    tp = shared_response_type(route)
    if tp is None:
        return "no response model or return annotation"
    return "untyped response body" if any(shared_origin(tp) is u for u in UNTYPED) else None


CHECKS: dict[str, Check] = {
    "RAPI-DTO-001": each(_dto001),
    "RAPI-DTO-002": each(_dto002),
}
