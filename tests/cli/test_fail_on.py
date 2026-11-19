"""The --fail-on severity and evidence-sufficiency gates (ported from BootUI 2.4.0 FailOnTests)."""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.cli.fail_on import (
    CANNOT_EVALUATE,
    EXCLUDED,
    INSUFFICIENT_TOOLS,
    PASS,
    THRESHOLD_MET,
    TOOLS,
    Criterion,
    clean_tool_arguments,
    effective_query,
    evaluate,
    parse,
    supports_insufficient,
    supports_severity,
)
from sharpit.cli.manifest import Manifest


def summary(scan_status: str, *counts: dict[str, Any]) -> dict[str, Any]:
    return {
        "reportTool": "get_fastapi_report",
        "scan": {"status": scan_status},
        "findingsFound": 0,
        "severityCounts": list(counts),
    }


def count(severity: str, n: int) -> dict[str, Any]:
    return {"severity": severity, "count": n}


def runtime_insights(available: bool, insufficient: int, partial: int, omitted: int) -> dict[str, Any]:
    return {
        "available": available,
        "query": "all",
        "requests": 1,
        "insufficient": insufficient,
        "partial": partial,
        "observations": [],
        "omitted": omitted,
    }


# ported: FailOnTests.aFindingAtTheThresholdExitsThreeAndPrintsTheSameJson
def test_a_finding_at_the_threshold_exits_three_and_prints_the_same_json():
    payload = summary("SCANNED", count("HIGH", 2), count("LOW", 1))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == THRESHOLD_MET
    assert "--fail-on high: found HIGH=2." in verdict.message
    assert "LOW" not in verdict.message


# ported: FailOnTests.aFindingAboveTheThresholdExitsThree
def test_a_finding_above_the_threshold_exits_three():
    payload = summary("SCANNED", count("CRITICAL", 1))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == THRESHOLD_MET


# ported: FailOnTests.onlyLowerSeveritiesPass
def test_only_lower_severities_pass():
    payload = summary("SCANNED", count("CRITICAL", 0), count("HIGH", 0), count("MEDIUM", 4), count("LOW", 9))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == PASS
    assert verdict.message == ""


# ported: FailOnTests.theThresholdIsInclusiveAtEveryLevel
def test_the_threshold_is_inclusive_at_every_level():
    for level in ("critical", "high", "medium", "low", "info"):
        payload = summary("SCANNED", count(level.upper(), 1))
        criterion = parse("get_fastapi_report", level)
        assert evaluate(payload, criterion, "get_fastapi_report").exit_code == THRESHOLD_MET


# ported: FailOnTests.theValueIsCaseInsensitive
def test_the_value_is_case_insensitive():
    payload = summary("SCANNED", count("HIGH", 1))
    criterion = parse("get_fastapi_report", "HiGh")
    assert evaluate(payload, criterion, "get_fastapi_report").exit_code == THRESHOLD_MET


# ported: FailOnTests.aReportWithNoFindingsPasses
def test_a_report_with_no_findings_passes():
    payload = summary("SCANNED", count("CRITICAL", 0), count("HIGH", 0))
    criterion = parse("get_fastapi_report", "low")
    assert evaluate(payload, criterion, "get_fastapi_report").exit_code == PASS


# ported: FailOnTests.severitiesOutsideTheOrderAreIgnored
def test_severities_outside_the_order_are_ignored():
    payload = summary("SCANNED", count("UNKNOWN", 3), count("NONE", 5))
    criterion = parse("vulnerabilities_scan", "info")
    assert evaluate(payload, criterion, "vulnerabilities_scan").exit_code == PASS


# ported: FailOnTests.aPartialScanWithAFindingStillFails
def test_a_partial_scan_with_a_finding_still_fails():
    payload = summary("PARTIAL", count("HIGH", 1))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == THRESHOLD_MET
    assert "PARTIAL" not in verdict.message


# ported: FailOnTests.aPartialScanWithoutAFindingPassesButSaysItIsNotProof
def test_a_partial_scan_without_a_finding_passes_but_says_it_is_not_proof():
    payload = summary("PARTIAL", count("HIGH", 0), count("MEDIUM", 3))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == PASS
    assert "PARTIAL" in verdict.message
    assert "not proof" in verdict.message


