"""scripts/dev/red_check.py: a worker-side check that each red test fails with an assertion under ``tests/``.

A throwaway project in a temp folder is checked with the real pytest, so the verdicts come from lane_gate.py's own
accept rule. The project has no ``pythonpath`` for ``src``: red_check puts the tree's ``src`` on ``PYTHONPATH``.
"""

import contextlib
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from _load import load_script

red_check = load_script("scripts/dev/red_check.py")

RED = "RED (assertion under tests/)"
WAIT_FOR_BUILD = 120  # seconds a worker waits for another's verdicts before building its own
pytestmark = pytest.mark.timeout(300)  # the wait, then a build of 24 pytest subprocesses

SRC = """\
def widget():
    return 1


def broken():
    raise TypeError("stub")


def guarded():
    assert False, "assert inside production code"
"""

HELPER = "def check(x):\n    assert x == 2, '{} assert'\n"
RAISES_HELPER = """

def check_raises(fn):
    import pytest

    with pytest.raises(ValueError):
        fn()
"""

TESTS = """\
import pytest
from red_scripts_helper import check as scripts_check
from red_test_helper import check as helper_check, check_raises

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


def test_did_not_raise_in_helper():
    check_raises(widget)
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
    "test_did_not_raise_in_helper",
    "test_missing",
)


def _project(root: Path) -> Path:
    for folder in ("src", "tests", "scripts"):
        (root / folder).mkdir()
    (root / "src" / "mod.py").write_text(SRC, encoding="utf-8")
    (root / "tests" / "test_mod.py").write_text(TESTS, encoding="utf-8")
    (root / "tests" / "red_test_helper.py").write_text(HELPER.format("helper") + RAISES_HELPER, encoding="utf-8")
    (root / "scripts" / "red_scripts_helper.py").write_text(HELPER.format("scripts"), encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\npythonpath = scripts tests\n", encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _project(tmp_path_factory.mktemp("red-check"))


def _built_once(shared: Path, build: Callable[[], dict[str, str]]) -> dict[str, str]:
    """``build()``'s result: the first xdist worker to claim ``shared`` builds it, the others wait and read it."""
    claim, result = shared / "red-check-verdicts.claim", shared / "red-check-verdicts.json"
    try:
        claim.touch(exist_ok=False)
    except FileExistsError:
        deadline = time.monotonic() + WAIT_FOR_BUILD
        while claim.exists() and time.monotonic() < deadline:
            # Windows can refuse a read while a file is renamed into place or scanned
            with contextlib.suppress(FileNotFoundError, PermissionError):
                return json.loads(result.read_text(encoding="utf-8"))
            time.sleep(0.05)
        return build()  # the claimant failed or died, and the verdicts are the same built here
    try:
        value = build()
    except BaseException:
        claim.unlink()
        raise
    scratch = result.with_suffix(".tmp")
    try:
        scratch.write_text(json.dumps(value), encoding="utf-8")
        scratch.replace(result)  # atomic: a waiter never reads a half-written file
    except OSError:  # Windows can hold the file; these verdicts are good, and the waiters build their own
        claim.unlink(missing_ok=True)
    return value


