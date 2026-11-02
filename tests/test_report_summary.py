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


def _run_module(path: Path) -> subprocess.CompletedProcess[bytes]:
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    return subprocess.run(
        [sys.executable, "-m", "sharpit.report", "summary", str(path)], capture_output=True, env=env, check=False
    )


def test_summary_cli_writes_utf8_regardless_of_console_code_page(tmp_path: Path) -> None:
    # finding: a non-cp1252 message crashed the CLI with UnicodeEncodeError on a Windows runner
    path = tmp_path / "r.json"
    path.write_text(json.dumps(_report(findings=[_finding(1, message="日本語 ✓ Ω")])), encoding="utf-8")
    done = _run_module(path)
    assert "日本語 ✓ Ω" in done.stdout.decode("utf-8", errors="replace"), done.stderr.decode(errors="replace")


def test_summary_cli_deeply_nested_json_fails_cleanly(tmp_path: Path) -> None:
    # finding: deeply nested JSON escaped as a RecursionError traceback instead of the sharpit.report error
    path = tmp_path / "r.json"
    path.write_text("[" * 200_000, encoding="utf-8")
    done = _run_module(path)
    assert done.stderr.decode(errors="replace").startswith("sharpit.report: "), done.stderr[-300:]


def test_summary_unknown_status_prints_each_reason_once() -> None:
    # finding: for an unknown run statusReasons == unknownReasons, so every reason printed twice
    out = render_summary(_report(status="unknown", statusReasons=["coverage gap"], unknownReasons=["coverage gap"]))
    assert out.count("coverage gap") == 1, out


def test_summary_excludes_dismissed_findings_from_count_and_table() -> None:
    # finding: dismissed findings were counted and listed, unlike severityCounts
    out = render_summary(_report(findings=[_finding(1, target="gone", dismissed=True), _finding(2)]))
    assert "- **Findings:** 1" in out, out
    assert "gone" not in out, out


def test_summary_orders_failing_findings_before_severity() -> None:
    # finding: a baselined HIGH outranked a failing LOW in the top 20
    findings = [_finding(1, "HIGH", target="old", baselineState="existing"), _finding(2, "LOW", target="new")]
    out = render_summary(_report(findings=findings))
    assert out.index("| new |") < out.index("| old |"), out


def test_summary_escapes_baseline_fixed() -> None:
    # finding: baseline.fixed was interpolated without _esc
    baseline = {"existing": 1, "new": 0, "fixed": "<b>x</b>"}
    out = render_summary(_report(baseline=baseline))
    assert "fixed \\<b\\>x\\</b\\>" in out, out


def test_summary_neutralises_bare_urls() -> None:
    # finding: GFM autolinked bare URLs in untrusted finding text
    from sharpit.report.summary import _esc  # pyright: ignore[reportPrivateUsage]

    assert _esc("go HTTPS://a.b/c, http://d and www.e.f") == "go HTTPS:​//a.b/c, http:​//d and www​.e.f"