# ported: FailOnTests.anIgnoredSeverityWithFindingsIsNamedButDoesNotGate
def test_an_ignored_severity_with_findings_is_named_but_does_not_gate():
    payload = summary("SCANNED", count("HIGH", 0), count("UNKNOWN", 3), count("NONE", 0))
    verdict = evaluate(payload, Criterion.LOW, "vulnerabilities_scan")
    assert verdict.exit_code == PASS
    assert "does not count UNKNOWN=3" in verdict.message
    assert "NONE" not in verdict.message


# ported: FailOnTests.zeroFindingsFromAScanWithNoUsableEvidenceCannotPass
def test_zero_findings_from_a_scan_with_no_usable_evidence_cannot_pass():
    payload = {
        "scan": {"status": "SCANNED"},
        "severityCounts": [count("HIGH", 0)],
        "evidence": {"usable": False, "coverageComplete": False, "limitations": []},
    }
    verdict = evaluate(payload, Criterion.HIGH, "architecture_scan")
    assert verdict.exit_code == CANNOT_EVALUATE
    assert "cannot evaluate --fail-on" in verdict.message
    assert "no usable evidence" in verdict.message


# ported: FailOnTests.aFindingStillFailsWhenTheEvidenceIsNotUsableAndUsableEvidencePasses
def test_a_finding_still_fails_when_the_evidence_is_not_usable_and_usable_evidence_passes():
    payload1 = {
        "scan": {"status": "SCANNED"},
        "severityCounts": [count("HIGH", 1)],
        "evidence": {"usable": False},
    }
    assert evaluate(payload1, Criterion.HIGH, "architecture_scan").exit_code == THRESHOLD_MET

    payload2 = {
        "scan": {"status": "SCANNED"},
        "severityCounts": [count("HIGH", 0)],
        "evidence": {"usable": True},
    }
    assert evaluate(payload2, Criterion.HIGH, "architecture_scan").exit_code == PASS


# ported: FailOnTests.payloadTextIsNeverEchoedToStderrVerbatim
def test_payload_text_is_never_echoed_to_stderr_verbatim():
    payload1 = {
        "scan": {"status": "SCANNED"},
        "severityCounts": [
            {"severity": "HIGH\u001b[31m", "count": 0},
            {"severity": "WEIRD\u001b[31m", "count": 2},
            {"severity": "HIGH\u001b", "count": 1},
        ],
    }
    ignored = evaluate(payload1, Criterion.HIGH, "get_fastapi_report")
    assert "\u001b" not in ignored.message

    payload2 = summary("EVIL\u001b[31m", count("HIGH", 0))
    status_verdict = evaluate(payload2, Criterion.HIGH, "get_fastapi_report")
    assert status_verdict.exit_code == CANNOT_EVALUATE
    assert "\u001b" not in status_verdict.message
    assert "not recognised" in status_verdict.message


# ported: FailOnTests.aFullReportShapeGatesTooAndKeepsItsOtherFields
def test_a_full_report_shape_gates_too_and_keeps_its_other_fields():
    payload = {
        "scanningEnabled": True,
        "total": 4,
        "vulnerable": 1,
        "severityCounts": [count("CRITICAL", 1), count("HIGH", 0)],
        "scan": {"scanner": "OSV.dev", "status": "SCANNED", "packagesScanned": 4},
        "dependencies": [],
    }
    verdict = evaluate(payload, Criterion.HIGH, "get_vulnerabilities_report")
    assert verdict.exit_code == THRESHOLD_MET


# ported: FailOnTests.aScanThatDidNotEvaluateIsNeverAPass
@pytest.mark.parametrize("scan_status", ["NOT_SCANNED", "DISABLED", "ERROR", "FAILED", "SOMETHING_NEW"])
def test_a_scan_that_did_not_evaluate_is_never_a_pass(scan_status: str):
    payload = summary(scan_status, count("CRITICAL", 0), count("HIGH", 0))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == CANNOT_EVALUATE
    assert "cannot evaluate --fail-on" in verdict.message
    assert scan_status in verdict.message


