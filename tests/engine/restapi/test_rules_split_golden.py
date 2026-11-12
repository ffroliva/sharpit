"""Characterize ordered REST API findings before splitting the rule implementations."""

import json
from pathlib import Path

from sharpit.engine.collectors.restapi.rules import RULES, SKIPPED_RULES
from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.spi import ApiModel


def test_restapi_findings_match_pre_split_golden():
    from test_restapi_report import HANDLERS, ROUTES

    run = assess(ApiModel(ROUTES, HANDLERS, ()), Masker(Exposure.MASKED, True))
    actual = [
        {"ruleId": finding.rule_id, "message": finding.message, "location": finding.target} for finding in run.findings
    ]
    from test_restapi_findings import CASES

    for routes, handlers, _ in CASES.values():
        case = assess(ApiModel(routes, handlers, ()), Masker(Exposure.MASKED, True))
        actual.extend(
            {"ruleId": finding.rule_id, "message": finding.message, "location": finding.target}
            for finding in case.findings
        )
    golden = json.loads(Path(__file__).with_name("restapi_rules_split_golden.json").read_text(encoding="utf-8"))
    lane_rules = {"RAPI-ERR-004", "RAPI-ERR-005", "RAPI-ERR-007", "RAPI-ERR-008", "RAPI-ERR-010", "RAPI-ERR-011"}
    expected_rule_ids = ({rule.id for rule in RULES} - SKIPPED_RULES.keys()) - lane_rules
    assert {finding["ruleId"] for finding in golden} == expected_rule_ids
    assert [f for f in actual if f["ruleId"] not in lane_rules] == golden
