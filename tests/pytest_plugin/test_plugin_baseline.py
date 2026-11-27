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
    result = pytester.runpytest_inprocess(
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
    _refused(pytester, pytester.runpytest_inprocess(*_SINGLE, "--sharpit-write-baseline=b.json"))


def test_write_baseline_refused_on_single_process_marker_addopts(pytester: pytest.Pytester) -> None:
    _two_tests(pytester, 'addopts = -m "not slow"')
    _refused(pytester, pytester.runpytest_inprocess(*_SINGLE, "--sharpit-write-baseline=b.json"))


def test_write_baseline_refused_on_conftest_deselection(pytester: pytest.Pytester) -> None:
    _two_tests(pytester)
    pytester.makeconftest(
        "def pytest_collection_modifyitems(config, items):\n"
        " gone = [i for i in items if i.name == 'test_y']\n"
        " items[:] = [i for i in items if i.name != 'test_y']\n"
        " config.hook.pytest_deselected(items=gone)"
    )
    _refused(pytester, pytester.runpytest_inprocess(*_SINGLE, "--sharpit-write-baseline=b.json"))


@pytest.mark.parametrize("selection", [["-k", "x"], ["-m", "not slow"]])
def test_write_baseline_refused_on_single_process_command_line_selection(
    pytester: pytest.Pytester, selection: list[str]
) -> None:
    # characterisation: command-line -k/-m were already caught by the argument scan
    _two_tests(pytester)
    _refused(pytester, pytester.runpytest_inprocess(*_SINGLE, *selection, "--sharpit-write-baseline=b.json"))


def test_single_process_keyword_addopts_keeps_fixed_null(pytester: pytest.Pytester) -> None:
    # supersedes test_single_process_deselection_keeps_fixed_null, whose `-k x` also matched its own module name
    pytester.makepyfile("def test_a(): pass\ndef test_b(): pass")
    pytester.makeini("[pytest]\naddopts = -k test_a")
    (pytester.path / "previous.json").write_text(
        '{"schema":"sharpit-baseline/1","findings":[{"fingerprint":"old",'
        '"ruleId":"R","target":"t","message":"m","observed":null}]}',
        encoding="utf-8",
    )
    pytester.runpytest_inprocess(*_SINGLE, "--sharpit-baseline=previous.json", "--sharpit-report=report.json")
    data = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert data["baseline"]["fixed"] is None
    assert data["baseline"]["fixedReason"] == "partial run"


def test_write_baseline_requires_path(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_a(): pass")
    result = pytester.runpytest_inprocess(*_SINGLE, "--sharpit-write-baseline")
    assert result.ret == 4
    assert list(pytester.path.glob("*baseline*.json")) == []


def test_write_baseline_ini_option_writes_nothing(pytester: pytest.Pytester) -> None:
    # spec: the flag is the only way to write a baseline
    pytester.makepyfile("def test_a(): pass")
    pytester.makeini("[pytest]\nsharpit_write_baseline = b.json")
    pytester.runpytest_inprocess(*_SINGLE)
    assert not (pytester.path / "b.json").exists()


def _complete_write(pytester: pytest.Pytester, *extra: str) -> pytest.RunResult:
    pytester.makepyfile(test_mod="def test_a(): pass")
    (pytester.path / "sub").mkdir()
    (pytester.path / "sub" / "test_sub.py").write_text("def test_b(): pass", encoding="utf-8")
    return pytester.runpytest_subprocess(*_SINGLE, *extra, "--sharpit-write-baseline=b.json")


def test_warning_filter_is_not_selection(pytester: pytest.Pytester) -> None:
    result = _complete_write(pytester, "-W", "ignore::DeprecationWarning")
    assert (pytester.path / "b.json").exists(), result.stdout.str()


def test_maxfail_without_stop_is_complete(pytester: pytest.Pytester) -> None:
    result = _complete_write(pytester, "--maxfail=5")
    assert (pytester.path / "b.json").exists(), result.stdout.str()


def test_directory_argument_is_partial(pytester: pytest.Pytester) -> None:
    _refused(pytester, _complete_write(pytester, "sub"))


def test_ignore_option_is_partial(pytester: pytest.Pytester) -> None:
    _refused(pytester, _complete_write(pytester, "--ignore=sub"))


def test_baseline_write_failure_is_reported_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_a(): pass")
    (pytester.path / "b.json").mkdir()  # os.replace onto a directory fails
    result = pytester.runpytest_subprocess(
        *_SINGLE[:-2], "-q", "--sharpit-report=report.json", "--sharpit-write-baseline=b.json"
    )
    report = json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))
    assert any("baseline write failed" in reason for reason in report["unknownReasons"]), report["unknownReasons"]
    assert report["status"] != "pass"
    assert "baseline write failed" in result.stdout.str()
    assert result.ret == 1


# --- an entry whose owner did not prove it fixed is inconclusive, not fixed (#329) ---------------------------------

