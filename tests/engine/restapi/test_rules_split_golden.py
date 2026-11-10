"""Characterize ordered REST API findings before splitting the rule implementations."""

import json
from pathlib import Path

from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.spi import ApiModel


def test_restapi_findings_match_pre_split_golden():
    from test_restapi_report import HANDLERS, ROUTES

    run = assess(ApiModel(ROUTES, HANDLERS, ()), Masker(Exposure.MASKED, True))
    actual = [
        {"ruleId": finding.rule_id, "message": finding.message, "location": finding.target} for finding in run.findings
    ]
    golden = Path(__file__).with_name("restapi_rules_split_golden.json")
    assert actual == json.loads(golden.read_text(encoding="utf-8"))
