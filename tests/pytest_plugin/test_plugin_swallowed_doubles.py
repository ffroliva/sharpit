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


def test_swallowed_test_doubles_are_named_in_all_outputs(pytester: pytest.Pytester) -> None:
    result = _run(pytester)
    data = json.loads((pytester.path / "report.json").read_text("utf-8"))
    found_double = _finding(data, "test_label_with_a_mocked_client")
    found_real = _finding(data, "test_title_with_a_real_client")

    assert NOTE in found_double["message"]
    assert found_double["severity"] == "HIGH"
    assert NOTE not in found_real["message"]
    assert found_real["severity"] == "HIGH"
    result.assert_outcomes(failed=2)

    sarif = json.loads((pytester.path / "report.sarif").read_text("utf-8"))
    texts = [r["message"]["text"] for r in sarif["runs"][0]["results"] if r["ruleId"] == RULE]
    assert sum(NOTE in text for text in texts) == 1

    lines = (FIXTURE / "doubleapp.py").read_text("utf-8").splitlines()
    handlers = [number for number, line in enumerate(lines, 1) if line.strip() == "except Exception:"]
    summary = [line for line in result.outlines if line.startswith(("swallowed exceptions:", "  doubleapp.py:"))]
    assert summary == [
        "swallowed exceptions: 2 clauses, 2 tests",
        f"  doubleapp.py:{handlers[0]}: 1 test, {NOTE}",
        f"  doubleapp.py:{handlers[1]}: 1 test",
    ]


def test_application_message_starting_with_mock_is_not_a_double() -> None:
    from sharpit.engine.testsession.doubles import raised_by_test_double

    assert not raised_by_test_double(RuntimeError("Mock server unavailable"))


SECRET_APP = """
def read():
    try:
        raise TypeError("MagicMock token-s3cr3t-9f2")  # the text names a double and holds a secret
    except Exception:
        return None
"""


def test_the_exception_text_that_named_a_double_reaches_no_output(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        secretapp=SECRET_APP, test_secret="from secretapp import read\n\ndef test_read():\n    assert read() is None\n"
    )

    result = pytester.runpytest_subprocess(*ARGS)

    written = result.stdout.str() + (pytester.path / "report.json").read_text("utf-8")
    written += (pytester.path / "report.sarif").read_text("utf-8")
    assert NOTE in written
    assert "token-s3cr3t-9f2" not in written
