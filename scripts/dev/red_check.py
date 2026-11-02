"""Check that each red test fails for the right reason before a ``test:`` commit.

    uv run python scripts/dev/red_check.py <node id | test file> [...]

Each node id runs in its own pytest call, in the current tree, with the tree's ``src`` first on ``PYTHONPATH`` (as the
merge gate's replay). A test file (or any id without ``::``) is expanded to its node ids first. One verdict per test:

- ``RED (assertion under tests/)``: a valid red;
- ``CRASH (<detail>) - not a red``: a TypeError/AttributeError/pytest.fail stub, or an ``assert`` outside ``tests/``
  (``src``, ``scripts``): use a wrong-value stub (return the wrong state) so the test's own assertion fails;
- ``PASS (not a red)``: the test passed or was skipped;
- ``ERROR (fixture setup/teardown)``: a fixture errored (a failing call plus a teardown error is not a clean red);
- ``ERROR (collection)``: the id was not collected; ``ERROR (collection timeout)``: collecting it ran out of time.

Exit 0 only when every test is a valid red. The accept rule is lane_gate.py's own (``is_red``, ``red_verdicts``).
What only the gate checks: the red SHA is committed and an ancestor of the head, the test is unchanged from the red
SHA to the head, it is inside the lane diff, the names it references are frozen, and it passes at the head.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

TIMEOUT = 900  # seconds, as the gate's replay
TAIL = 15  # pytest output lines shown under a verdict that is not RED
RED = "RED (assertion under tests/)"


def _load_lane_gate() -> ModuleType:
    """lane_gate.py by file path (scripts/ is not a package), so its accept rule is the one this check applies."""
    spec = importlib.util.spec_from_file_location("_red_check_lane_gate", Path(__file__).with_name("lane_gate.py"))
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


lane_gate = _load_lane_gate()


def _root(cwd: Path) -> Path:
    done = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, check=False)
    return Path(done.stdout.strip()).resolve() if done.returncode == 0 else cwd.resolve()


def _env(root: Path) -> dict[str, str]:
    """The tree's own ``src`` first, so a stale editable install elsewhere cannot answer for it."""
    paths = [str(root / "src"), str(root), os.environ.get("PYTHONPATH", "")]
    return {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in paths if p)}


def _pytest(root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", *args]
    return subprocess.run(
        command,
        cwd=root,
        env=_env(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT,
        check=False,
    )


def normalise(arg: str, cwd: Path, root: Path) -> str:
    """A node id relative to ``root`` in POSIX form: backslashes, ``./`` and absolute paths are accepted."""
    path, sep, rest = arg.partition("::")
    path = path.replace("\\", "/")  # before resolving: on POSIX a backslash is part of one file name
    with contextlib.suppress(ValueError):  # outside the tree: leave it for pytest to report
        path = (cwd / path).resolve().relative_to(root).as_posix()
    return path + sep + rest


def _expand(root: Path, arg: str) -> tuple[list[str], str]:
    """Node ids collected from a file or directory argument, and pytest's output for when there are none."""
    done = _pytest(root, ["--collect-only", arg])  # _pytest already passes -q: one -q lists node ids
    ids = [line.strip() for line in done.stdout.splitlines() if "::" in line and not line.startswith("ERROR")]
    return ids, done.stdout + done.stderr


def _label(outcome: tuple[str, str]) -> str:
    kind, detail = outcome
    if lane_gate.is_red(outcome):
        return RED
    if kind == "failure":
        return f"CRASH ({detail or 'unnamed exception'}) - not a red: use a wrong-value stub"
    if kind in ("passed", "skipped"):
        return "PASS (not a red)"
    if kind == "error":
        return "ERROR (fixture setup/teardown)"
    return "ERROR (collection)"


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-TAIL:]).encode("ascii", "replace").decode("ascii")


def _run_one(root: Path, nodeid: str) -> tuple[str, str]:
    """(verdict, pytest's tail output when the verdict is not RED); a parametrised id is red only if every case is."""
    with tempfile.TemporaryDirectory(prefix="red-check-") as scratch:
        junit = Path(scratch) / "junit.xml"
        try:
            done = _pytest(root, ["--tb=long", f"--junitxml={junit}", nodeid])
        except subprocess.TimeoutExpired:
            return f"ERROR (timed out after {TIMEOUT}s)", ""
        outcomes = lane_gate.red_verdicts(junit, [nodeid], root)[nodeid]
    verdict = next((v for v in map(_label, outcomes) if v != RED), RED)
    output = done.stdout if done.stdout.strip() else done.stderr  # stderr is mostly plugin warnings
    return verdict, "" if verdict == RED else _tail(output)


def run(args: Sequence[str], cwd: Path | None = None) -> dict[str, tuple[str, str]]:
    """node id -> (verdict, tail). One pytest call per id, so one bad id cannot poison the rest."""
    here = (cwd or Path.cwd()).resolve()
    root = _root(here)
    results: dict[str, tuple[str, str]] = {}
    for arg in args:
        nodeid = normalise(arg, here, root)
        if "::" in nodeid:
            results[nodeid] = _run_one(root, nodeid)
            continue
        try:
            ids, output = _expand(root, nodeid)
        except subprocess.TimeoutExpired:
            results[nodeid] = ("ERROR (collection timeout)", f"pytest --collect-only ran over {TIMEOUT}s")
            continue
        if not ids:
            results[nodeid] = ("ERROR (collection)", _tail(output))
        for found in ids:
            results[found] = _run_one(root, found)
    return results


def check(args: Sequence[str], cwd: Path | None = None) -> dict[str, str]:
    """node id -> verdict."""
    return {nodeid: verdict for nodeid, (verdict, _tail) in run(args, cwd).items()}


def uncommitted(root: Path) -> list[str]:
    """Uncommitted Python files the tests may import.

    shortcut: any changed .py under src/, tests/ or a conftest counts, not only the files these tests import;
    narrow it if the warning gets noisy.
    """
    done = subprocess.run(
        ["git", "status", "--porcelain", "--", "src", "tests", "conftest.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    files = [line[3:].strip().split(" -> ")[-1] for line in done.stdout.splitlines()] if done.returncode == 0 else []
    return [f for f in files if f.endswith(".py")]


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 2
    changed = uncommitted(_root(Path.cwd()))
    if changed:
        print(f"warning: uncommitted changes the tests may import: {', '.join(changed)}", file=sys.stderr)
        print("warning: the verdict is for the working tree, not a commit; commit, then re-run", file=sys.stderr)
    results = run(args)
    for nodeid, (verdict, tail) in results.items():
        print(f"{verdict}  {nodeid}")
        if tail:
            print("    " + tail.replace("\n", "\n    "))
    return 0 if results and all(v == RED for v, _t in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
