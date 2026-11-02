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


_SINGLE = ["--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q"]


def _two_tests(pytester: pytest.Pytester, ini: str = "") -> None:
    pytester.makepyfile("import pytest\ndef test_x(): pass\n@pytest.mark.slow\ndef test_y(): pass")
    pytester.makeini(f"[pytest]\nmarkers = slow\n{ini}")


def _refused(pytester: pytest.Pytester, result: pytest.RunResult) -> None:
    assert result.ret == 4
    assert "refusing to write baseline: partial run" in result.stdout.str() + result.stderr.str()
    assert not (pytester.path / "b.json").exists()


def test_write_baseline_refused_on_single_process_deselection(pytester: pytest.Pytester) -> None:
    _two_tests(pytester, "addopts = -k x")
    _refused(pytester, pytester.runpytest_subprocess(*_SINGLE, "--sharpit-write-baseline=b.json"))


def test_write_baseline_refused_on_single_process_marker_addopts(pytester: pytest.Pytester) -> None:
    _two_tests(pytester, 'addopts = -m "not slow"')
    _refused(pytester, pytester.runpytest_subprocess(*_SINGLE, "--sharpit-write-baseline=b.json"))


def test_write_baseline_refused_on_conftest_deselection(pytester: pytest.Pytester) -> None:
    _two_tests(pytester)
    pytester.makeconftest(
        "def pytest_collection_modifyitems(config, items):\n"
        " gone = [i for i in items if i.name == 'test_y']\n"
        " items[:] = [i for i in items if i.name != 'test_y']\n"
        " config.hook.pytest_deselected(items=gone)"
    )
    _refused(pytester, pytester.runpytest_subprocess(*_SINGLE, "--sharpit-write-baseline=b.json"))


def test_single_process_deselection_keeps_fixed_null(pytester: pytest.Pytester) -> None:
    _two_tests(pytester, "addopts = -k x")
    (pytester.path / "previous.json").write_text(
        '{"schema":"sharpit-baseline/1","findings":[{"fingerprint":"old",'
        '"ruleId":"R","target":"t","message":"m","observed":null}]}',
        encoding="utf-8",
    )
    pytester.runpytest_subprocess(*_SINGLE, "--sharpit-baseline=previous.json", "--sharpit-report=report.json")
    data = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert data["baseline"]["fixed"] is None
    assert data["baseline"]["fixedReason"] == "partial run"


@pytest.mark.parametrize("selection", [["-k", "x"], ["-m", "not slow"]])
def test_write_baseline_refused_on_single_process_command_line_selection(
    pytester: pytest.Pytester, selection: list[str]
) -> None:
    # characterisation: command-line -k/-m were already caught by the argument scan
    _two_tests(pytester)
    _refused(pytester, pytester.runpytest_subprocess(*_SINGLE, *selection, "--sharpit-write-baseline=b.json"))


def test_single_process_keyword_addopts_keeps_fixed_null(pytester: pytest.Pytester) -> None:
    # supersedes test_single_process_deselection_keeps_fixed_null, whose `-k x` also matched its own module name
    pytester.makepyfile("def test_a(): pass\ndef test_b(): pass")
    pytester.makeini("[pytest]\naddopts = -k test_a")
    (pytester.path / "previous.json").write_text(
        '{"schema":"sharpit-baseline/1","findings":[{"fingerprint":"old",'
        '"ruleId":"R","target":"t","message":"m","observed":null}]}',
        encoding="utf-8",
    )
    pytester.runpytest_subprocess(*_SINGLE, "--sharpit-baseline=previous.json", "--sharpit-report=report.json")
    data = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert data["baseline"]["fixed"] is None
    assert data["baseline"]["fixedReason"] == "partial run"
