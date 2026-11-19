"""The --fail-on severity and evidence-sufficiency gates (ported from BootUI 2.4.0 FailOnTests)."""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.cli.arguments import build_tool_arguments
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.fail_on import (
    ADVISOR_TOOLS,
    EXCLUDED,
    INSUFFICIENT_TOOLS,
    Criterion,
    accepted,
    effective_query,
    evaluate,
    parse,
    supports_insufficient,
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
    assert verdict.exit_code == ExitCodes.THRESHOLD
    assert "--fail-on high: found HIGH=2." in verdict.message
    assert "LOW" not in verdict.message


# ported: FailOnTests.aFindingAboveTheThresholdExitsThree
def test_a_finding_above_the_threshold_exits_three():
    payload = summary("SCANNED", count("CRITICAL", 1))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == ExitCodes.THRESHOLD


# ported: FailOnTests.onlyLowerSeveritiesPass
def test_only_lower_severities_pass():
    payload = summary("SCANNED", count("CRITICAL", 0), count("HIGH", 0), count("MEDIUM", 4), count("LOW", 9))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == ExitCodes.SUCCESS
    assert verdict.message == ""


# ported: FailOnTests.theThresholdIsInclusiveAtEveryLevel
def test_the_threshold_is_inclusive_at_every_level():
    for level in ("critical", "high", "medium", "low", "info"):
        payload = summary("SCANNED", count(level.upper(), 1))
        criterion = parse("get_fastapi_report", level)
        assert evaluate(payload, criterion, "get_fastapi_report").exit_code == ExitCodes.THRESHOLD


# ported: FailOnTests.theValueIsCaseInsensitive
def test_the_value_is_case_insensitive():
    payload = summary("SCANNED", count("HIGH", 1))
    criterion = parse("get_fastapi_report", "HiGh")
    assert evaluate(payload, criterion, "get_fastapi_report").exit_code == ExitCodes.THRESHOLD


# ported: FailOnTests.aReportWithNoFindingsPasses
def test_a_report_with_no_findings_passes():
    payload = summary("SCANNED", count("CRITICAL", 0), count("HIGH", 0))
    criterion = parse("get_fastapi_report", "low")
    assert evaluate(payload, criterion, "get_fastapi_report").exit_code == ExitCodes.SUCCESS


# ported: FailOnTests.severitiesOutsideTheOrderAreIgnored
def test_severities_outside_the_order_are_ignored():
    payload = summary("SCANNED", count("UNKNOWN", 3), count("NONE", 5))
    criterion = parse("vulnerabilities_scan", "info")
    assert evaluate(payload, criterion, "vulnerabilities_scan").exit_code == ExitCodes.SUCCESS


# ported: FailOnTests.aPartialScanWithAFindingStillFails
def test_a_partial_scan_with_a_finding_still_fails():
    payload = summary("PARTIAL", count("HIGH", 1))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == ExitCodes.THRESHOLD
    assert "PARTIAL" not in verdict.message


# ported: FailOnTests.aPartialScanWithoutAFindingPassesButSaysItIsNotProof
def test_a_partial_scan_without_a_finding_passes_but_says_it_is_not_proof():
    payload = summary("PARTIAL", count("HIGH", 0), count("MEDIUM", 3))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == ExitCodes.SUCCESS
    assert "PARTIAL" in verdict.message
    assert "not proof" in verdict.message


# ported: FailOnTests.anIgnoredSeverityWithFindingsIsNamedButDoesNotGate
def test_an_ignored_severity_with_findings_is_named_but_does_not_gate():
    payload = summary("SCANNED", count("HIGH", 0), count("UNKNOWN", 3), count("NONE", 0))
    verdict = evaluate(payload, Criterion.LOW, "vulnerabilities_scan")
    assert verdict.exit_code == ExitCodes.SUCCESS
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
    assert verdict.exit_code == ExitCodes.ERROR
    assert "cannot evaluate --fail-on" in verdict.message
    assert "no usable evidence" in verdict.message


# ported: FailOnTests.aFindingStillFailsWhenTheEvidenceIsNotUsableAndUsableEvidencePasses
def test_a_finding_still_fails_when_the_evidence_is_not_usable_and_usable_evidence_passes():
    payload1 = {
        "scan": {"status": "SCANNED"},
        "severityCounts": [count("HIGH", 1)],
        "evidence": {"usable": False},
    }
    assert evaluate(payload1, Criterion.HIGH, "architecture_scan").exit_code == ExitCodes.THRESHOLD

    payload2 = {
        "scan": {"status": "SCANNED"},
        "severityCounts": [count("HIGH", 0)],
        "evidence": {"usable": True},
    }
    assert evaluate(payload2, Criterion.HIGH, "architecture_scan").exit_code == ExitCodes.SUCCESS


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
    assert ignored.exit_code == ExitCodes.THRESHOLD
    assert "\u001b" not in ignored.message

    payload2 = summary("EVIL\u001b[31m", count("HIGH", 0))
    status_verdict = evaluate(payload2, Criterion.HIGH, "get_fastapi_report")
    assert status_verdict.exit_code == ExitCodes.ERROR
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
    assert verdict.exit_code == ExitCodes.THRESHOLD


# ported: FailOnTests.aScanThatDidNotEvaluateIsNeverAPass
@pytest.mark.parametrize("scan_status", ["NOT_SCANNED", "DISABLED", "ERROR", "FAILED", "SOMETHING_NEW"])
def test_a_scan_that_did_not_evaluate_is_never_a_pass(scan_status: str):
    payload = summary(scan_status, count("CRITICAL", 0), count("HIGH", 0))
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == ExitCodes.ERROR
    assert "cannot evaluate --fail-on" in verdict.message
    assert scan_status in verdict.message


# ported: FailOnTests.aMissingScanStatusIsUnevaluable
def test_a_missing_scan_status_is_unevaluable():
    payload = {"severityCounts": [count("HIGH", 0)]}
    verdict = evaluate(payload, Criterion.HIGH, "get_fastapi_report")
    assert verdict.exit_code == ExitCodes.ERROR
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
    assert verdict.exit_code == ExitCodes.ERROR
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
    assert verdict.exit_code == ExitCodes.ERROR
    assert "cannot evaluate --fail-on" in verdict.message


# ported: FailOnTests.anInvalidValueIsAUsageErrorListingTheAcceptedOnesAndMakesNoCall
def test_an_invalid_value_is_a_usage_error_listing_the_accepted_ones():
    with pytest.raises(ValueError) as excinfo:
        parse("get_fastapi_report", "severe")
    assert "severe" in str(excinfo.value)
    assert "critical, high, medium, low, info" in str(excinfo.value)


# derived: FailOnTests.theOptionNeedsAValue
def test_the_option_needs_a_value():
    with pytest.raises(ValueError):
        parse("get_fastapi_report", "")


# ported: FailOnTests.theThresholdIsNeverSentToTheApplication
def test_the_threshold_is_never_sent_to_the_application():
    manifest = Manifest.bundled()
    for tool in manifest.tools:
        assert "fail_on" not in tool.arguments
        assert "failOn" not in tool.arguments
    insights_tool = manifest.by_name("get_runtime_insights")
    assert insights_tool is not None
    built = build_tool_arguments(
        insights_tool,
        {
            "fail_on": "high",
            "json": True,
            "url": "http://127.0.0.1:8000",
            "token": "tok",
            "api_path": "/sharpit/api",
            "query": "x",
            "limit": 3,
        },
    )
    assert built == {"query": "x", "limit": 3}
    for forbidden in ("fail_on", "failOn", "json", "url", "token", "api_path"):
        assert forbidden not in built


def test_build_tool_arguments_maps_scan_id_to_wire_name():
    manifest = Manifest.bundled()
    tool = next(t for t in manifest.tools if "scanId" in t.arguments)
    options = {
        "scan_id": "scan-42",
        "limit": 10,
        "fail_on": "high",
        "json": True,
        "url": "http://127.0.0.1:8000",
    }
    args = build_tool_arguments(tool, options)
    assert args == {"scanId": "scan-42", "limit": 10}


def test_build_tool_arguments_applies_effective_query():
    manifest = Manifest.bundled()
    tool = next(t for t in manifest.tools if t.name == "get_runtime_insights")
    args = build_tool_arguments(tool, {"query": None, "limit": 5}, criterion=Criterion.INSUFFICIENT)
    assert args == {"query": "all", "limit": 5}


# ported: FailOnTests.runtimeInsightsGateUsesAggregateCountsEvenWhenRowsAreOmitted
def test_runtime_insights_gate_uses_aggregate_counts_even_when_rows_are_omitted():
    payload = runtime_insights(True, 1, 0, 7)
    verdict = evaluate(payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert verdict.exit_code == ExitCodes.THRESHOLD
    assert "1 insufficient and 0 partial" in verdict.message


# ported: FailOnTests.runtimeInsightsGateFailsOnPartialEvidenceAndFailsClosedOnUnavailableOrMalformedReports
def test_runtime_insights_gate_fails_on_partial_evidence_and_fails_closed_on_unavailable_or_malformed_reports():
    payload1 = runtime_insights(True, 0, 2, 2)
    assert evaluate(payload1, Criterion.INSUFFICIENT, "get_runtime_insights").exit_code == ExitCodes.THRESHOLD

    payload2 = runtime_insights(False, 0, 0, 0)
    unavailable = evaluate(payload2, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert unavailable.exit_code == ExitCodes.ERROR
    assert "cannot evaluate --fail-on" in unavailable.message
    assert "unavailable" in unavailable.message

    payload3 = {"available": True, "insufficient": 0, "partial": 0, "observations": [], "omitted": 1.5}
    assert evaluate(payload3, Criterion.INSUFFICIENT, "get_runtime_insights").exit_code == ExitCodes.ERROR

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
    assert inconsistent.exit_code == ExitCodes.ERROR
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
    assert inflated.exit_code == ExitCodes.ERROR
    assert "aggregate counts do not match" in inflated.message


# ported: FailOnTests.runtimeInsightsGateDefaultsToAllAndAllowsCleanEmptyResultsOnlyWithActivity
def test_runtime_insights_gate_defaults_to_all_and_allows_clean_empty_results_only_with_activity():
    assert effective_query("get_runtime_insights", None, Criterion.INSUFFICIENT) == "all"

    payload1 = runtime_insights(True, 0, 0, 0)
    clean = evaluate(payload1, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert clean.exit_code == ExitCodes.SUCCESS

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
    assert no_activity.exit_code == ExitCodes.ERROR
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
    assert result.exit_code == ExitCodes.ERROR
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
    assert result.exit_code == ExitCodes.ERROR
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
    assert result.exit_code == ExitCodes.SUCCESS


# ported: FailOnTests.oneRuntimeObservationUsesItsExplicitStatus
def test_one_runtime_observation_uses_its_explicit_status():
    payload_partial = {"available": True, "observation": {"status": "PARTIAL"}}
    partial = evaluate(payload_partial, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert partial.exit_code == ExitCodes.THRESHOLD
    assert "status is PARTIAL" in partial.message

    payload_observed = {"available": True, "observation": {"status": "OBSERVED"}}
    assert evaluate(payload_observed, Criterion.INSUFFICIENT, "get_runtime_insight").exit_code == ExitCodes.SUCCESS

    payload_finding = {"available": True, "observation": {"status": "FINDING"}}
    assert evaluate(payload_finding, Criterion.INSUFFICIENT, "get_runtime_insight").exit_code == ExitCodes.SUCCESS

    payload_future = {"available": True, "observation": {"status": "FUTURE"}}
    unknown = evaluate(payload_future, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert unknown.exit_code == ExitCodes.ERROR
    assert "status is not recognised" in unknown.message

    payload_unavail = {"available": True, "observation": {"status": "UNAVAILABLE"}}
    unavailable = evaluate(payload_unavail, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert unavailable.exit_code == ExitCodes.ERROR
    assert "status is UNAVAILABLE" in unavailable.message

    payload_na = {"available": True, "observation": {"status": "NOT_APPLICABLE"}}
    not_applicable = evaluate(payload_na, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert not_applicable.exit_code == ExitCodes.ERROR
    assert "status is NOT_APPLICABLE" in not_applicable.message


# adapted: FailOnTests.caughtExceptionGateFailsOnInsufficientOrPartialRowsAndOnUnavailableEvidence
def test_exceptions_tool_rejects_fail_on_with_usage_error():
    assert "get_exceptions" not in INSUFFICIENT_TOOLS
    with pytest.raises(ValueError) as excinfo:
        parse("get_exceptions", "insufficient")
    assert "sharpit records no caught-in-code evidence, so this gate cannot be evaluated" in str(excinfo.value)
    assert str(excinfo.value).endswith(".")


# ported: FailOnTests.insufficientCriterionIsAcceptedOnlyForEvidenceTools
def test_insufficient_criterion_is_accepted_only_for_evidence_tools():
    assert set(INSUFFICIENT_TOOLS) == {"get_runtime_insight", "get_runtime_insights"}
    for tool in Manifest.bundled().tools:
        if supports_insufficient(tool.name):
            assert parse(tool.name, "insufficient") == Criterion.INSUFFICIENT
        else:
            with pytest.raises(ValueError):
                parse(tool.name, "insufficient")


EXPECTED_ADVISORS: frozenset[str] = frozenset(
    {
        "architecture_scan",
        "get_architecture_report",
        "database_advisor_scan",
        "get_database_advisor_report",
        "fastapi_scan",
        "get_fastapi_report",
        "rest_api_scan",
        "get_rest_api_report",
        "security_scan",
        "get_security_report",
        "vulnerabilities_scan",
        "get_vulnerabilities_report",
    }
)


# ported: FailOnTests.everyAdvisorToolTakesTheOptionAndNoOtherCommandDoes
def test_every_advisor_tool_takes_the_option_and_no_other_command_does():
    manifest = Manifest.bundled()
    accepting: set[str] = set()
    rejecting: set[str] = set()
    for tool in manifest.tools:
        try:
            if parse(tool.name, "high") == Criterion.HIGH:
                accepting.add(tool.name)
            else:
                rejecting.add(tool.name)
        except ValueError:
            rejecting.add(tool.name)

    assert accepting == EXPECTED_ADVISORS
    assert rejecting == {t.name for t in manifest.tools if t.name not in EXPECTED_ADVISORS}
    assert ADVISOR_TOOLS == EXPECTED_ADVISORS


# ported: FailOnTests.everyScanAndReportToolIsEitherGatedOrExplicitlyExcluded
def test_every_scan_and_report_tool_is_either_gated_or_explicitly_excluded():
    manifest = Manifest.bundled()
    candidates = {
        tool.name
        for tool in manifest.tools
        if tool.name.endswith("_scan") or (tool.name.startswith("get_") and tool.name.endswith("_report"))
    }
    known = set(ADVISOR_TOOLS) | set(EXCLUDED.keys())
    assert candidates.issubset(known), "add a new advisor to ADVISOR_TOOLS, or to EXCLUDED with a reason"
    assert set(ADVISOR_TOOLS).isdisjoint(set(EXCLUDED.keys()))
    manifest_tool_names = {t.name for t in manifest.tools}
    assert known.issubset(manifest_tool_names), "a gated or excluded tool that no longer exists is stale"


def test_accepted_and_parse_for_excluded_tool_and_exceptions():
    msg_pg = accepted("get_postgresql_report")
    assert "takes no --fail-on: runtime views have no severities to gate on." in msg_pg
    assert msg_pg.endswith(".")
    with pytest.raises(ValueError) as excinfo_pg:
        parse("get_postgresql_report", "high")
    assert "takes no --fail-on: runtime views have no severities to gate on." in str(excinfo_pg.value)
    assert str(excinfo_pg.value).endswith(".")

    msg_ex = accepted("get_exceptions")
    assert "sharpit records no caught-in-code evidence, so this gate cannot be evaluated." in msg_ex
    assert msg_ex.endswith(".")
    with pytest.raises(ValueError) as excinfo_ex:
        parse("get_exceptions", "insufficient")
    assert "sharpit records no caught-in-code evidence, so this gate cannot be evaluated." in str(excinfo_ex.value)
    assert str(excinfo_ex.value).endswith(".")


def test_accepted_and_parse_for_tool_with_neither_criterion():
    msg = accepted("get_overview")
    assert "takes no --fail-on" in msg
    assert "critical" not in msg
    assert msg.endswith(".")
    with pytest.raises(ValueError) as excinfo:
        parse("get_overview", "high")
    assert "takes no --fail-on" in str(excinfo.value)
    assert "critical" not in str(excinfo.value)
    assert str(excinfo.value).endswith(".")


def test_error_scan_status_with_findings_is_unevaluable_in_cli():
    payload = {
        "scan": {"status": "ERROR"},
        "severityCounts": [count("HIGH", 1)],
    }
    verdict = evaluate(payload, Criterion.HIGH, "architecture_scan")
    assert verdict.exit_code == ExitCodes.ERROR
    assert "cannot evaluate --fail-on" in verdict.message
    assert "the scan status is ERROR, so its counts are not evidence" in verdict.message


def test_info_threshold_gates_on_info_finding():
    payload = summary("SCANNED", count("INFO", 1))
    verdict = evaluate(payload, Criterion.INFO, "get_fastapi_report")
    assert verdict.exit_code == ExitCodes.THRESHOLD
    assert "--fail-on info: found INFO=1." in verdict.message


def test_runtime_insights_gate_evaluates_real_engine_payload():
    from dataclasses import dataclass, field

    from sharpit.engine.capture.journal import RuntimeJournal
    from sharpit.engine.collectors.insights.agent_view import Steps, agent_list
    from sharpit.engine.collectors.insights.finding import Evaluation, Finding
    from sharpit.engine.collectors.insights.service import InsightsService
    from sharpit.engine.tools import COMMANDS
    from sharpit.settings_registry import JOURNAL_SOURCES

    steps = Steps(COMMANDS)
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    journal.offer({"source": "http", "requestId": "r1"})

    clean_report = InsightsService(journal, []).report()
    clean_payload = agent_list(clean_report, "all", None, steps)
    verdict_clean = evaluate(clean_payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert verdict_clean.exit_code == ExitCodes.SUCCESS
    assert verdict_clean.message == ""

    @dataclass(frozen=True)
    class FakeKind:
        kind: str = "repeated-selects"
        title: str = "Repeated SELECTs"
        minimum_tier: str = "REQUEST_ID"
        reads: frozenset[str] = frozenset({"ai"})
        optional_reads: frozenset[str] = frozenset()
        evaluate: object = field(default=lambda _s: Evaluation(0, []))

    finding = Finding("k1", "GET /x", False, "Not enough data", 4, 3, ["look"], ["r1"], [], [], [])
    bad_kind = FakeKind(evaluate=lambda _s: Evaluation(4, [finding]))

    bad_report = InsightsService(journal, [bad_kind]).report()
    bad_payload = agent_list(bad_report, "all", None, steps)
    verdict_bad = evaluate(bad_payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert verdict_bad.exit_code == ExitCodes.THRESHOLD
    assert "--fail-on insufficient: found 1 insufficient and 0 partial" in verdict_bad.message


def test_runtime_insight_detail_gate_evaluates_real_engine_payload():
    from dataclasses import dataclass, field

    from sharpit.engine.capture.journal import RuntimeJournal
    from sharpit.engine.collectors.insights.agent_view import Steps, agent_detail
    from sharpit.engine.collectors.insights.finding import Evaluation, Finding
    from sharpit.engine.collectors.insights.service import InsightsService
    from sharpit.engine.tools import COMMANDS
    from sharpit.settings_registry import JOURNAL_SOURCES

    steps = Steps(COMMANDS)
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    journal.offer({"source": "http", "requestId": "r1"})

    @dataclass(frozen=True)
    class FakeKind:
        kind: str = "k1"
        title: str = "Title 1"
        minimum_tier: str = "REQUEST_ID"
        reads: frozenset[str] = frozenset({"http"})
        optional_reads: frozenset[str] = frozenset()
        evaluate: object = field(default=None)

    # 1. INSUFFICIENT finding (sufficient=False) -> exit code 3
    finding_insufficient = Finding("k1", "GET /x", False, "Not enough data", 4, 3, ["look"], ["r1"], [], [], [])
    svc_insufficient = InsightsService(journal, [FakeKind(evaluate=lambda _s: Evaluation(4, [finding_insufficient]))])
    rep_insufficient = svc_insufficient.report()
    obs_id = rep_insufficient["observations"][0]["id"]
    raw_detail_insufficient = svc_insufficient.insight(obs_id)
    payload_insufficient = agent_detail(raw_detail_insufficient, steps)
    verdict_insufficient = evaluate(payload_insufficient, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert verdict_insufficient.exit_code == ExitCodes.THRESHOLD
    assert "--fail-on insufficient: observation status is INSUFFICIENT." in verdict_insufficient.message

    # 2. OBSERVED finding (sufficient=True) -> exit code 0
    finding_observed = Finding("k1", "GET /x", True, "Observed behavior", 4, 3, ["look"], ["r1"], [], [], [])
    svc_observed = InsightsService(journal, [FakeKind(evaluate=lambda _s: Evaluation(4, [finding_observed]))])
    raw_detail_observed = svc_observed.insight(obs_id)
    payload_observed = agent_detail(raw_detail_observed, steps)
    verdict_observed = evaluate(payload_observed, Criterion.INSUFFICIENT, "get_runtime_insight")
    assert verdict_observed.exit_code == ExitCodes.SUCCESS
    assert verdict_observed.message == ""


def test_runtime_insights_partial_list_row_evaluates_to_threshold():
    from dataclasses import dataclass, field

    from sharpit.engine.capture.journal import RuntimeJournal
    from sharpit.engine.collectors.insights.agent_view import Steps, agent_list
    from sharpit.engine.collectors.insights.finding import Evaluation, Finding
    from sharpit.engine.collectors.insights.service import InsightsService
    from sharpit.engine.tools import COMMANDS
    from sharpit.settings_registry import JOURNAL_SOURCES

    steps = Steps(COMMANDS)
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    journal.offer({"source": "http", "requestId": "r1"})
    journal.count_dropped("http")

    @dataclass(frozen=True)
    class FakeKind:
        kind: str = "k1"
        title: str = "Title 1"
        minimum_tier: str = "REQUEST_ID"
        reads: frozenset[str] = frozenset({"http"})
        optional_reads: frozenset[str] = frozenset()
        evaluate: object = field(default=None)

    finding = Finding("k1", "GET /x", True, "Found something", 4, 3, ["look"], ["r1"], [], [], [])
    svc = InsightsService(journal, [FakeKind(evaluate=lambda _s: Evaluation(4, [finding]))])
    rep = svc.report()
    payload = agent_list(rep, "all", None, steps)
    assert any(obs.get("status") == "PARTIAL" for obs in payload["observations"])
    verdict = evaluate(payload, Criterion.INSUFFICIENT, "get_runtime_insights")
    assert verdict.exit_code == ExitCodes.THRESHOLD
    assert "--fail-on insufficient: found 0 insufficient and 1 partial" in verdict.message
