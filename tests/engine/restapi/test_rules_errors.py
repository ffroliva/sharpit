"""Unit tests for REST API error-handling rules (RAPI-ERR-004, -005, -007, -008, -010, -011)."""

from __future__ import annotations

from sharpit.engine.collectors.restapi.error_contract import ErrorContractEntry
from sharpit.engine.collectors.restapi.rules import evaluate
from sharpit.engine.collectors.restapi.rules_errors import (
    _err004,
    _err005,
    _err007,
    _err008,
    _err010,
    _err011,
)
from sharpit.engine.spi import ApiRouteInfo


def _entry(
    *,
    exception_type: str = "builtins.ValueError",
    exception_simple_name: str = "ValueError",
    component: str = "app.errors",
    component_simple_name: str = "errors",
    method: str = "handle",
    status: str | None = None,
    status_source: str = "UNRESOLVED",  # no status visible
    body_category: str = "CUSTOM_OBJECT",
    body_type: str | None = "dict",
    produces: tuple[str, ...] = (),
) -> ErrorContractEntry:
    return ErrorContractEntry(
        id=f"{component}#{method}({exception_type})",
        exception_type=exception_type,
        exception_simple_name=exception_simple_name,
        component=component,
        component_simple_name=component_simple_name,
        method=method,
        source="STARLETTE_EXCEPTION_HANDLER",
        scope="GLOBAL",
        scope_target=None,
        precedence=1,
        precedence_source="DEFAULT",
        status=status,
        status_source=status_source,
        body_category=body_category,
        body_type=body_type,
        produces=produces,
    )


def _route(path: str = "/items", method: str = "GET", status_code: int | None = None) -> ApiRouteInfo:
    return ApiRouteInfo(
        methods=(method,),
        path=path,
        handler=f"app.routes:{method.lower()}_handler",
        status_code=status_code,
    )


# --- RAPI-ERR-004 --------------------------------------------------------------------------------------------------


def test_err004_flags_body_without_explicit_status() -> None:
    # ported: RestApiRulesTests.errorHandlingEdgeRuleFlagsBodyWithoutErrorStatus
    entry = _entry(body_category="CUSTOM_OBJECT", status=None)
    violations = _err004((), (), error_contract=(entry,))
    assert len(violations) == 1
    assert "errors#handle" in violations[0].target
    assert "declares a body without explicit status selection" in violations[0].message


def test_err004_passes_explicit_status_or_empty_body() -> None:
    # ported: RestApiRulesTests.phase3ErrorHandlingRulesFlagAndPass
    with_status = _entry(body_category="CUSTOM_OBJECT", status="400", status_source="ANNOTATION")
    empty_body = _entry(body_category="EMPTY", status=None)
    dynamic_body = _entry(body_category="DYNAMIC", status=None)

    assert _err004((), (), error_contract=(with_status,)) == []
    assert _err004((), (), error_contract=(empty_body,)) == []
    assert _err004((), (), error_contract=(dynamic_body,)) == []


# --- RAPI-ERR-005 --------------------------------------------------------------------------------------------------


def test_err005_flags_broad_handler_with_fixed_non_5xx_status() -> None:
    # ported: RestApiRulesTests.broadExceptionHandlerRuleAllowsA500FallbackButFlagsANon5xxCollapse
    entry = _entry(
        exception_type="builtins.Exception",
        exception_simple_name="Exception",
        status="400",
        status_source="ANNOTATION",
    )
    violations = _err005((), (), error_contract=(entry,))
    assert len(violations) == 1
    assert "errors#handle" in violations[0].target
    assert "catches Exception/BaseException and maps it to a fixed non-5xx status (400)" in violations[0].message


def test_err005_passes_500_fallback_or_specific_exception() -> None:
    # ported: RestApiRuleAccuracyTests.errorStatusReviewRequiresObservableFixedNonServerError
    server_error = _entry(
        exception_type="builtins.Exception",
        exception_simple_name="Exception",
        status="500",
        status_source="ANNOTATION",
    )
    specific_exc = _entry(
        exception_type="builtins.ValueError",
        exception_simple_name="ValueError",
        status="400",
        status_source="ANNOTATION",
    )
    dynamic_status = _entry(
        exception_type="builtins.Exception",
        exception_simple_name="Exception",
        status=None,
        status_source="DYNAMIC",
    )

    assert _err005((), (), error_contract=(server_error,)) == []
    assert _err005((), (), error_contract=(specific_exc,)) == []
    assert _err005((), (), error_contract=(dynamic_status,)) == []


