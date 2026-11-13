"""REST API versioning rule checks."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.collectors.restapi.rules_common import (
    APPLICATION,
    NON_API_SEGMENTS,
    VERSION,
    Check,
    Violation,
    shared_describe,
    shared_segments,
    shared_static,
)
from sharpit.engine.spi import ApiRouteInfo

DOCUMENTATION_SEGMENTS = frozenset({"api-docs", "swagger-ui"})


def _is_api(route: ApiRouteInfo) -> bool:
    """BootUI ``isNonApiEndpoint``: an operational first segment, or generated docs anywhere (``/v3/api-docs``)."""
    statics = [s.lower() for s in shared_static(route.path)]
    operational = bool(statics) and statics[0] in NON_API_SEGMENTS  # a variable-only path stays an API handler
    return bool(shared_segments(route.path)) and not operational and DOCUMENTATION_SEGMENTS.isdisjoint(statics)


def _ver001(routes: Sequence[ApiRouteInfo], _handlers: Sequence[str]) -> list[Violation]:
    api = [r for r in routes if _is_api(r)]
    unversioned = [r for r in api if not any(VERSION.fullmatch(s) for s in shared_segments(r.path))]
    if not unversioned:
        return []
    if len(unversioned) == len(api):
        return [
            Violation(
                APPLICATION,
                "No API version signal (no /vN path, version header/param, or versioned media type) was detected"
                f" across {len(api)} handler(s).",
            )
        ]
    examples = ", ".join(shared_describe(r) for r in unversioned[:5])
    return [
        Violation(
            APPLICATION,
            f"Versioning is applied inconsistently: {len(unversioned)} of {len(api)} API handler(s) have no version"
            f" signal while others do. Unversioned example(s): {examples}",
        )
    ]


CHECKS: dict[str, Check] = {
    "RAPI-VER-001": _ver001,
}
