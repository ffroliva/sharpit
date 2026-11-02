from __future__ import annotations

import json

import pytest


def test_report_only_does_not_fail_finding_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        "import sqlite3\ndef test_repeated_selects():\n"
        " c=sqlite3.connect(':memory:')\n"
        " for _ in range(5): c.execute('SELECT 1').fetchone()"
    )
    result = pytester.runpytest_subprocess(
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-report-only",
        "--sharpit-report=report.json",
        "--sharpit-junit=junit.xml",
        "-q",
    )
    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert data["mode"] == "report-only"
    assert any(finding["advisor"] == "test-runtime" for finding in data["findings"])
    assert "<failure" not in (pytester.path / "junit.xml").read_text(encoding="utf-8")
    assert "sharpit report-only: 1 tests would fail, status fail" in result.stdout.str()
