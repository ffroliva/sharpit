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
    expected_rule_ids = {rule.id for rule in RULES} - SKIPPED_RULES.keys()
    assert {finding["ruleId"] for finding in golden} == expected_rule_ids
    assert actual == golden
