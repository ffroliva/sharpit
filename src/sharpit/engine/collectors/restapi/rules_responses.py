"""REST API responses rule checks."""

from __future__ import annotations

import types
import typing

from sharpit.engine.collectors.restapi.rules_common import (
    CREATION_PREFIXES,
    NONE,
    Check,
    each,
    shared_first_word,
    shared_function,
    shared_has_body_type,
    shared_response_type,
)
from sharpit.engine.spi import ApiRouteInfo


def _resp001(route: ApiRouteInfo) -> str | None:
    if "POST" not in route.methods or route.status_code is not None or route.dynamic_response:
        return None
    return (
        "creation-like POST with the default 200 status"
        if shared_first_word(shared_function(route)) in CREATION_PREFIXES
        else None
    )


def _resp002(route: ApiRouteInfo) -> str | None:
    if "DELETE" not in route.methods or route.status_code is not None or route.dynamic_response:
        return None
    return None if shared_has_body_type(route) else "DELETE with the default 200 status and no response body"


def _resp006(route: ApiRouteInfo) -> str | None:
    if route.status_code != 204 or route.dynamic_response:
        return None
    return "204 declared with a content-capable return type" if shared_has_body_type(route) else None


def _resp011(route: ApiRouteInfo) -> str | None:
    if "GET" not in route.methods or route.status_code not in (None, 200) or route.dynamic_response:
        return None
    tp = shared_response_type(route)
    while typing.get_origin(tp) is typing.Annotated:
        tp = typing.get_args(tp)[0]
    args = typing.get_args(tp)
    optional = typing.get_origin(tp) in (typing.Union, types.UnionType) and NONE in args and len(args) > 1
    return "Optional return served as 200 with a null body" if optional else None


CHECKS: dict[str, Check] = {
    "RAPI-RESP-001": each(_resp001),
    "RAPI-RESP-002": each(_resp002),
    "RAPI-RESP-006": each(_resp006),
    "RAPI-RESP-011": each(_resp011),
}
