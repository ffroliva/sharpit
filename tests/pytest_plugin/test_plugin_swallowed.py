"""Swallowed application exceptions observed with sys.monitoring during a test session (spec 0.4.0 §5.5 F1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "swallowed_exception"
RULE = "sharpit.swallowed-exception"


def _week_project(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        weekapp=(FIXTURE / "weekapp.py").read_text("utf-8"),
        test_weeks=(FIXTURE / "cases.py").read_text("utf-8"),
    )


def _report(pytester: pytest.Pytester) -> dict[str, Any]:
    return json.loads((pytester.path / "report.json").read_text("utf-8"))


def _test_entry(data: dict[str, Any], name: str) -> dict[str, Any]:
    return next(t for t in data["tests"] if t["nodeId"].endswith(f"::{name}"))


def test_spike_f1_swallowed_attribute_error_fails(pytester: pytest.Pytester) -> None:
    # spike: F1 T4
    _week_project(pytester)

    pytester.runpytest_subprocess("--sharpit", "--sharpit-app=weekapp:app", "--sharpit-report=report.json", "-q")

    data = _report(pytester)
    planted = [f for f in data["findings"] if f["ruleId"] == RULE and f["testNodeId"].endswith("::test_week_count")]
    assert planted, f"no {RULE} finding for the planted handler: {[f['ruleId'] for f in data['findings']]}"
    assert _test_entry(data, "test_week_count")["outcome"] == "failed"
