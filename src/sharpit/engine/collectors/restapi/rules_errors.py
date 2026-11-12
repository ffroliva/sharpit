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

_BODY_RENDERING = frozenset({"CUSTOM_OBJECT", "STRING"})  # a problem-detail body carries its own status
_SERVER_ERROR_CODES = frozenset(range(500, 600))
_THROTTLING_STATUSES = frozenset({"429", "503"})


def _err004(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-004: Make error-handler status ownership explicit.

    A handler that renders a non-problem-detail body with no status visible (defaults to 200). A status built at
    runtime (DYNAMIC) is unknown, not missing.
    """
    violations: list[Violation] = []
    for entry in error_contract:
        if entry.body_category in _BODY_RENDERING and entry.status is None and entry.status_source != "DYNAMIC":
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

    A handler keyed Exception or BaseException returning a literal status below 500 (problem-detail bodies skipped).
    """
    violations: list[Violation] = []
    for entry in error_contract:
        if (
            entry.exception_simple_name in ("Exception", "BaseException")
            and entry.body_category != "PROBLEM_DETAIL"
            and entry.status is not None
            and entry.status.isdigit()
        ):
            code = int(entry.status)
            if code not in _SERVER_ERROR_CODES:
                target = f"{entry.component}#{entry.method}"
                msg = (
                    f"{entry.component_simple_name}#{entry.method} catches Exception/BaseException and "
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

    A literal 429/503 on a route, or on an exception handler with no literal Retry-After header; a handler whose
    headers are built at runtime is unknown and skipped. Routes carry no header evidence.
    """
    violations: list[Violation] = [
        Violation(
            shared_route_target(route),
            f"{shared_describe(route)} declares {route.status_code}; optionally review Retry-After policy",
        )
        for route in routes
        if route.status_code in (429, 503)
    ]
    for entry in error_contract:
        if entry.status in _THROTTLING_STATUSES and entry.retry_after is False:
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


def _err010(
    _routes: Sequence[ApiRouteInfo],
    _handlers: Sequence[str],
    *,
    error_contract: Sequence[ErrorContractEntry] = (),
) -> list[Violation]:
    """RAPI-ERR-010: Review differing known error contracts.

    At least two handlers with different known body categories. DYNAMIC and UNRESOLVED are ignored. BootUI also
    compares per media type; the model has no ``produces`` yet (always empty), so every handler is unspecified.
    """
    rendering = [entry for entry in error_contract if entry.body_category in _CATEGORY_DISPLAY]
    if not rendering:
        return []
    first = rendering[0]
    other = next((e for e in rendering if e.body_category != first.body_category), None)
    return [_disagreement(first, other)] if other else []


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
