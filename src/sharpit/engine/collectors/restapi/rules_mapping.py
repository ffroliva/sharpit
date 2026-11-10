"""REST API mapping rule checks."""

from __future__ import annotations

import re
from collections.abc import Sequence

from sharpit.engine.collectors.restapi.rules_common import (
    CATCH_ALL,
    DOUBLE_SLASH,
    MUTATING,
    NON_MUTATING_PREFIXES,
    STATE_CHANGING_PREFIXES,
    Check,
    Violation,
    each,
    shared_first_word,
    shared_function,
    shared_is_variable,
    shared_segments,
)
from sharpit.engine.spi import ApiRouteInfo


def _map001(route: ApiRouteInfo) -> str | None:
    mutating = [m for m in route.methods if m in MUTATING]
    return f"GET combined with {', '.join(mutating)}" if "GET" in route.methods and mutating else None


def _map002(routes: Sequence[ApiRouteInfo], _handlers: Sequence[str]) -> list[Violation]:
    by_route: dict[tuple[str, str], list[str]] = {}
    for route in routes:
        for method in route.methods:
            by_route.setdefault((method, route.path), []).append(route.handler)
    return [
        Violation(
            f"{method} {path}", f"{method} {path} with matching dispatch conditions handled by {', '.join(handlers)}"
        )
        for (method, path), handlers in by_route.items()
        if len(handlers) > 1
    ]


def _map003(route: ApiRouteInfo) -> str | None:
    name = shared_function(route)
    if "GET" not in route.methods or name.replace("_", "").lower().startswith(NON_MUTATING_PREFIXES):
        return None
    return "mutation-like name on GET" if shared_first_word(name) in STATE_CHANGING_PREFIXES else None


def _map005(route: ApiRouteInfo) -> str | None:
    outside = re.sub(r"\{[^}]*\}", "", route.path)
    if DOUBLE_SLASH.search(outside):
        return "doubled slash"
    return "trailing slash" if len(route.path) > 1 and route.path.endswith("/") else None


def _map007(route: ApiRouteInfo) -> str | None:
    methods = [m for m in route.methods if m in ("GET", "HEAD", "DELETE")]
    return f"request body on {', '.join(methods)}" if route.has_body and methods else None


def _map010(route: ApiRouteInfo) -> str | None:
    return "catch-all path parameter" if CATCH_ALL.search(route.path) else None


def _map011(route: ApiRouteInfo) -> str | None:
    segments = shared_segments(route.path)
    depth = sum(
        1 for a, b in zip(segments, segments[1:], strict=False) if not shared_is_variable(a) and shared_is_variable(b)
    )
    return f"{depth} levels of collection/{{id}} nesting" if depth > 3 else None


CHECKS: dict[str, Check] = {
    "RAPI-MAP-001": each(_map001),
    "RAPI-MAP-002": _map002,
    "RAPI-MAP-003": each(_map003),
    "RAPI-MAP-005": each(_map005),
    "RAPI-MAP-007": each(_map007),
    "RAPI-MAP-010": each(_map010),
    "RAPI-MAP-011": each(_map011),
}