_N1_BODY = " c=sqlite3.connect(':memory:')\n for _ in range(30): c.execute('SELECT 1').fetchone()\n"
_N1_TEST = f"import sqlite3\ndef test_n1():\n{_N1_BODY}\ndef test_other(): pass\n"
_RUN = ["--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q"]
DID_NOT_RUN = "its test did not run"
DID_NOT_COMPLETE = "its test did not complete"
STILL_SHOWN = "its test still shows it outside the gate"
INCOMPLETE = "the run's evidence is incomplete"


def _write_first_baseline(pytester: pytest.Pytester) -> str:
    """Run the suite once with the finding present; return the fingerprint written for it."""
    pytester.makepyfile(test_a=_N1_TEST)
    pytester.runpytest_subprocess(*_RUN, "--sharpit-write-baseline=baseline.json")
    rows = json.loads((pytester.path / "baseline.json").read_text(encoding="utf-8"))["findings"]
    assert len(rows) == 1, "the first run must baseline exactly the one N+1 finding"
    return rows[0]["fingerprint"]


def _changed_run(pytester: pytest.Pytester, source: str, *extra: str, workers: bool = False) -> dict:
    pytester.makepyfile(test_a=source)
    args = ["-n", "2"] if workers else []
    pytester.runpytest_subprocess(
        *args, *_RUN, "--sharpit-baseline=baseline.json", "--sharpit-report=report.json", *extra
    )
    return json.loads((pytester.path / "report.json").read_text(encoding="utf-8"))["baseline"]


def _only_reason(result: dict, fingerprint: str, reason: str) -> None:
    assert result["fixed"] == 0
    assert result.get("inconclusiveFindings") == [{"fingerprint": fingerprint, "reason": reason}]


def test_issue_329_deleted_test_is_not_fixed(pytester: pytest.Pytester) -> None:
    fingerprint = _write_first_baseline(pytester)
    result = _changed_run(pytester, "def test_other(): pass\n")
    _only_reason(result, fingerprint, DID_NOT_RUN)


def test_skip_marker_on_the_owner_is_not_fixed(pytester: pytest.Pytester) -> None:
    fingerprint = _write_first_baseline(pytester)
    skipped = f"import pytest, sqlite3\n@pytest.mark.skip\ndef test_n1():\n{_N1_BODY}\ndef test_other(): pass\n"
    _only_reason(_changed_run(pytester, skipped), fingerprint, DID_NOT_COMPLETE)


def test_crashed_xdist_worker_is_not_fixed(pytester: pytest.Pytester) -> None:
    fingerprint = _write_first_baseline(pytester)
    crashed = "import os\ndef test_n1(): os._exit(1)\ndef test_other(): pass\n"
    _only_reason(_changed_run(pytester, crashed, workers=True), fingerprint, INCOMPLETE)


def test_dropped_sql_events_are_not_fixed(pytester: pytest.Pytester) -> None:
    fingerprint = _write_first_baseline(pytester)
    pytester.makeconftest(
        "from sharpit.engine.testsession.sink import TestSessionSink\n"
        "def broken(*args, **kwargs): raise RuntimeError('injected')\n"
        "TestSessionSink.begin_test = broken\n"
    )
    _only_reason(_changed_run(pytester, _N1_TEST), fingerprint, INCOMPLETE)


def test_request_moved_to_a_fixture_is_not_fixed(pytester: pytest.Pytester) -> None:
    fingerprint = _write_first_baseline(pytester)
    moved = (
        "import pytest, sqlite3\n@pytest.fixture\ndef rows():\n"
        f"{_N1_BODY}\ndef test_n1(rows): pass\ndef test_other(): pass\n"
    )
    _only_reason(_changed_run(pytester, moved), fingerprint, STILL_SHOWN)


def test_write_keeps_an_inconclusive_entry(pytester: pytest.Pytester) -> None:
    fingerprint = _write_first_baseline(pytester)
    before = json.loads((pytester.path / "baseline.json").read_text(encoding="utf-8"))["findings"]
    _changed_run(pytester, "def test_other(): pass\n", "--sharpit-write-baseline=baseline.json")
    after = json.loads((pytester.path / "baseline.json").read_text(encoding="utf-8"))["findings"]
    assert [row["fingerprint"] for row in after] == [fingerprint]
    assert after[0]["owner"] == before[0]["owner"]


def test_report_lists_inconclusive_with_reason(pytester: pytest.Pytester) -> None:
    fingerprint = _write_first_baseline(pytester)
    result = _changed_run(pytester, "def test_other(): pass\n")
    assert result.get("inconclusive") == 1
    assert result.get("inconclusiveFindings") == [{"fingerprint": fingerprint, "reason": DID_NOT_RUN}]


@pytest.mark.parametrize("workers", [False, True], ids=["serial", "xdist"])
def test_fixed_for_a_real_fix_serial_and_xdist(pytester: pytest.Pytester, workers: bool) -> None:
    _write_first_baseline(pytester)
    fixed = "import sqlite3\ndef test_n1():\n c=sqlite3.connect(':memory:')\n c.execute('SELECT 1').fetchone()\n"
    fixed += "def test_other(): pass\n"
    result = _changed_run(pytester, fixed, workers=workers)
    assert result["fixed"] == 1
    assert result["inconclusive"] == 0
