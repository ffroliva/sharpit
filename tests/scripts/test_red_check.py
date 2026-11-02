"""scripts/dev/red_check.py: a worker-side check that each red test fails with an assertion under ``tests/``.

A throwaway project in a temp folder is checked with the real pytest, so the verdicts come from lane_gate.py's own
accept rule. The project has no ``pythonpath`` for ``src``: red_check puts the tree's ``src`` on ``PYTHONPATH``.
"""

import subprocess
from pathlib import Path

import pytest
from _load import load_script

red_check = load_script("scripts/dev/red_check.py")

RED = "RED (assertion under tests/)"

SRC = """\
def widget():
    return 1


def broken():
    raise TypeError("stub")


def guarded():
    assert False, "assert inside production code"
"""

HELPER = "def check(x):\n    assert x == 2, '{} assert'\n"

TESTS = """\
import pytest
from red_scripts_helper import check as scripts_check
from red_test_helper import check as helper_check

from mod import broken, guarded, widget


@pytest.fixture
def broken_setup():
    raise RuntimeError("setup broke")


@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError("teardown broke")


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


def test_setup_error(broken_setup):
    assert widget() == 2


def test_red_with_teardown_error(broken_teardown):
    assert widget() == 2


@pytest.mark.parametrize("expected", [1, 2])
def test_mixed_params(expected):
    assert widget() == expected


def test_did_not_raise():
    with pytest.raises(ValueError):
        widget()
"""

IDS = (
    "test_valid_red",
    "test_crash_stub",
    "test_passes",
    "test_assert_in_src",
    "test_assert_in_scripts",
    "test_assert_in_test_helper",
    "test_setup_error",
    "test_red_with_teardown_error",
    "test_mixed_params",
    "test_did_not_raise",
    "test_missing",
)


def _project(root: Path) -> Path:
    for folder in ("src", "tests", "scripts"):
        (root / folder).mkdir()
    (root / "src" / "mod.py").write_text(SRC, encoding="utf-8")
    (root / "tests" / "test_mod.py").write_text(TESTS, encoding="utf-8")
    (root / "tests" / "red_test_helper.py").write_text(HELPER.format("helper"), encoding="utf-8")
    (root / "scripts" / "red_scripts_helper.py").write_text(HELPER.format("scripts"), encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\npythonpath = scripts tests\n", encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _project(tmp_path_factory.mktemp("red-check"))


@pytest.fixture(scope="module")
def verdicts(project: Path) -> dict[str, str]:
    return red_check.check([f"tests/test_mod.py::{name}" for name in IDS], cwd=project)


def _of(verdicts: dict[str, str], name: str) -> str:
    return verdicts.get(f"tests/test_mod.py::{name}", "<no verdict>")


def test_valid_assertion_red_is_red(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_valid_red") == RED


def test_type_error_stub_is_crash(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_crash_stub").startswith("CRASH (TypeError)"), _of(verdicts, "test_crash_stub")


def test_passing_test_is_not_a_red(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_passes") == "PASS (not a red)"


def test_assert_inside_src_is_refused(verdicts: dict[str, str]) -> None:
    verdict = _of(verdicts, "test_assert_in_src")
    assert verdict.startswith("CRASH (AssertionError raised outside the test file, not under tests/"), verdict


def test_assert_inside_scripts_is_refused(verdicts: dict[str, str]) -> None:
    verdict = _of(verdicts, "test_assert_in_scripts")
    assert verdict.startswith("CRASH (AssertionError raised outside the test file, not under tests/"), verdict


def test_assert_in_a_helper_under_tests_is_red(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_assert_in_test_helper") == RED


def test_setup_error_is_a_fixture_error(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_setup_error") == "ERROR (fixture setup/teardown)"


def test_red_with_teardown_error_is_not_a_clean_red(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_red_with_teardown_error") == "ERROR (fixture setup/teardown)"


def test_one_passing_parametrisation_makes_the_id_not_a_red(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_mixed_params") == "PASS (not a red)"


def test_did_not_raise_from_the_test_file_is_red(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_did_not_raise") == RED


def test_unknown_id_is_a_collection_error_and_does_not_poison_the_batch(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_missing") == "ERROR (collection)"
    assert _of(verdicts, "test_valid_red") == RED


def test_file_path_expands_to_its_node_ids(project: Path) -> None:
    found = red_check.check(["tests/test_mod.py"], cwd=project)
    assert found.get("tests/test_mod.py::test_valid_red") == RED, found
    assert "tests/test_mod.py::test_mixed_params[2]" in found, found


@pytest.mark.parametrize("form", ["backslash", "dot", "absolute"])
def test_ids_are_normalised_to_rootdir_relative_posix(project: Path, form: str) -> None:
    given = {
        "backslash": "tests\\test_mod.py::test_valid_red",
        "dot": "./tests/test_mod.py::test_valid_red",
        "absolute": f"{project / 'tests' / 'test_mod.py'}::test_valid_red",
    }[form]
    assert red_check.check([given], cwd=project) == {"tests/test_mod.py::test_valid_red": RED}


def test_output_shows_pytest_tail_for_a_crash_and_is_ascii(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(project)
    assert red_check.main(["tests/test_mod.py::test_crash_stub"]) == 1
    out = capsys.readouterr().out
    assert "TypeError: stub" in out, out
    assert out.isascii(), out


def test_exit_code_zero_only_when_every_test_is_red(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project)
    assert red_check.main(["tests/test_mod.py::test_valid_red"]) == 0
    assert red_check.main(["tests/test_mod.py::test_valid_red", "tests/test_mod.py::test_passes"]) == 1


def test_warns_about_uncommitted_files_the_tests_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    for args in (["init", "-q"], ["add", "."], ["-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-c", f"core.hooksPath={tmp_path / 'no-hooks'}", *args], cwd=root, check=True)
    (root / "src" / "mod.py").write_text(SRC.replace("return 1", "return 2"), encoding="utf-8")
    monkeypatch.chdir(root)
    red_check.main(["tests/test_mod.py::test_valid_red"])
    err = capsys.readouterr().err
    assert "uncommitted" in err, err
    assert "src/mod.py" in err, err
