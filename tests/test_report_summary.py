"""The report summary renderer and its CLI (spec 0.4.0 section 5.3)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sharpit.report.__main__ import main
from sharpit.report.summary import render_summary

FIXTURES = Path(__file__).parent / "fixtures"


def _finding(n: int, severity: str = "LOW", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ruleId": "n-plus-one",
        "advisor": "n-plus-one",
        "severity": severity,
        "target": f"tests/test_a.py::test_{n}",
        "message": "text",
        "fingerprint": f"fp{n:04d}",
        "testNodeId": None,
        "dismissed": False,
        "observed": None,
        "baselineState": None,
    }
    return base | over


def _report(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": "sharpit-report/1",
        "status": "pass",
        "statusReasons": [],
        "mode": "gate",
        "unknownReasons": [],
        "baseline": None,
        "totals": {"tests": 1, "queries": 3},
        "findings": [],
        "futureKey": {"ignored": True},
    }
    return base | over


def _golden_report() -> dict[str, object]:
    return _report(
        status="fail",
        totals={"tests": 2, "queries": 14},
        findings=[
            _finding(1, "HIGH", fingerprint="b", message="Repeated query `SELECT 1`"),
            _finding(
                2,
                "CRITICAL",
                ruleId="max-queries",
                fingerprint="a",
                target="tests/test_b.py::test_y",
                message="12 queries | budget 10",
            ),
        ],
    )


def _golden_report_with_baseline() -> dict[str, object]:
    return _report(
        status="unknown",
        mode="report-only",
        unknownReasons=["advisor did not finish"],
        baseline={
            "path": "b.json",
            "sha256": "0" * 64,
            "existing": 1,
            "new": 0,
            "fixed": None,
            "fixedReason": "partial run",
        },
        findings=[_finding(1, baselineState="existing")],
    )


def test_summary_golden() -> None:
    assert render_summary(_golden_report()) == (FIXTURES / "report-summary.md").read_text(encoding="utf-8")


def test_summary_has_status_mode_totals() -> None:
    text = render_summary(_golden_report())
    assert "**Status:** fail" in text
    assert "**Mode:** gate" in text
    assert "**Tests:** 2" in text
    assert "**Queries:** 14" in text


def test_summary_includes_baseline_counts_when_present() -> None:
    expected = (FIXTURES / "report-summary-baseline.md").read_text(encoding="utf-8")
    assert render_summary(_golden_report_with_baseline()) == expected


def test_summary_without_baseline_is_stable() -> None:
    report = _golden_report()
    assert render_summary(report) == render_summary(report)
    assert "Baseline:**" not in render_summary(report)


def test_summary_escapes_markdown_values() -> None:
    nasty = "a|b [x](http://e) `c` <img src=x> *m* _u_\nline2\r\nline3"
    text = render_summary(_report(findings=[_finding(1, message=nasty, target=nasty, ruleId=nasty)]))
    row = next((line for line in text.splitlines() if line.startswith("| LOW")), "")
    assert "\n" not in row
    assert "<img" not in row.replace(r"\<", "")
    assert "[x]" not in row
    assert "`c`" not in row
    assert r"a\|b" in row
    assert row.count("|") - row.count(r"\|") == 6


def test_summary_limits_findings_to_top_20_and_reports_totals() -> None:
    findings = [_finding(n, "LOW") for n in range(30)]
    findings.append(_finding(99, "CRITICAL", target="tests/test_crit.py::t"))
    text = render_summary(_report(findings=findings))
    rows = [line for line in text.splitlines() if line.startswith(("| LOW", "| CRITICAL"))]
    assert len(rows) == 20
    assert "crit" in rows[0]
    assert "**Findings:** 31" in text
    assert "showing 20 of 31" in text


def test_summary_renders_unknown_reasons_even_when_status_is_fail() -> None:
    text = render_summary(_report(status="fail", unknownReasons=["capture <b>incomplete</b>"]))
    assert r"unknown: capture \<b\>incomplete\</b\>" in text


def test_summary_cli_reads_report_and_writes_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "r.json"
    path.write_text(json.dumps(_golden_report()), encoding="utf-8")
    assert main(["summary", str(path)]) == 0
    assert capsys.readouterr().out == render_summary(_golden_report())


def test_summary_cli_invalid_json_returns_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "r.json"
    path.write_text("{not json", encoding="utf-8")
    assert main(["summary", str(path)]) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert captured.err.startswith("sharpit.report:")


def test_summary_cli_missing_file_returns_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["summary", str(tmp_path / "nope.json")]) != 0
    assert capsys.readouterr().err.startswith("sharpit.report:")


def test_summary_cli_runs_as_module(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    path.write_text(json.dumps(_golden_report()), encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "sharpit.report", "summary", str(path)], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0
    assert done.stdout.startswith("## sharpit report")


def test_backslash_in_finding_text_is_escaped_too() -> None:
    # finding: a pre-escaped value (`\[x\](https://evil)`) must not turn back into a live link or raw HTML
    from sharpit.report.summary import _esc  # pyright: ignore[reportPrivateUsage]

    assert _esc(r"\[x\](https://evil)") == r"\\\[x\\\](https://evil)"
