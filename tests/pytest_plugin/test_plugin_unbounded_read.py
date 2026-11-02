"""Unbounded ORM reads against the F2 spike fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "unbounded_read"
RULE = "sharpit.unbounded-read"


def _spike_project(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        fixture=(FIXTURE / "fixture.py").read_text("utf-8"),
        test_teams="from fastapi.testclient import TestClient\nfrom fixture import app\n\ndef test_page():\n    response = TestClient(app).get('/teams?skip=0&limit=5')\n    assert response.json() == [f'team-{i}' for i in range(5)]",
    )
    pytester.makeconftest((FIXTURE / "conftest.py").read_text("utf-8"))


def _report(pytester: pytest.Pytester) -> dict[str, Any]:
    return json.loads((pytester.path / "report.json").read_text("utf-8"))


def test_spike_f2_unbounded_read_found(pytester: pytest.Pytester) -> None:
    # spike: F2
    _spike_project(pytester)
    pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=fixture:app", "--sharpit-report=report.json", "-q"
    )
    data = _report(pytester)
    findings = [finding for finding in data["findings"] if finding["ruleId"] == RULE]
    assert findings, f"no {RULE} finding for 52 materialized Team rows and page size 5"
    assert "Team" in findings[0]["message"]
    assert "52" in findings[0]["message"]
    assert "5" in findings[0]["message"]


def test_f2_report_names_materialized_rows_and_page_size(pytester: pytest.Pytester) -> None:
    # spike: F2
    _spike_project(pytester)
    pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-app=fixture:app", "--sharpit-report=report.json", "-q"
    )
    findings = [finding for finding in _report(pytester)["findings"] if finding["ruleId"] == RULE]
    assert findings, "F2 spike did not report an unbounded read"
    message = findings[0]["message"]
    assert "Team" in message
    assert "52" in message
    assert "5" in message