@pytest.fixture(scope="module")
def verdicts(project: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    def build() -> dict[str, str]:
        return red_check.check([f"tests/test_mod.py::{name}" for name in IDS], cwd=project)

    if "PYTEST_XDIST_WORKER" not in os.environ:
        return build()
    return _built_once(tmp_path_factory.getbasetemp().parent, build)  # the run's folder, above each worker's own


def test_workers_share_one_verdicts_build(tmp_path: Path) -> None:
    """Each worker that drew a verdict test re-ran all 12 pytest subprocesses: 48 s + 21 s at -n 22 (T-suite-speed)."""
    builds: list[int] = []
    results: list[dict[str, str]] = []

    def build() -> dict[str, str]:
        builds.append(1)
        time.sleep(0.2)  # long enough that every worker arrives while the first is still building
        return {"id": "verdict"}

    workers = [threading.Thread(target=lambda: results.append(_built_once(tmp_path, build))) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert len(builds) == 1
    assert results == [{"id": "verdict"}] * 4


def test_a_waiter_retries_a_verdicts_file_windows_still_holds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """At -n 12 a waiter read the file as it was renamed into place: PermissionError on Windows (T-suite-speed)."""
    (tmp_path / "red-check-verdicts.claim").touch()
    (tmp_path / "red-check-verdicts.json").write_text('{"id": "verdict"}', encoding="utf-8")
    real = Path.read_text
    refusals = [PermissionError(13, "Permission denied")]

    def held_once(self: Path, *args: object, **kwargs: object) -> str:
        if refusals:
            raise refusals.pop()
        return real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", held_once)
    found: dict[str, str] = {}
    with contextlib.suppress(PermissionError):  # a waiter that lets it escape fails this assert, not with a crash
        found = _built_once(tmp_path, lambda: {"id": "rebuilt"})
    assert found == {"id": "verdict"}


def test_a_waiter_gives_up_before_its_test_times_out(request: pytest.FixtureRequest) -> None:
    """A timeout under the wait kills every waiting worker when the build is slow (code review, T-suite-speed)."""
    marker = request.node.get_closest_marker("timeout")
    limit = marker.args[0] if marker else float(request.config.getini("timeout"))
    assert limit > WAIT_FOR_BUILD


def test_a_verdicts_file_that_cannot_be_published_frees_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def held(self: Path, target: Path) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "replace", held)
    found: dict[str, str] = {}
    with contextlib.suppress(PermissionError):  # a builder that lets it escape fails this assert, not with a crash
        found = _built_once(tmp_path, lambda: {"id": "verdict"})
    assert found == {"id": "verdict"}
    assert not (tmp_path / "red-check-verdicts.claim").exists()


def test_a_failed_verdicts_build_leaves_the_next_worker_to_build(tmp_path: Path) -> None:
    def broken() -> dict[str, str]:
        raise RuntimeError("build broke")

    with pytest.raises(RuntimeError, match="build broke"):
        _built_once(tmp_path, broken)
    assert list(tmp_path.iterdir()) == []  # a claim left behind would keep every other worker waiting
    assert _built_once(tmp_path, lambda: {"id": "verdict"}) == {"id": "verdict"}


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


def test_did_not_raise_from_a_helper_under_tests_is_red(verdicts: dict[str, str]) -> None:
    assert _of(verdicts, "test_did_not_raise_in_helper") == RED


def _fake_pytest(junit_body: str):
    def fake(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        for arg in args:
            if arg.startswith("--junitxml="):
                Path(arg.removeprefix("--junitxml=")).write_text(junit_body, encoding="utf-8")
        return subprocess.CompletedProcess(args, 1, "", "")

    return fake


def test_assertion_without_a_traceback_frame_is_not_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = '<testcase classname="tests.test_x" name="test_y"><failure message="assert 0">no tail</failure></testcase>'
    monkeypatch.setattr(red_check, "_pytest", _fake_pytest(f"<testsuites><testsuite>{case}</testsuite></testsuites>"))
    verdict = red_check.check(["tests/test_x.py::test_y"], cwd=tmp_path)["tests/test_x.py::test_y"]
    assert verdict.startswith("CRASH (AssertionError with no traceback frame"), verdict


def test_collection_timeout_is_reported_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, red_check.TIMEOUT)

    monkeypatch.setattr(red_check, "_pytest", slow)
    try:
        found = red_check.check(["tests/test_x.py"], cwd=tmp_path)
    except subprocess.TimeoutExpired:
        found = {"tests/test_x.py": "<raised TimeoutExpired>"}
    assert found == {"tests/test_x.py": "ERROR (collection timeout)"}