# ported: FailOnTests.aMissingScanStatusIsUnevaluable
def test_a_missing_scan_status_is_unevaluable():
    payload = {"severityCounts": [count("HIGH", 0)]}
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == CANNOT_EVALUATE
    assert "cannot evaluate --fail-on" in verdict.message
    assert "scan status" in verdict.message


# ported: FailOnTests.aMissingOrMisshapenSeverityCountsIsUnevaluable
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"scan": {"status": "SCANNED"}},
        {"scan": {"status": "SCANNED"}, "severityCounts": None},
        {"scan": {"status": "SCANNED"}, "severityCounts": []},
        {"scan": {"status": "SCANNED"}, "severityCounts": {"HIGH": 0}},
        [],
        None,
    ],
)
def test_a_missing_or_misshapen_severity_counts_is_unevaluable(body: Any):
    verdict = evaluate(body, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == CANNOT_EVALUATE
    assert "cannot evaluate --fail-on" in verdict.message


# ported: FailOnTests.aMalformedEntryIsUnevaluableEvenAfterAnEarlierMatch
@pytest.mark.parametrize(
    "entry",
    [
        {"count": 1},
        {"severity": 5, "count": 1},
        {"severity": "HIGH"},
        {"severity": "HIGH", "count": "1"},
        {"severity": "HIGH", "count": -1},
        {"severity": "HIGH", "count": 1.5},
        {"severity": "HIGH", "count": 100.0},
        "HIGH",
    ],
)
def test_a_malformed_entry_is_unevaluable_even_after_an_earlier_match(entry: Any):
    payload = summary("SCANNED", count("CRITICAL", 1), entry)
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == CANNOT_EVALUATE
    assert "cannot evaluate --fail-on" in verdict.message


# ported: FailOnTests.anInvalidValueIsAUsageErrorListingTheAcceptedOnesAndMakesNoCall
def test_an_invalid_value_is_a_usage_error_listing_the_accepted_ones():
    with pytest.raises(ValueError) as excinfo:
        parse("get_fastapi_report", "severe")
    assert "severe" in str(excinfo.value)
    assert "critical, high, medium, low, info" in str(excinfo.value)


# ported: FailOnTests.theOptionNeedsAValue
def test_the_option_needs_a_value():
    with pytest.raises(ValueError):
        parse("get_fastapi_report", "")


# ported: FailOnTests.theThresholdIsNeverSentToTheApplication
def test_the_threshold_is_never_sent_to_the_application():
    manifest = Manifest.bundled()
    for tool in manifest.tools:
        assert "fail_on" not in tool.arguments
        assert "failOn" not in tool.arguments
    cleaned = clean_tool_arguments({"fail_on": "high", "query": "x", "limit": 3})
    assert cleaned == {"query": "x", "limit": 3}


# ported: FailOnTests.runtimeInsightsGateUsesAggregateCountsEvenWhenRowsAreOmitted
def test_runtime_insights_gate_uses_aggregate_counts_even_when_rows_are_omitted():
    payload = runtime_insights(True, 1, 0, 7)
    verdict = evaluate(payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert verdict.exit_code == THRESHOLD_MET
    assert "1 insufficient and 0 partial" in verdict.message


# ported: FailOnTests.runtimeInsightsGateFailsOnPartialEvidenceAndFailsClosedOnUnavailableOrMalformedReports
def test_runtime_insights_gate_fails_on_partial_evidence_and_fails_closed_on_unavailable_or_malformed_reports():
    payload1 = runtime_insights(True, 0, 2, 2)
    assert evaluate(payload1, Criterion.INSUFFICIENT, "get_runtime_insights").exit_code == THRESHOLD_MET

    payload2 = runtime_insights(False, 0, 0, 0)
    unavailable = evaluate(payload2, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert unavailable.exit_code == CANNOT_EVALUATE
    assert "cannot evaluate --fail-on" in unavailable.message
    assert "unavailable" in unavailable.message

    payload3 = {"available": True, "insufficient": 0, "partial": 0, "observations": [], "omitted": 1.5}
    assert evaluate(payload3, Criterion.INSUFFICIENT, "get_runtime_insights").exit_code == CANNOT_EVALUATE

    payload4 = {
        "available": True,
        "query": "all",
        "requests": 1,
        "insufficient": 0,
        "partial": 0,
        "observations": [{"status": "INSUFFICIENT"}],
        "omitted": 0,
    }
    inconsistent = evaluate(payload4, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert inconsistent.exit_code == CANNOT_EVALUATE
    assert "aggregate counts do not match" in inconsistent.message

    payload5 = {
        "available": True,
        "query": "all",
        "requests": 1,
        "insufficient": 1,
        "partial": 0,
        "observations": [{"status": "OBSERVED"}],
        "omitted": 0,
    }
    inflated = evaluate(payload5, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert inflated.exit_code == CANNOT_EVALUATE
    assert "aggregate counts do not match" in inflated.message


# ported: FailOnTests.runtimeInsightsGateDefaultsToAllAndAllowsCleanEmptyResultsOnlyWithActivity
def test_runtime_insights_gate_defaults_to_all_and_allows_clean_empty_results_only_with_activity():
    assert effective_query("get_runtime_insights", None, Criterion.INSUFFICIENT) == "all"

    payload1 = runtime_insights(True, 0, 0, 0)
    clean = evaluate(payload1, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert clean.exit_code == PASS

    payload2 = {
        "available": True,
        "query": "all",
        "requests": 0,
        "insufficient": 0,
        "partial": 0,
        "observations": [],
        "omitted": 0,
    }
    no_activity = evaluate(payload2, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert no_activity.exit_code == CANNOT_EVALUATE
    assert "empty result requires query=all and request activity" in no_activity.message


# ported: FailOnTests.runtimeInsightsGatePreservesAnExplicitQuery
def test_runtime_insights_gate_preserves_an_explicit_query():
    assert effective_query("get_runtime_insights", "my-filter", Criterion.INSUFFICIENT) == "my-filter"
    payload = {
        "available": True,
        "query": "my-filter",
        "requests": 1,
        "insufficient": 0,
        "partial": 0,
        "observations": [],
        "omitted": 0,
    }
    result = evaluate(payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert result.exit_code == CANNOT_EVALUATE
    assert "empty result requires query=all and request activity" in result.message


# ported: FailOnTests.runtimeInsightsGatePreservesAnExplicitBlankQuery
@pytest.mark.parametrize("query", ["", " "])
def test_runtime_insights_gate_preserves_an_explicit_blank_query(query: str):
    assert effective_query("get_runtime_insights", query, Criterion.INSUFFICIENT) == query
    payload = {
        "available": True,
        "query": query,
        "requests": 1,
        "insufficient": 0,
        "partial": 0,
        "observations": [],
        "omitted": 0,
    }
    result = evaluate(payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert result.exit_code == CANNOT_EVALUATE
    assert "empty result requires query=all and request activity" in result.message


# ported: FailOnTests.runtimeInsightsGateRecognizesCaseInsensitiveAllQuery
def test_runtime_insights_gate_recognizes_case_insensitive_all_query():
    payload = {
        "available": True,
        "query": "ALL",
        "requests": 1,
        "insufficient": 0,
        "partial": 0,
        "observations": [],
        "omitted": 0,
    }
    result = evaluate(payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert result.exit_code == PASS


# ported: FailOnTests.oneRuntimeObservationUsesItsExplicitStatus
def test_one_runtime_observation_uses_its_explicit_status():
    payload_partial = {"available": True, "observation": {"status": "PARTIAL"}}
    partial = evaluate(payload_partial, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert partial.exit_code == THRESHOLD_MET
    assert "status is PARTIAL" in partial.message

    payload_observed = {"available": True, "observation": {"status": "OBSERVED"}}
    assert evaluate(payload_observed, Criterion.INSUFFICIENT, "get_runtime_insight").exit_code == PASS

    payload_finding = {"available": True, "observation": {"status": "FINDING"}}
    assert evaluate(payload_finding, Criterion.INSUFFICIENT, "get_runtime_insight").exit_code == PASS

    payload_future = {"available": True, "observation": {"status": "FUTURE"}}
    unknown = evaluate(payload_future, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert unknown.exit_code == CANNOT_EVALUATE
    assert "status is not recognised" in unknown.message

    payload_unavail = {"available": True, "observation": {"status": "UNAVAILABLE"}}
    unavailable = evaluate(payload_unavail, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert unavailable.exit_code == CANNOT_EVALUATE
    assert "status is UNAVAILABLE" in unavailable.message

    payload_na = {"available": True, "observation": {"status": "NOT_APPLICABLE"}}
    not_applicable = evaluate(payload_na, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert not_applicable.exit_code == CANNOT_EVALUATE
    assert "status is NOT_APPLICABLE" in not_applicable.message


# ported: FailOnTests.caughtExceptionGateFailsOnInsufficientOrPartialRowsAndOnUnavailableEvidence
def test_caught_exception_gate_fails_on_insufficient_or_partial_rows_and_on_unavailable_evidence():
    payload_insufficient = {
        "available": True,
        "caughtInCode": {"available": True, "insufficient": 1, "partial": 0},
    }
    assert evaluate(payload_insufficient, Criterion.INSUFFICIENT, "get_exceptions").exit_code == THRESHOLD_MET

    payload_pass = {
        "available": True,
        "caughtInCode": {"available": True, "insufficient": 0, "partial": 0},
    }
    assert evaluate(payload_pass, Criterion.INSUFFICIENT, "get_exceptions").exit_code == PASS

    payload_partial = {
        "available": True,
        "caughtInCode": {"available": True, "insufficient": 0, "partial": 1},
    }
    assert evaluate(payload_partial, Criterion.INSUFFICIENT, "get_exceptions").exit_code == THRESHOLD_MET

    payload_unavail = {
        "available": True,
        "caughtInCode": {"available": False, "insufficient": 0, "partial": 0},
    }
    unavailable = evaluate(payload_unavail, Criterion.INSUFFICIENT, "get_exceptions")
    assert unavailable.exit_code == CANNOT_EVALUATE
    assert "caught-exception evidence is unavailable" in unavailable.message

    # sharpit's caughtInCode stays null without a sensor, so decide by BootUI's rule for unavailable answer:
    payload_null = {"available": True, "caughtInCode": None}
    no_sensor = evaluate(payload_null, Criterion.INSUFFICIENT, "get_exceptions")
    assert no_sensor.exit_code == CANNOT_EVALUATE
    assert "caught-exception evidence is unavailable" in no_sensor.message


# ported: FailOnTests.insufficientCriterionIsAcceptedOnlyForEvidenceTools
def test_insufficient_criterion_is_accepted_only_for_evidence_tools():
    assert {"get_exceptions", "get_runtime_insight", "get_runtime_insights"} == INSUFFICIENT_TOOLS
    for tool in Manifest.bundled().tools:
        if supports_insufficient(tool.name):
            assert parse(tool.name, "insufficient") == Criterion.INSUFFICIENT
        else:
            with pytest.raises(ValueError):
                parse(tool.name, "insufficient")


# ported: FailOnTests.everyAdvisorToolTakesTheOptionAndNoOtherCommandDoes
def test_every_advisor_tool_takes_the_option_and_no_other_command_does():
    manifest = Manifest.bundled()
    accepting: set[str] = set()
    rejecting: set[str] = set()
    for tool in manifest.tools:
        if supports_severity(tool.name):
            accepting.add(tool.name)
        else:
            rejecting.add(tool.name)
    assert len(accepting) == 12
    assert accepting == set(TOOLS)
    assert rejecting == {t.name for t in manifest.tools if t.name not in TOOLS}


# ported: FailOnTests.everyScanAndReportToolIsEitherGatedOrExplicitlyExcluded
def test_every_scan_and_report_tool_is_either_gated_or_explicitly_excluded():
    manifest = Manifest.bundled()
    candidates = {
        tool.name
        for tool in manifest.tools
        if tool.name.endswith("_scan") or (tool.name.startswith("get_") and tool.name.endswith("_report"))
    }
    known = set(TOOLS) | set(EXCLUDED)
    assert candidates.issubset(known), "add a new advisor to TOOLS or EXCLUDED with a reason"
    assert not (TOOLS & EXCLUDED)
    assert known.issubset({tool.name for tool in manifest.tools}), (
        "a gated or excluded tool that no longer exists is stale"
    )
