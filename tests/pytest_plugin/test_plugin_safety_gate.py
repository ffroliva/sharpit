from __future__ import annotations

import json

import pytest

_SQL = "import sqlite3\nconn = sqlite3.connect(':memory:')\nfor _ in range(5): conn.execute('SELECT 1').fetchone()"
_GATE = ["--sharpit", "--sharpit-no-advisors", "-q"]
_SQL_GATE = [*_GATE, "--sharpit-allow-unknown"]


def _test_source(*names: str) -> str:
    body = _SQL.replace("\n", "\n    ")
    return "\n\n".join(f"def {name}():\n    {body}" for name in names)


def test_gate_failure_exits_nonzero(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(_test_source("test_repeated_selects"))

    result = pytester.runpytest_inprocess(*_SQL_GATE, "--sharpit-report=report.json")

    assert result.ret == 1
    assert "sharpit: sharpit.n-plus-one" in result.stdout.str()


def test_gate_does_not_hide_a_failing_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(_test_source("test_repeated_selects") + "\n    assert False, 'pytest failure'")

    result = pytester.runpytest_inprocess(*_SQL_GATE, "--sharpit-report=report.json")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert "pytest failure" in result.stdout.str()
    assert "sharpit: sharpit.n-plus-one" in result.stdout.str()


def test_gate_failure_never_overwrites_a_nonzero_pytest_status(pytester: pytest.Pytester) -> None:
    # exit code 3 is neither 0 nor the gate's own 1, so a gate that overwrote pytest's status would show
    pytester.makepyfile(
        "import pytest\n\n"
        + _test_source("test_repeated_selects", "test_halts")
        + "\n    pytest.exit('halt', returncode=3)"
    )

    result = pytester.runpytest_inprocess(*_SQL_GATE, "--sharpit-report=report.json")

    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "fail"
    assert result.ret == 3


def test_report_only_preserves_pytest_test_failure(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(_test_source("test_repeated_selects") + "\n    assert False, 'pytest failure'")

    result = pytester.runpytest_inprocess(*_SQL_GATE, "--sharpit-report-only", "--sharpit-report=report.json")

    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert "sharpit report-only" in result.stdout.str()


def test_unreadable_baseline_fails_closed_in_report_only(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_clean(): pass")
    (pytester.path / "baseline.json").mkdir()

    result = pytester.runpytest_inprocess(
        *_GATE,
        "--sharpit-report-only",
        "--sharpit-baseline=baseline.json",
        "--sharpit-report=report.json",
    )

    assert result.ret == 1
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert any("baseline unusable" in reason for reason in report["unknownReasons"])


def test_baseline_allows_existing_finding_but_gates_new_one(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Subprocesses: a driver another test imported into this worker would make the write run refuse (unknown).
    # A shared key (>= 32 chars) keeps SQLite fingerprints stable between the write and the gated run on any machine.
    monkeypatch.setenv("SHARPIT_IDENTITY_KEY", "pytest-safety-gate-baseline-identity-key0")
    pytester.makepyfile(_test_source("test_existing"))
    written = pytester.runpytest_subprocess(
        *_SQL_GATE, "--sharpit-write-baseline=baseline.json", "--sharpit-report=write.json"
    )
    write_report = json.loads((pytester.path / "write.json").read_text(encoding="utf-8"))
    assert (pytester.path / "baseline.json").is_file(), (written.ret, write_report["unknownReasons"])
    pytester.makepyfile(_test_source("test_existing", "test_new"))

    result = pytester.runpytest_subprocess(
        *_SQL_GATE, "--sharpit-baseline=baseline.json", "--sharpit-report=report.json"
    )

    assert result.ret == 1
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert {finding["baselineState"] for finding in report["findings"]} == {"existing", "new"}
