from __future__ import annotations

import json

import pytest


def test_write_baseline_refused_on_partial_xdist_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_x(): pass\ndef test_y(): pass")
    result = pytester.runpytest_subprocess(
        "-n",
        "2",
        "-k",
        "x",
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-write-baseline=baseline.json",
        "-q",
    )
    assert result.ret == 4
    output = result.stdout.str() + result.stderr.str()
    assert "refusing to write baseline: partial run" in output
    assert not (pytester.path / "baseline.json").exists()


def test_write_baseline_is_only_writer(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        "import sqlite3\ndef test_repeated_selects():\n"
        " c=sqlite3.connect(':memory:')\n"
        " for _ in range(5): c.execute('SELECT 1').fetchone()"
    )
    args = ["--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"]
    pytester.runpytest_subprocess(*args)
    unbased = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert unbased["baseline"] is None
    assert unbased["findings"][0]["baselineState"] is None
    assert unbased["findings"][0]["observed"] is not None
    path = pytester.path / "baseline.json"
    assert path.exists() is False
    pytester.runpytest_subprocess(*args, "--sharpit-write-baseline=baseline.json")
    assert path.exists() is True
    loaded = pytester.runpytest_subprocess(*args, "--sharpit-baseline=baseline.json")
    assert loaded.ret == 0
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert report["baseline"]["existing"] == 1
    assert report["baseline"]["new"] == 0
    assert report["baseline"]["fixed"] == 0
    assert report["findings"][0]["baselineState"] == "existing"


def test_partial_xdist_report_keeps_fixed_null(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_x(): pass\ndef test_y(): pass")
    (pytester.path / "previous.json").write_text(
        '{"schema":"sharpit-baseline/1","findings":[{"fingerprint":"old",'
        '"ruleId":"R","target":"t","message":"m","observed":null}]}',
        encoding="utf-8",
    )
    result = pytester.runpytest_subprocess(
        "-n",
        "2",
        "-k",
        "x",
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-baseline=previous.json",
        "--sharpit-write-baseline=next.json",
        "--sharpit-report=report.json",
        "-q",
    )
    assert result.ret == 4
    data = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert data["baseline"]["fixed"] is None
    assert data["baseline"]["fixedReason"] == "partial run"
    assert (pytester.path / "next.json").exists() is False


def test_write_baseline_refuses_unknown_even_when_status_fails(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        "import sqlite3\ndef test_repeated_selects():\n"
        " c=sqlite3.connect(':memory:')\n"
        " for _ in range(5): c.execute('SELECT 1').fetchone()"
    )
    result = pytester.runpytest_subprocess(
        "--sharpit",
        "--sharpit-require-app",
        "--sharpit-report=report.json",
        "--sharpit-write-baseline=baseline.json",
        "-q",
    )
    assert result.ret == 4
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "fail"
    assert report["unknownReasons"]
    assert (pytester.path / "baseline.json").exists() is False


def test_baseline_loaded_on_every_xdist_worker(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        "import sqlite3\ndef test_x():\n"
        " c=sqlite3.connect(':memory:')\n"
        " for _ in range(5): c.execute('SELECT 1').fetchone()\n"
        "def test_y():\n"
        " c=sqlite3.connect(':memory:')\n"
        " for _ in range(5): c.execute('SELECT 1').fetchone()"
    )
    common = ["-n", "2", "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q"]
    pytester.runpytest_subprocess(*common, "--sharpit-write-baseline=baseline.json")
    result = pytester.runpytest_subprocess(*common, "--sharpit-baseline=baseline.json", "--sharpit-report=report.json")
    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert all(finding["baselineState"] == "existing" for finding in data["findings"])
