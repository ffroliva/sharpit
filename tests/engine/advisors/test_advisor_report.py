"""Advisor report helpers (spec §8; BootUI ``SeverityOrder.occurrenceCounts``, ``RestApiScanner.applyDismissals``,
``AdvisorEvidenceDto`` and ``AdvisorEvidenceDtoTests``)."""

from typing import Any

from sharpit.engine.advisors.report import apply_dismissals, evidence, sanitize_limitations, severity_counts
from sharpit.engine.advisors.rules import SEVERITIES


def test_severity_counts_every_severity_zero_included():
    assert severity_counts([], SEVERITIES) == [{"severity": s, "count": 0} for s in SEVERITIES]
    counts = severity_counts([("HIGH", 3), ("LOW", 1), ("HIGH", 2), ("UNKNOWN", 9)], SEVERITIES)
    assert counts == [
        {"severity": "CRITICAL", "count": 0},
        {"severity": "HIGH", "count": 5},
        {"severity": "MEDIUM", "count": 0},
        {"severity": "LOW", "count": 1},
        {"severity": "INFO", "count": 0},
    ]  # a severity outside the given order is skipped, as BootUI does
    six = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN", "NONE")
    assert [c["severity"] for c in severity_counts([], six)] == list(six)


def _result(rule_id: str, severity: str, count: int, status: str = "FAILED") -> dict[str, Any]:
    return {"id": rule_id, "severity": severity, "status": status, "violationCount": count, "dismissed": False}


def _report() -> dict[str, Any]:
    results = [_result("RAPI-A", "HIGH", 4), _result("RAPI-B", "LOW", 2), _result("RAPI-C", "INFO", 0, "PASSED")]
    return {
        "violationsFound": 2,
        "severityCounts": severity_counts([("HIGH", 4), ("LOW", 2)], SEVERITIES),
        "scan": {"status": "SCANNED", "violationsFound": 2},
        "results": results,
        "evidence": {"usable": True, "coverageComplete": True, "limitations": []},
    }


def test_dismissal_recomputes_counts():
    report = _report()
    applied = apply_dismissals(report, {"RAPI-A", "RAPI-unrelated"})
    assert [r["dismissed"] for r in applied["results"]] == [True, False, False]
    assert applied["violationsFound"] == 1  # active failing rules (BootUI active.size())
    assert applied["scan"] == {"status": "SCANNED", "violationsFound": 1}
    assert {c["severity"]: c["count"] for c in applied["severityCounts"]} == {
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 2,
        "INFO": 0,
    }
    assert applied["evidence"] == report["evidence"]  # dismissals never change evidence
    assert report == _report()  # the cached report is never mutated
    assert apply_dismissals(report, set()) == report


# ported: AdvisorEvidenceDtoTests.limitationsAreImmutableBoundedAndControlCharactersAreRemoved
def test_limitations_bounded_and_control_characters_removed():
    assert sanitize_limitations(["Unknown\nobservation", "x" * 300]) == ["Unknown observation", "x" * 240]
    assert len(sanitize_limitations([str(i) for i in range(30)])) == 20


# ported: AdvisorEvidenceDtoTests.invalidDependencyCompletionIsRejectedAndMissingEvidenceIsUnknown (limitations part)
def test_limitations_none_blank_and_duplicates_dropped():
    assert sanitize_limitations(None) == []
    assert sanitize_limitations([None, "  ", "\t\x00", " a\x7f", "a"]) == ["a"]


# ported: AdvisorEvidenceDtoTests.usabilityIsIndependentOfCoverageAndUsesBooleanWireFields, AdvisorEvidenceDto.unknown
def test_evidence_shape_and_unknown():
    assert evidence(True, False, ["Partial evidence"]) == {
        "usable": True,
        "coverageComplete": False,
        "limitations": ["Partial evidence"],
    }
    assert evidence(False, True, []) == {"usable": False, "coverageComplete": True, "limitations": []}
    assert evidence() == {
        "usable": False,
        "coverageComplete": False,
        "limitations": ["Assessment evidence is unavailable."],
    }
