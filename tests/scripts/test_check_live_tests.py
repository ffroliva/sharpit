"""scripts/ci/check_live_tests.py: the live job passes only when the required tests ran, and none failed or skipped."""

from pathlib import Path

import pytest
from _load import load_script

check_live = load_script("scripts/ci/check_live_tests.py")

CASE = '<testcase classname="tests.live.test_a_server_answers" name="{name}"{body}</testcase>'
OUTCOMES = {"pass": ">", "skip": '><skipped message="no server"/>', "fail": '><failure message="boom"/>'}


def _report(
    tmp_path: Path, cases: list[tuple[str, str]], *, tests: int | None = None, counters: str | None = None
) -> Path:
    """A pytest-style JUnit file: cases are (name, outcome); ``tests`` overrides the suite's own counter."""
    body = "".join(CASE.format(name=n, body=OUTCOMES[o]) for n, o in cases)
    count = len(cases) if tests is None else tests
    skipped = sum(o == "skip" for _, o in cases)
    failures = sum(o == "fail" for _, o in cases)
    attributes = counters or f'errors="0" failures="{failures}" skipped="{skipped}"'
    xml = (
        f'<?xml version="1.0"?><testsuites><testsuite name="pytest" {attributes} '
        f'tests="{count}">{body}</testsuite></testsuites>'
    )
    path = tmp_path / "live.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def _run(report: Path, *required: str) -> int:
    return check_live.main([str(report), "--require", *required])


# ported: test_mysql_live_tests.py
def test_check_live_passes_a_clean_report(tmp_path: Path) -> None:
    report = _report(
        tmp_path, [("test_a_server_answers[mysql84]", "pass"), ("test_a_server_answers[postgresql]", "pass")]
    )
    assert _run(report, "test_a_server_answers") == 0


# ported: test_mysql_live_tests.py
def test_check_live_fails_on_a_skip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _report(tmp_path, [("test_a_server_answers[mysql84]", "pass"), ("test_a_server_answers[mariadb]", "skip")])
    assert _run(report, "test_a_server_answers") == 1
    assert "skip" in capsys.readouterr().err


# ported: test_mysql_live_tests.py
def test_check_live_fails_on_no_cases(tmp_path: Path) -> None:
    report = _report(tmp_path, [])
    assert _run(report, "test_a_server_answers") == 1


# ported: test_mysql_live_tests.py
def test_check_live_fails_on_a_missing_suite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _report(tmp_path, [("test_a_server_answers[mysql84]", "pass")])
    assert _run(report, "test_a_server_answers", "test_other") == 1
    assert "test_other" in capsys.readouterr().err


# ported: test_mysql_live_tests.py
def test_check_live_fails_on_inconsistent_counts(tmp_path: Path) -> None:
    report = _report(tmp_path, [("test_a_server_answers[mysql84]", "pass")], tests=3)
    assert _run(report, "test_a_server_answers") == 1


def test_check_live_fails_on_a_failure(tmp_path: Path) -> None:
    report = _report(tmp_path, [("test_a_server_answers[mysql84]", "fail")])
    assert _run(report, "test_a_server_answers") == 1


def test_check_live_fails_on_an_unreadable_report(tmp_path: Path) -> None:
    path = tmp_path / "live.xml"
    path.write_text("<testsuites", encoding="utf-8")
    assert _run(path, "test_a_server_answers") == 1


# ported: check-mysql-live-tests.py counters
@pytest.mark.parametrize("counters", ['errors="0" failures="0" skipped="1"', 'errors="1" failures="0" skipped="0"'])
def test_check_live_fails_when_the_suite_counters_report_a_skip_or_error_no_case_shows(
    tmp_path: Path, counters: str
) -> None:
    report = _report(tmp_path, [("test_a_server_answers[mysql84]", "pass")], counters=counters)
    assert _run(report, "test_a_server_answers") == 1


def test_check_live_fails_when_fewer_cases_ran_than_the_required_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _report(tmp_path, [("test_a_server_answers[mysql84]", "pass")])
    assert _run(report, "test_a_server_answers=4") == 1
    assert "expected 4 cases, found 1" in capsys.readouterr().err


def test_check_live_passes_when_the_required_count_ran(tmp_path: Path) -> None:
    names = ("mysql84", "mysql80", "mariadb", "postgresql")
    report = _report(tmp_path, [(f"test_a_server_answers[{n}]", "pass") for n in names])
    assert _run(report, "test_a_server_answers=4") == 0


def test_the_leg_count_reads_junit_and_requires_a_returned_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "live.xml"
    report.write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0">'
        '<testcase classname="tests.live.test_server_oracle" name="test_oracle_row[mysql84-default-0]">'
        '<properties><property name="returned" value="True"/></properties></testcase>'
        '<testcase classname="tests.live.test_server_oracle" name="test_oracle_row[mysql84-ANSI_QUOTES-0]">'
        "</testcase></testsuite>",
        encoding="utf-8",
    )
    try:
        result = check_live.main(
            [str(report), "--legs", "mysql84-default=1", "mysql84-ANSI_QUOTES=1", "--require", "test_oracle_row"]
        )
    except SystemExit as error:
        result = error.code
    assert result == 1
    assert "mysql84-ANSI_QUOTES" in capsys.readouterr().err
