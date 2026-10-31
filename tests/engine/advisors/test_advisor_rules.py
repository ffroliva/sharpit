"""Shared advisor rule model (spec §8; BootUI ``SeverityOrder.DEFAULT`` and ``RestApiRuleResultDto``)."""

import dataclasses

import pytest

from sharpit.engine.advisors.rules import SEVERITIES, RuleDefinition, RuleResult, severity_rank

RULE = RuleDefinition(
    id="RAPI-MAP-001",
    name="One route answers GET and a mutating method",
    category="Mapping",
    severity="HIGH",
    description="d",
    recommendation="r",
    learn_more_url="https://github.com/ffroliva/sharpit",
)


def test_severity_order():
    assert SEVERITIES == ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
    assert [severity_rank(s) for s in SEVERITIES] == [0, 1, 2, 3, 4]
    assert severity_rank("UNKNOWN") == 5  # unknown sorts after every known severity (SeverityOrder.rank)


def test_rule_definition_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        RULE.severity = "LOW"  # type: ignore[misc]


def test_failed_result_keeps_first_ten_samples():
    result = RuleResult.evaluate(RULE, [f"GET /items/{i}" for i in range(12)])
    assert (result.status, result.violation_count, result.dismissed) == ("FAILED", 12, False)
    assert result.sample_violations == tuple(f"GET /items/{i}" for i in range(10))
    assert RuleResult.evaluate(RULE, []).status == "PASSED"
    assert RuleResult.skipped(RULE).status == "SKIPPED"


def test_result_dto_keys_match_bootui():
    # RestApiRuleResultDto component order
    assert list(RuleResult.evaluate(RULE, ["x"]).to_dto()) == [
        "id",
        "name",
        "category",
        "severity",
        "description",
        "status",
        "violationCount",
        "sampleViolations",
        "recommendation",
        "learnMoreUrl",
        "dismissed",
    ]
    assert RuleResult.evaluate(RULE, ["x"]).to_dto()["sampleViolations"] == ["x"]
