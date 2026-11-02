"""A malformed baseline never turns sharpit off: the session runs and reports it as an unknown reason."""

from __future__ import annotations

import json

import pytest

_BAD = {
    "bad_json": "{not json",
    "wrong_schema": '{"schema":"other/9","findings":[]}',
    "wrong_version": '{"schema":"sharpit-baseline/2","findings":[]}',
    "deeply_nested": "[" * 100_000,
}


def _report(pytester: pytest.Pytester) -> dict[str, object]:
    path = pytester.path / "report.json"
    assert path.exists(), "sharpit wrote no report: the bad baseline turned it off"
    return json.loads(path.read_text(encoding="utf-8"))


def _run(pytester: pytest.Pytester, *extra: str) -> tuple[pytest.RunResult, dict[str, object]]:
    pytester.makepyfile("def test_x(): pass")
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-report=report.json", "-q", *extra
    )
    assert result.ret != 4, "a bad baseline must not be a usage error that stops sharpit"
    return result, _report(pytester)


@pytest.mark.parametrize("content", _BAD.values(), ids=_BAD.keys())
def test_bad_baseline_usage_error_at_session_start(pytester: pytest.Pytester, content: str) -> None:
    (pytester.path / "b.json").write_text(content, encoding="utf-8")
    result, report = _run(pytester, "--sharpit-report-only", "--sharpit-baseline=b.json")
    assert result.ret == 1
    assert any("baseline unusable" in reason for reason in report["unknownReasons"])  # type: ignore[union-attr]


def test_unreadable_baseline_is_unknown(pytester: pytest.Pytester) -> None:
    (pytester.path / "b.json").mkdir()
    result, report = _run(pytester, "--sharpit-report-only", "--sharpit-baseline=b.json")
    assert result.ret == 1
    assert any("baseline unusable" in reason for reason in report["unknownReasons"])  # type: ignore[union-attr]


def test_bad_baseline_allowed_unknown_exits_zero(pytester: pytest.Pytester) -> None:
    (pytester.path / "b.json").write_text("[" * 100_000, encoding="utf-8")
    result, report = _run(pytester, "--sharpit-report-only", "--sharpit-allow-unknown", "--sharpit-baseline=b.json")
    assert result.ret == 0
    assert report["baseline"] is None
