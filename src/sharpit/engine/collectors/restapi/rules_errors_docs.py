"""REST API errors docs rule checks."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.collectors.restapi.rules_common import APPLICATION, FRAMEWORK_MODULES, Check, Violation, each
from sharpit.engine.spi import ApiRouteInfo


def _err001(routes: Sequence[ApiRouteInfo], handlers: Sequence[str]) -> list[Violation]:
    app_handlers = [h for h in handlers if h.partition(":")[0].partition(".")[0] not in FRAMEWORK_MODULES]
    if not routes or app_handlers:
        return []
    return [
        Violation(
            APPLICATION,
            "No application-wide exception handler was registered in app.exception_handlers for"
            f" {len(routes)} route handler(s).",
        )
    ]


def _doc001(route: ApiRouteInfo) -> str | None:
    return None if (route.summary or "").strip() or (route.description or "").strip() else "no summary or description"


def _doc002(route: ApiRouteInfo) -> str | None:
    return None if route.tags else "no tags"


CHECKS: dict[str, Check] = {
    "RAPI-ERR-001": _err001,
    "RAPI-DOC-001": each(_doc001),
    "RAPI-DOC-002": each(_doc002),
}
