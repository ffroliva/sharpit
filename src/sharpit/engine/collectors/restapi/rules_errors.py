"""REST API error-handling rules evaluated against the error contract."""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.collectors.restapi.error_contract import ErrorContractEntry
from sharpit.engine.collectors.restapi.rules_common import (
    APPLICATION,
    Violation,
    shared_describe,
    shared_route_target,
)
from sharpit.engine.spi import ApiRouteInfo

_BODY_RENDERING = frozenset({"PROBLEM_DETAIL", "CUSTOM_OBJECT", "STRING"})
_SERVER_ERROR_CODES = frozenset(range(500, 600))
_THROTTLING_STATUSES = frozenset({"429", "503"})


def _err004(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-004: Make error-handler status ownership explicit.

    A handler that renders a body with no literal status_code (defaults to 200).
    """
    violations: list[Violation] = []
    for entry in error_contract:
        if entry.body_category in _BODY_RENDERING and entry.status is None:
            target = f"{entry.component}#{entry.method}"
            msg = (
                f"{entry.component_simple_name}#{entry.method} declares a body without explicit status selection; "
                "review the default status"
            )
            violations.append(Violation(target, msg))
    return violations


def _err005(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-005: Review broad handlers with fixed non-5xx statuses.

    A handler keyed Exception or BaseException returning a literal status below 500.
    """
    violations: list[Violation] = []
    for entry in error_contract:
        if (
            entry.exception_simple_name in ("Exception", "BaseException")
            and entry.status is not None
            and entry.status.isdigit()
        ):
            code = int(entry.status)
            if code not in _SERVER_ERROR_CODES:
                target = f"{entry.component}#{entry.method}"
                msg = (
                    f"{entry.component_simple_name}#{entry.method} catches Exception/Throwable and "
                    f"maps it to a fixed non-5xx status ({entry.status})"
                )
                violations.append(Violation(target, msg))
    return violations


def _err007(
    routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-007: Consider Retry-After for declared 429/503 statuses.

    A literal 429/503 on a handler or route without a Retry-After in its headers.
    """
    violations: list[Violation] = [
        Violation(
            shared_route_target(route),
            shared_describe(route, f"declares {route.status_code}; optionally review Retry-After policy"),
        )
        for route in routes
        if route.status_code in (429, 503)
    ]
    for entry in error_contract:
        if entry.status in _THROTTLING_STATUSES:
            target = f"{entry.component}#{entry.method}"
            msg = (
                f"{entry.component_simple_name}#{entry.method} declares {entry.status}; "
                "optionally review Retry-After policy"
            )
            violations.append(Violation(target, msg))
    return violations


def _err008(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-008: Consider structured error bodies.

    A handler whose body category is STRING.
    """
    violations: list[Violation] = []
    for entry in error_contract:
        if entry.body_category == "STRING":
            target = f"{entry.component}#{entry.method}"
            msg = f"{entry.component_simple_name}#{entry.method} returns a raw String error body"
            violations.append(Violation(target, msg))
    return violations


_CATEGORY_DISPLAY = {
    "PROBLEM_DETAIL": "problem details",
    "CUSTOM_OBJECT": "custom object",
    "STRING": "raw string",
}


def _unspecified_conflict(
    handler: ErrorContractEntry,
    cat_handler: str,
    cat_first: str,
    first: ErrorContractEntry,
    different: ErrorContractEntry | None,
) -> Violation | None:
    if cat_first != cat_handler:
        return _disagreement(first, handler)
    if different is not None:
        return _disagreement(different, handler)
    return None


def _check_media_produces(
    handler: ErrorContractEntry,
    cat_handler: str,
    first_by_media: dict[str, ErrorContractEntry],
) -> Violation | None:
    for media in handler.produces:
        media_norm = media.strip().lower()
        if media_norm.startswith("!") or "*" in media_norm:
            continue
        other = first_by_media.setdefault(media_norm, handler)
        if other is not handler and _CATEGORY_DISPLAY[other.body_category] != cat_handler:
            return _disagreement(other, handler)
    return None


def _err010(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-010: Review differing known error contracts.

    At least two handlers with different known body categories for the same media type.
    DYNAMIC and UNRESOLVED are ignored.
    """
    rendering = [entry for entry in error_contract if entry.body_category in _CATEGORY_DISPLAY]
    if len(rendering) < 2:
        return []

    first_by_media: dict[str, ErrorContractEntry] = {}
    first = rendering[0]
    different: ErrorContractEntry | None = None
    unspecified: ErrorContractEntry | None = None

    for handler in rendering:
        cat_handler = _CATEGORY_DISPLAY[handler.body_category]
        cat_first = _CATEGORY_DISPLAY[first.body_category]
        if different is None and cat_first != cat_handler:
            different = handler

        if not handler.produces:
            conflict = _unspecified_conflict(handler, cat_handler, cat_first, first, different)
            if conflict is not None:
                return [conflict]
            unspecified = handler
        else:
            if unspecified is not None and _CATEGORY_DISPLAY[unspecified.body_category] != cat_handler:
                return [_disagreement(unspecified, handler)]
            conflict = _check_media_produces(handler, cat_handler, first_by_media)
            if conflict is not None:
                return [conflict]
    return []


def _disagreement(first: ErrorContractEntry, second: ErrorContractEntry) -> Violation:
    cat1 = _CATEGORY_DISPLAY[first.body_category]
    cat2 = _CATEGORY_DISPLAY[second.body_category]
    msg = (
        f"Exception handlers have different error body declaration categories: {cat1} "
        f"({first.component_simple_name}#{first.method}); {cat2} ({second.component_simple_name}#{second.method})"
    )
    return Violation(APPLICATION, msg)


def _err011(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-011: Exception handlers do not expose stack traces (retired in 2.3.0)."""
    return []


CHECKS = {
    "RAPI-ERR-004": _err004,
    "RAPI-ERR-005": _err005,
    "RAPI-ERR-007": _err007,
    "RAPI-ERR-008": _err008,
    "RAPI-ERR-010": _err010,
    "RAPI-ERR-011": _err011,
}
