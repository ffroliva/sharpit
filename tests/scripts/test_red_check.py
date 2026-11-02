"""scripts/dev/red_check.py: a worker-side check that each red test fails with an assertion in the test file.

Each test writes a throwaway project in ``tmp_path`` and runs the real pytest on it, so the classification is the one
lane_gate.py applies at merge time.
"""

from pathlib import Path

from _load import load_script

red_check = load_script("scripts/dev/red_check.py")

SRC = """\
def widget():
    return 1


def broken():
    raise TypeError("stub")


def guarded():
    assert False, "assert inside production code"
"""

TESTS = """\
from red_test_helper import check as helper_check
from mod import broken, guarded, widget
from red_scripts_helper import check as scripts_check


def test_valid_red():
    assert widget() == 2, "widget must return 2"


def test_crash_stub():
    assert broken() == 2


def test_passes():
    assert widget() == 1


def test_assert_in_src():
    assert guarded() == 2


def test_assert_in_scripts():
    scripts_check(widget())


def test_assert_in_test_helper():
    helper_check(widget())
"""

HELPER = "def check(x):\n    assert x == 2, '{} assert'\n"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(SRC, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mod.py").write_text(TESTS, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = src scripts tests\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "red_scripts_helper.py").write_text(HELPER.format("scripts"), encoding="utf-8")
    (tmp_path / "tests" / "red_test_helper.py").write_text(HELPER.format("helper"), encoding="utf-8")
    return tmp_path


def _verdict(tmp_path: Path, name: str) -> str:
    nodeid = f"tests/test_mod.py::{name}"
    return red_check.check([nodeid], cwd=_project(tmp_path))[nodeid]


def test_valid_assertion_red_is_red(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "test_valid_red") == "RED (assertion in test file)"


def test_type_error_stub_is_crash(tmp_path: Path) -> None:
    verdict = _verdict(tmp_path, "test_crash_stub")
    assert verdict.startswith("CRASH (TypeError"), verdict


def test_passing_test_is_not_a_red(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "test_passes") == "PASS (not a red)"


def test_assert_inside_src_is_refused(tmp_path: Path) -> None:
    verdict = _verdict(tmp_path, "test_assert_in_src")
    assert verdict.startswith("CRASH (AssertionError raised outside the test file, not under tests/"), verdict


def test_unknown_node_is_collection_error(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "test_missing") == "ERROR (collection)"


def test_exit_code_zero_only_when_every_test_is_red(tmp_path: Path, monkeypatch) -> None:
    project = _project(tmp_path)
    monkeypatch.chdir(project)
    assert red_check.main(["tests/test_mod.py::test_valid_red"]) == 0
    assert red_check.main(["tests/test_mod.py::test_valid_red", "tests/test_mod.py::test_passes"]) == 1


def test_assert_inside_scripts_is_refused(tmp_path: Path) -> None:
    verdict = _verdict(tmp_path, "test_assert_in_scripts")
    assert verdict.startswith("CRASH (AssertionError raised outside the test file, not under tests/"), verdict


def test_assert_in_a_helper_under_tests_is_red(tmp_path: Path) -> None:
    assert _verdict(tmp_path, "test_assert_in_test_helper") == "RED (assertion in test file)"
