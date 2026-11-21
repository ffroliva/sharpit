"""A test double's swallowed exception, end to end under pytester (issue 68)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "apps" / "swallowed_test_double"
RULE = "sharpit.swallowed-exception"
NOTE = "a test double raised this, so this code path did not run"
ARGS = (
    "--sharpit",
    "--sharpit-no-advisors",
    "--sharpit-allow-unknown",
    "--sharpit-report=report.json",
    "--sharpit-sarif=report.sarif",
    "-q",
)


def _run(pytester: pytest.Pytester) -> pytest.RunResult:
    pytester.makepyfile(
        doubleapp=(FIXTURE / "doubleapp.py").read_text("utf-8"), test_double=(FIXTURE / "cases.py").read_text("utf-8")
    )
    return pytester.runpytest_subprocess(*ARGS)


def _finding(data: dict[str, Any], test: str) -> dict[str, Any]:
    found = next((f for f in data["findings"] if f["ruleId"] == RULE and f["testNodeId"].endswith(f"::{test}")), None)
    assert found is not None, f"no {RULE} finding for {test}: {[f['testNodeId'] for f in data['findings']]}"
    return found


def test_a_swallowed_magic_mock_await_is_named_in_the_report(pytester: pytest.Pytester) -> None:
    _run(pytester)

    found = _finding(json.loads((pytester.path / "report.json").read_text("utf-8")), "test_label_with_a_mocked_client")

    assert NOTE in found["message"]
    assert found["severity"] == "HIGH"


def test_sarif_carries_the_test_double_note(pytester: pytest.Pytester) -> None:
    _run(pytester)

    sarif = json.loads((pytester.path / "report.sarif").read_text("utf-8"))

    texts = [r["message"]["text"] for r in sarif["runs"][0]["results"] if r["ruleId"] == RULE]
    assert sum(NOTE in text for text in texts) == 1


def test_the_summary_groups_swallowed_findings_by_clause(pytester: pytest.Pytester) -> None:
    result = _run(pytester)

    lines = (FIXTURE / "doubleapp.py").read_text("utf-8").splitlines()
    handlers = [number for number, line in enumerate(lines, 1) if line.strip() == "except Exception:"]
    summary = [line for line in result.outlines if line.startswith(("swallowed exceptions:", "  doubleapp.py:"))]
    assert summary == [
        "swallowed exceptions: 2 clauses, 2 tests",
        f"  doubleapp.py:{handlers[0]}: 1 test, {NOTE}",
        f"  doubleapp.py:{handlers[1]}: 1 test",
    ]
