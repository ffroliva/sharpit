"""Finding contract and advisor-run outcomes (0.3.0 spec §5.2-5.3)."""

import re

import pytest

from sharpit.engine.advisors.findings import AdvisorRun, Finding, severity_counts_of
from sharpit.engine.advisors.report import evidence
from sharpit.engine.advisors.rules import SEVERITIES, Severity

_GRAMMAR = re.compile(r"[A-Za-z0-9._:-]{1,200}")


def _finding(severity: Severity = "HIGH", **overrides: object) -> Finding:
    fields: dict[str, object] = {
        "rule_id": "RAPI-004",
        "advisor": "rest-api",
        "severity": severity,
        "target": "GET /owners/{owner_id}",
        "message": "a message",
    }
    return Finding(**{**fields, **overrides})  # type: ignore[arg-type]


def _complete() -> dict[str, object]:
    return evidence(True, True, [])


def test_fingerprint_stable_and_grammar():
    first = _finding().fingerprint
    assert first == _finding(message="other text").fingerprint
    assert _GRAMMAR.fullmatch(first)


def test_fingerprint_golden():
    # derived: sha256("RAPI-004" 0x1f "GET /owners/{owner_id}" 0x1f "")[:16], computed independently of the code
    assert _finding().fingerprint == "rest-api:RAPI-004:590e8b46a921f986"


def test_fingerprint_identity_overrides_target():
    by_identity = _finding(target="a", identity="shared")
    assert by_identity.fingerprint == _finding(target="b", identity="shared").fingerprint
    assert by_identity.fingerprint != _finding(target="a").fingerprint


def test_fingerprint_includes_test_node_id():
    assert _finding(test_node_id="t.py::a").fingerprint != _finding(test_node_id="t.py::b").fingerprint


def test_finding_dto_keys():
    dto = _finding().to_dto()
    assert list(dto) == [
        "ruleId",
        "advisor",
        "severity",
        "target",
        "message",
        "fingerprint",
        "testNodeId",
        "dismissed",
    ]
    assert dto["testNodeId"] is None


def test_run_failed_on_gate_severity():
    run = AdvisorRun.of("rest-api", [_finding("HIGH")], _complete())
    assert run.status == "FAILED"
    assert run.reason is None


def test_run_medium_only_passes_with_high_gate():
    assert AdvisorRun.of("rest-api", [_finding("MEDIUM")], _complete()).status == "PASSED"


def test_run_unknown_when_coverage_incomplete():
    run = AdvisorRun.of("rest-api", [], evidence(True, False, ["router x could not be read"]))
    assert run.status == "UNKNOWN"
    assert run.reason == "router x could not be read"


def test_run_unknown_when_unusable_with_limitations():
    assert AdvisorRun.of("rest-api", [], evidence(False, True, ["nothing readable"])).status == "UNKNOWN"


def test_run_confirmed_empty_passes():
    # ported: RestApiScannerTests.noControllersIsConfirmedEmpty (usable false, coverageComplete true, no limitations)
    assert AdvisorRun.of("rest-api", [], evidence(False, True, [])).status == "PASSED"


@pytest.mark.parametrize("scan_status", ["PARTIAL", "ERROR"])
def test_run_partial_and_error_are_unknown(scan_status: str):
    assert AdvisorRun.of("rest-api", [], _complete(), scan_status=scan_status).status == "UNKNOWN"


def test_run_unknown_reason_fallback():
    run = AdvisorRun.of("rest-api", [], _complete(), scan_status="PARTIAL")
    assert run.reason == "assessment evidence is incomplete"


def test_dismissed_finding_does_not_fail():
    assert AdvisorRun.of("rest-api", [_finding("CRITICAL", dismissed=True)], _complete()).status == "PASSED"


def test_run_fail_on_lowers_the_gate():
    assert AdvisorRun.of("rest-api", [_finding("MEDIUM")], _complete(), fail_on="MEDIUM").status == "FAILED"


def test_failure_wins_over_incomplete_coverage():
    run = AdvisorRun.of("rest-api", [_finding("HIGH")], evidence(True, False, ["x"]))
    assert run.status == "FAILED"


def test_run_dto_keys():
    dto = AdvisorRun.of("rest-api", [_finding()], _complete(), app="demo").to_dto()
    assert list(dto) == ["advisor", "status", "reason", "app", "evidence", "findings"]
    assert dto["app"] == "demo"
    assert dto["findings"] == [_finding().to_dto()]


def test_severity_counts_of_all_five_in_order():
    findings = [_finding("LOW"), _finding("HIGH"), _finding("HIGH", target="b"), _finding("CRITICAL", dismissed=True)]
    counts = severity_counts_of(findings)
    assert [c["severity"] for c in counts] == list(SEVERITIES)
    assert [c["count"] for c in counts] == [0, 2, 0, 1, 0]