# --- RAPI-ERR-007 --------------------------------------------------------------------------------------------------


def test_err007_flags_throttling_statuses_on_routes_and_handlers() -> None:
    # ported: RestApiRulesTests.retryAfterRuleFlagsThrottlingResponsesFromHandlersAndExceptionHandlers
    route_429 = _route("/rate-limited", status_code=429)
    route_503 = _route("/busy", status_code=503)
    entry_503 = _entry(status="503", status_source="ANNOTATION")

    violations = _err007((route_429, route_503), (), error_contract=(entry_503,))
    assert len(violations) == 3
    for v in violations:
        assert "review Retry-After policy" in v.message


def test_err007_passes_non_throttling_statuses() -> None:
    # ported: RestApiRulesTests.retryAfterRuleFlagsThrottlingResponsesFromHandlersAndExceptionHandlers
    route_200 = _route("/items", status_code=200)
    entry_400 = _entry(status="400", status_source="ANNOTATION")
    assert _err007((route_200,), (), error_contract=(entry_400,)) == []


# --- RAPI-ERR-008 --------------------------------------------------------------------------------------------------


def test_err008_flags_raw_string_error_body() -> None:
    # ported: RestApiRulesTests.headBodyAndRawStringExceptionRulesFireOnSpringAndJaxRs
    entry = _entry(body_category="STRING", status="400", status_source="ANNOTATION")
    violations = _err008((), (), error_contract=(entry,))
    assert len(violations) == 1
    assert "errors#handle" in violations[0].target
    assert "returns a raw String error body" in violations[0].message


def test_err008_passes_structured_error_bodies() -> None:
    # ported: RestApiRulesTests.headBodyAndRawStringExceptionRulesFireOnSpringAndJaxRs
    custom_obj = _entry(body_category="CUSTOM_OBJECT", status="400")
    problem = _entry(body_category="PROBLEM_DETAIL", status="400")
    empty = _entry(body_category="EMPTY", status="204")

    assert _err008((), (), error_contract=(custom_obj,)) == []
    assert _err008((), (), error_contract=(problem,)) == []
    assert _err008((), (), error_contract=(empty,)) == []


# --- RAPI-ERR-010 --------------------------------------------------------------------------------------------------


def test_err010_flags_differing_known_error_categories() -> None:
    # ported: RestApiRuleAccuracyTests.errorContractsCompareKnownShapesWithoutTreatingNegotiationAsAContradiction
    first = _entry(method="handle_problem", body_category="PROBLEM_DETAIL")
    second = _entry(method="handle_text", body_category="STRING")

    violations = _err010((), (), error_contract=(first, second))
    assert len(violations) == 1
    assert violations[0].target == "application"
    assert "different error body declaration categories: problem details" in violations[0].message
    assert "raw string" in violations[0].message


def test_err010_passes_matching_or_dynamic_categories() -> None:
    # ported: RestApiRuleAccuracyTests.errorContractsCompareKnownShapesWithoutTreatingNegotiationAsAContradiction
    first = _entry(method="first", body_category="PROBLEM_DETAIL")
    second = _entry(method="second", body_category="PROBLEM_DETAIL")
    dynamic = _entry(method="dyn", body_category="DYNAMIC")
    unresolved = _entry(method="unres", body_category="UNRESOLVED")

    assert _err010((), (), error_contract=(first, second)) == []
    assert _err010((), (), error_contract=(first, dynamic)) == []
    assert _err010((), (), error_contract=(first, unresolved)) == []
    assert _err010((), (), error_contract=(first,)) == []


# --- RAPI-ERR-011 --------------------------------------------------------------------------------------------------


def test_err011_retired_definition_emits_no_findings() -> None:
    # ported: RestApiRuleRegistryTests.retiredDefinitionsKeepTheirIdsWithoutEmittingFindings
    entry = _entry(body_category="STRING", status="500")
    assert _err011((), (), error_contract=(entry,)) == []


# --- evaluate integration ------------------------------------------------------------------------------------------


def test_evaluate_integrates_error_rules() -> None:
    route = _route("/rate-limited", status_code=429)
    entry = _entry(body_category="STRING", status="429")
    found, errored = evaluate((route,), (), error_contract=(entry,))
    assert errored == set()
    assert len(found["RAPI-ERR-007"]) >= 1
    assert len(found["RAPI-ERR-008"]) == 1
