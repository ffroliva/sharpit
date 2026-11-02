"""Mechanical 0.4.0 lane merge gate (spec §10.3; council C2, F1c, F1f, R2, R7, round 4).

Run the release/0.4.0 copy from the integration worktree, never a lane's copy:

    uv run python scripts/dev/lane_gate.py <lane-id> [--worktree PATH] [--sha SHA] [--integration PATH]
                                           [--accept-unverified] [--no-rerun]

Exit 0 only when every check passes; each refusal is printed. Checks, in order:

1. the lane diff (merge-base with the integration HEAD .. lane head) touches no reviewer-owned or protected path;
2. the lane evidence (C2) at the lane head and the reviewer verdict + gate logs in the integration worktree;
3. red integrity and replay (R2, round 4) for every red test recorded in ``findings.md``/``handoff.md``;
4. the four gates re-run at the lane head, logs written to ``<integration>/<lane folder>/gate/<name>.log``.

Steps 3 and 4 are expensive and only run when the earlier steps found nothing.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

GateRunner = Callable[[str, Sequence[str], Path], tuple[int, str]]
PytestRunner = Callable[[Path, Sequence[str], Path], None]

WORKTREE_ROOT = Path(r"C:\development\github\sharpit-wt")
LANES = ".superpowers/sdd/0.4.0/lanes"
EVIDENCE = ("handoff.md", "findings.md", "field-map.md", "checklist.md")
SHA_LOGS = ("lowest-direct", "no-sqlalchemy")  # run by the coordinator in a throwaway copy, pinned to the head SHA
GATES: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("ruff-check", ("uv", "run", "ruff", "check"), 300),
    ("ruff-format", ("uv", "run", "ruff", "format", "--check"), 300),
    ("pyright", ("uv", "run", "pyright"), 900),
    ("pytest", ("uv", "run", "pytest", "-q", "-n", "4"), 1800),
)
PROTECTED = (
    "scripts/dev/lane_gate.py",
    "sonar-baseline.txt",
    "tests/engine/test_import_boundary.py",
    "uv.lock",
)
F_MAY_CHANGE = {"scripts/dev/lane_gate.py", "tests/engine/test_import_boundary.py", "uv.lock", "pyproject.toml"}
BASELINE = "tests/complexity_baseline.json"
LEASED_LANE = "A-postgresql"
LEASED_TESTS = ("test_read_only_wrapper_rejects_write", "test_autocommit_engine_is_unavailable")
FIXTURE_PREFIX = "test-fixture"
REVIEWER_OWNED = re.compile(rf"^{re.escape(LANES)}/[^/]+/(review\.md|live-verify\.md|gate/.*)$")
BUDGET_LINE = re.compile(r"^(BUDGET\w*)\s*(?::[^=]*)?=\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Options:
    lane: str
    worktree: Path
    sha: str
    integration: Path
    accept_unverified: bool = False
    no_rerun: bool = False


@dataclass
class Result:
    refusals: list[str] = field(default_factory=list[str])
    unverified: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class Red:
    test: str
    sha: str


# --- git helpers ------------------------------------------------------------------------------------------------------


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8")


def _show(repo: Path, sha: str, path: str) -> str | None:
    done = _git(repo, "show", f"{sha}:{path}", check=False)
    return done.stdout if done.returncode == 0 else None


def _resolve(repo: Path, ref: str) -> str | None:
    done = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    return done.stdout.strip() or None


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    return _git(repo, "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


# --- markdown tables --------------------------------------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _code(cell: str) -> str:
    """The first `code span` in a cell (a cell may add notes after it), else the cell's text."""
    found = re.search(r"`([^`]+)`", cell)
    return found.group(1).strip() if found else cell.strip()


def _tables(text: str) -> Iterator[tuple[list[str], list[list[str]]]]:
    """Yield (lower-cased header, rows) for every markdown table in ``text``."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        is_head = lines[i].lstrip().startswith("|") and i + 1 < len(lines)
        if is_head and re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", lines[i + 1]) and "-" in lines[i + 1]:
            header = [cell.lower() for cell in _cells(lines[i])]
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            yield header, rows
        else:
            i += 1


def _column(header: list[str], *names: str) -> int | None:
    return next((header.index(name) for name in names if name in header), None)


def _cell(row: list[str], col: int | None) -> str:
    return _code(row[col]) if col is not None and col < len(row) else ""


def red_tests(texts: Mapping[str, str]) -> tuple[list[Red], list[str]]:
    """Every (test, red SHA) pair from tables with a ``Test id``/``Test`` column and a column whose header contains
    ``Red SHA``, de-duplicated, plus the problems: a row naming a test with a blank Red SHA (unless parked), and a
    findings table (one with a ``Disposition`` column) without a Red SHA column."""
    reds: dict[Red, None] = {}
    problems: list[str] = []
    for label, text in texts.items():
        for header, rows in _tables(text):
            test_col = _column(header, "test id", "test")
            sha_col = next((i for i, name in enumerate(header) if "red sha" in name), None)
            disp_col = _column(header, "disposition")
            if sha_col is None and disp_col is not None:
                problems.append(f"{label}: a findings table has no Red SHA column")
            if test_col is None or sha_col is None:
                continue
            for row in rows:
                test, sha = _cell(row, test_col), _cell(row, sha_col)
                if not test or (not sha and _cell(row, disp_col).lower().startswith("parked")):
                    continue
                if sha:
                    reds[Red(test, sha)] = None
                else:
                    problems.append(f"{label}: red table row for {test} has no Red SHA")
    return list(reds), problems


# --- checks -----------------------------------------------------------------------------------------------------------


def _diff_paths(repo: Path, base: str, head: str) -> list[str]:
    return _git(repo, "diff", "--name-only", "--no-renames", base, head).stdout.splitlines()


def _dependency_lists(text: str | None) -> object:
    data = tomllib.loads(text or "")
    project = data.get("project", {})
    return (
        project.get("dependencies"),
        project.get("optional-dependencies"),
        data.get("dependency-groups"),
        data.get("build-system", {}).get("requires"),
    )


def _baseline_refusals(lane: str, before: str | None, after: str | None) -> list[str]:
    old: dict[str, int] = json.loads(before or "{}")
    new: dict[str, int] = json.loads(after or "{}")
    if lane == "F":  # F1c: F may re-key moved code; the per-finding total must not rise
        rose = sum(new.values()) > sum(old.values())
        return [f"complexity baseline total rose: {sum(old.values())} -> {sum(new.values())}"] if rose else []
    problems = [f"complexity baseline entry added: {key}" for key in new if key not in old]
    problems += [f"complexity baseline raised: {key}" for key in new if key in old and new[key] > old[key]]
    return problems


def diff_refusals(opts: Options, base: str) -> list[str]:
    repo, head, is_f = opts.worktree, opts.sha, opts.lane == "F"
    problems: list[str] = []
    for path in _diff_paths(repo, base, head):
        before, after = _show(repo, base, path), _show(repo, head, path)
        if REVIEWER_OWNED.match(path):
            problems.append(f"reviewer-owned path changed: {path}")
        elif path in PROTECTED and not (is_f and path in F_MAY_CHANGE):
            problems.append(f"protected path changed: {path}")
        elif path == BASELINE:
            problems += _baseline_refusals(opts.lane, before, after)
        elif path == "pyproject.toml" and not is_f and _dependency_lists(before) != _dependency_lists(after):
            problems.append("dependency list changed: pyproject.toml")
        elif path.endswith(".py") and BUDGET_LINE.findall(before or "") != BUDGET_LINE.findall(after or ""):
            problems.append(f"overhead budget constant changed: {path}")
    return problems


def _evidence_path_exists(opts: Options, token: str) -> bool:
    rel = re.split(r"::|:\d", token, maxsplit=1)[0].strip()
    if not rel or " " in rel:
        return False
    in_lane = _git(opts.worktree, "cat-file", "-e", f"{opts.sha}:{rel}", check=False).returncode == 0
    return in_lane or (opts.integration / rel).exists()


def _checklist_refusals(opts: Options, text: str) -> list[str]:
    problems: list[str] = []
    for n in range(1, 11):
        line = next((ln for ln in text.splitlines() if re.match(rf"^\s*\|?\s*{n}\s*(\||\.|\)|\s)", ln)), None)
        if line is None:
            problems.append(f"checklist.md: item {n} missing")
        elif "N/A" not in line and not any(_evidence_path_exists(opts, t) for t in re.findall(r"`([^`]+)`", line)):
            problems.append(f"checklist.md: item {n} has no existing evidence path")
    return problems


def _findings_refusals(text: str) -> list[str]:
    problems: list[str] = []
    for header, rows in _tables(text):
        disp_col, test_col = _column(header, "disposition"), _column(header, "test id", "test")
        if disp_col is None:
            continue
        for row in rows:
            disposition = row[disp_col] if len(row) > disp_col else ""
            test = row[test_col] if test_col is not None and len(row) > test_col else ""
            word = disposition.lower()
            fixed = word.startswith("fixed") and bool(test)
            parked = word.startswith("parked") and bool(disposition[6:].strip(" :-—–()"))
            if not (fixed or parked):
                problems.append(f"findings.md: unresolved finding: {' | '.join(row)}")
    return problems


def _review_refusals(opts: Options, handoff: str) -> list[str]:
    path = opts.integration / LANES / opts.lane / "review.md"
    if not path.is_file():
        return [f"missing review: {path}"]
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    problems: list[str] = []
    if not lines or lines[-1] != "VERDICT: APPROVE":
        problems.append("review.md: last line is not VERDICT: APPROVE")
    if opts.sha not in text:
        problems.append(f"review.md: does not name the head SHA {opts.sha}")
    reviewer = re.search(r"^Reviewer:\s*(\S+)", text, re.MULTILINE)
    implementer = re.search(r"^Implementer:\s*(\S+)", handoff, re.MULTILINE)
    if reviewer is None:
        problems.append("review.md: no reviewer id (a 'Reviewer: <id>' line)")
    elif implementer is not None and reviewer.group(1) == implementer.group(1):
        problems.append(f"review.md: reviewer is the implementer ({reviewer.group(1)})")
    return problems


def evidence_refusals(opts: Options, base: str) -> tuple[list[str], dict[str, str]]:
    folder = f"{LANES}/{opts.lane}"
    texts = {name: _show(opts.worktree, opts.sha, f"{folder}/{name}") for name in EVIDENCE}
    problems = [f"missing evidence: {name} (at {folder}/ in the lane head)" for name, t in texts.items() if t is None]
    found = {name: text for name, text in texts.items() if text is not None}
    if "handoff.md" in found and f"{folder}/handoff.md" not in _diff_paths(opts.worktree, base, opts.sha):
        problems.append("handoff.md is not current: the lane diff never updated it")
    problems += _checklist_refusals(opts, found.get("checklist.md", "")) if "checklist.md" in found else []
    problems += _findings_refusals(found.get("findings.md", ""))
    problems += _review_refusals(opts, found.get("handoff.md", ""))
    for name in SHA_LOGS:
        log = opts.integration / folder / "gate" / f"{name}.log"
        first = log.read_text(encoding="utf-8").splitlines()[:1] if log.is_file() else []
        if not first or opts.sha not in first[0]:
            problems.append(f"gate/{name}.log does not name head {opts.sha} on line 1 (missing or stale)")
    return problems, found


def leased_pg_problem(opts: Options) -> str | None:
    log = opts.integration / LANES / opts.lane / "gate" / "leased-pg.log"
    if not log.is_file():
        return f"leased-pg: {log} missing"
    lines = log.read_text(encoding="utf-8").splitlines()
    if not lines or opts.sha not in lines[0]:
        return "leased-pg: gate/leased-pg.log line 1 does not name the head SHA"
    for name in LEASED_TESTS:
        if not any(name in ln and "PASSED" in ln for ln in lines[1:]):
            return f"leased-pg: {name} not PASSED (missing or skipped)"
    return None


# --- red integrity and replay -----------------------------------------------------------------------------------------


def _function_source(source: str, nodeid: str) -> str | None:
    *classes, name = nodeid.split("[", 1)[0].split("::")[1:]
    try:
        body: list[ast.stmt] = ast.parse(source).body
    except SyntaxError:
        return None
    for cls in classes:
        node = next((n for n in body if isinstance(n, ast.ClassDef) and n.name == cls), None)
        if node is None:
            return None
        body = node.body
    func = next((n for n in body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name), None)
    if func is None:
        return None
    start = min([func.lineno, *(d.lineno for d in func.decorator_list)])
    return "\n".join(source.splitlines()[start - 1 : func.end_lineno])


def _module_shape(source: str) -> tuple[str, dict[str, str]] | None:
    """(the module without its top-level test functions, blank lines dropped; {test function name: source})."""
    try:
        body = ast.parse(source).body
    except SyntaxError:
        return None
    lines = source.splitlines()
    tests: dict[str, str] = {}
    skip: set[int] = set()
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            tests[node.name] = "\n".join(lines[start - 1 : node.end_lineno])
            skip.update(range(start - 1, node.end_lineno or start))
    rest = "\n".join(line for i, line in enumerate(lines) if i not in skip and line.strip())
    return rest, tests


def _red_file_problems(opts: Options, sha: str, path: str) -> list[str]:
    """Round 4, widened: after the red commit the red test's file may only gain new test functions, and no
    conftest.py on its path may change (constants, parametrize lists, fixtures and helpers can weaken a red too)."""
    problems: list[str] = []
    before = _module_shape(_show(opts.worktree, sha, path) or "")
    after = _module_shape(_show(opts.worktree, opts.sha, path) or "")
    changed = before is None or after is None or before[0] != after[0]
    changed = changed or any(after[1].get(name) != src for name, src in before[1].items())  # type: ignore[index]
    if changed:
        problems.append("test file changed outside added test functions after the red commit")
    parts = path.split("/")[:-1]
    conftests = ["/".join([*parts[:i], "conftest.py"]) for i in range(len(parts) + 1)]
    moved = _git(opts.worktree, "diff", "--name-only", sha, opts.sha, "--", *conftests).stdout.split()
    problems += [f"{conftest} changed after red commit" for conftest in moved]
    return problems


@dataclass
class _Integrity:
    replayable: list[Red] = field(default_factory=list[Red])
    problems: list[str] = field(default_factory=list[str])
    unverified: list[str] = field(default_factory=list[str])


def red_integrity(opts: Options, base: str, reds: Sequence[Red]) -> _Integrity:
    out = _Integrity()
    if not reds:
        out.problems.append("no red tests recorded in findings.md/handoff.md (table: | Test id | Red SHA | ... |)")
    for red in reds:
        tag = f"red {red.test}"
        if ".py::" not in red.test:
            out.unverified.append(f"{tag}: not a pytest test; replay it by hand at {red.sha}")
            continue
        sha = _resolve(opts.worktree, red.sha)
        if sha is None:
            out.problems.append(f"{tag}: red SHA {red.sha} is unknown")
            continue
        if not _is_ancestor(opts.worktree, sha, opts.sha):
            out.problems.append(f"{tag}: red SHA {red.sha} is not an ancestor of head")
            continue
        if _is_ancestor(opts.worktree, sha, base):
            out.problems.append(f"{tag}: red SHA {red.sha} is not a lane commit (already in the integration branch)")
            continue
        path = red.test.split("::", 1)[0]
        at_red = _function_source(_show(opts.worktree, sha, path) or "", red.test)
        at_head = _function_source(_show(opts.worktree, opts.sha, path) or "", red.test)
        if at_red is None:
            out.problems.append(f"{tag}: test missing at red SHA {red.sha}")
        elif at_head is None:
            out.problems.append(f"{tag}: test missing at head")
        elif at_red != at_head:
            out.problems.append(f"{tag}: test body changed after red commit {red.sha}")
        elif _function_source(_show(opts.worktree, base, path) or "", red.test) == at_red:
            # council r2: the red test must be in the lane diff; an old test plus a broken src is a fake red
            out.problems.append(f"{tag}: test unchanged from the integration branch (a red must add or change it)")
        elif file_problems := _red_file_problems(opts, sha, path):
            out.problems += [f"{tag}: {problem} {red.sha}" for problem in file_problems]
        else:
            out.replayable.append(Red(red.test, sha))
    return out


def _exception_name(failure: ET.Element) -> tuple[str, str]:
    """(class name, file of the last frame) of the failing exception.

    The ``--tb=long`` last line is ``<file>:<line>: <type>``. Without it (never seen from real pytest) fall back to the
    ``type`` attribute, then the message (a rewritten ``assert`` reports ``assert 1 == 2`` with no exception name);
    the file is then unknown ("").
    """
    tail = (failure.text or "").strip().splitlines()[-1:]
    found = re.search(r"^(.*):\d+: ([\w.]+)$", tail[0]) if tail else None
    if found is not None:
        return found.group(2).rsplit(".", 1)[-1], found.group(1).strip()
    message = failure.get("message", "")
    if failure.get("type"):
        return failure.get("type", "").rsplit(".", 1)[-1], ""
    if message.startswith("assert "):
        return "AssertionError", ""
    named = re.match(r"([\w.]+):", message)
    return (named.group(1).rsplit(".", 1)[-1] if named else ""), ""


def _is_test_file(frame_file: str, test_path: str) -> bool:
    frame = frame_file.replace("\\", "/")
    return frame == test_path or frame.endswith("/" + test_path)


Outcome = tuple[str, str]  # (passed|failure|error|skipped|not collected, a failure's exception class name)


def _outcomes(junit: Path, nodeids: Sequence[str]) -> dict[str, list[Outcome]]:
    """nodeid -> the outcome of every matching case: a bare function id matches all its parametrisations."""
    cases = ET.parse(junit).getroot().iter("testcase") if junit.is_file() else iter(())
    by_key: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for case in cases:
        outcome, message, frame = "passed", "", ""
        for kind in ("failure", "error", "skipped"):
            child = case.find(kind)
            if child is not None:
                outcome = kind
                message, frame = _exception_name(child) if kind == "failure" else (child.get("message", ""), "")
                break
        name = case.get("name", "")
        for key in {name, name.split("[", 1)[0]}:
            by_key.setdefault((case.get("classname", ""), key), []).append((outcome, message, frame))
    result: dict[str, list[Outcome]] = {}
    for nodeid in nodeids:
        path, *rest = nodeid.split("::")
        classname = ".".join([path.removesuffix(".py").replace("/", "."), *rest[:-1]])
        result[nodeid] = [
            # an AssertionError from src (``def f(): assert False``) is a disguised stub, not the test's assertion
            (o, f"AssertionError raised outside the test file ({f})")
            if o == "failure" and m == "AssertionError" and f and not _is_test_file(f, path)
            else (o, m)
            for o, m, f in by_key.get((classname, rest[-1]), [("not collected", "", "")])
        ]
    return result


def _replay(opts: Options, sha: str, nodeids: Sequence[str], run_pytest: PytestRunner) -> dict[str, list[Outcome]]:
    scratch = Path(tempfile.mkdtemp(prefix="lane-gate-"))
    tree = scratch / "tree"
    _git(opts.worktree, "worktree", "add", "--detach", "--quiet", str(tree), sha)
    try:
        junit = scratch / "junit.xml"
        run_pytest(tree, nodeids, junit)
        return _outcomes(junit, nodeids)
    finally:
        _git(opts.worktree, "worktree", "remove", "--force", str(tree), check=False)
        shutil.rmtree(scratch, ignore_errors=True)


def replay_refusals(opts: Options, reds: Sequence[Red], run_pytest: PytestRunner) -> list[str]:
    problems: list[str] = []
    for sha in dict.fromkeys(red.sha for red in reds):
        ids = [red.test for red in reds if red.sha == sha]
        for nodeid, outcomes in _replay(opts, sha, ids, run_pytest).items():
            bad = [(o, m) for o, m in outcomes if not (o == "failure" and m == "AssertionError")]
            if bad:
                outcome, message = bad[0]
                detail = f"{message or 'unnamed exception'} failure" if outcome == "failure" else outcome
                problems.append(f"red {nodeid}: {detail} at red SHA {sha} (needs an AssertionError failure)")
    head_ids = list(dict.fromkeys(red.test for red in reds))
    if head_ids:
        for nodeid, outcomes in _replay(opts, opts.sha, head_ids, run_pytest).items():
            failing = [o for o, _m in outcomes if o != "passed"]
            if failing:
                problems.append(f"red {nodeid}: does not pass at head ({failing[0]})")
    return problems


# --- the four gates ---------------------------------------------------------------------------------------------------


def gate_refusals(opts: Options, run_gate: GateRunner) -> list[str]:
    logs = opts.integration / LANES / opts.lane / "gate"
    logs.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    for name, command, _timeout in GATES:
        code, output = run_gate(name, command, opts.worktree)
        (logs / f"{name}.log").write_text(f"{opts.sha}\n$ {' '.join(command)}\nexit {code}\n{output}", encoding="utf-8")
        if code != 0:
            problems.append(f"gate {name} failed (exit {code}); see {logs / f'{name}.log'}")
    return problems


def _env(**extra: str) -> dict[str, str]:
    # uv's default hardlinks hit Windows' per-file link limit on a busy cache (os error 1142); copying always works
    return {"UV_LINK_MODE": "copy", **os.environ, **extra}


def run_gate_command(name: str, command: Sequence[str], cwd: Path) -> tuple[int, str]:
    timeout = next(t for n, _c, t in GATES if n == name)
    try:
        done = subprocess.run(
            list(command), cwd=cwd, env=_env(), capture_output=True, text=True, encoding="utf-8", timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        return 124, f"timed out after {timeout}s\n{exc.stdout or ''}"
    return done.returncode, done.stdout + done.stderr


def run_pytest_in(integration: Path) -> PytestRunner:
    """Replay with the integration worktree's environment; the replayed tree's ``src`` shadows the editable install."""

    def run(tree: Path, nodeids: Sequence[str], junit: Path) -> None:
        env = _env(PYTHONPATH=os.pathsep.join([str(tree / "src"), str(tree)]))
        command = ["uv", "run", "--project", str(integration), "--frozen", "python", "-m", "pytest", "-q"]
        command += ["-p", "no:cacheprovider", "-p", "no:randomly", "--tb=long", f"--junitxml={junit}", *nodeids]
        subprocess.run(command, cwd=tree, env=env, capture_output=True, timeout=900, check=False)

    return run


# --- entry points -----------------------------------------------------------------------------------------------------


def evaluate(
    opts: Options,
    *,
    run_gate: GateRunner,
    run_pytest: PytestRunner,
    prepare_env: Callable[[Path], tuple[int, str]] = lambda tree: (0, ""),
) -> Result:
    result = Result()
    if opts.no_rerun and not opts.lane.startswith(FIXTURE_PREFIX):
        result.refusals.append(f"--no-rerun is only for test fixture lanes ({FIXTURE_PREFIX}-*), not {opts.lane}")
    head = _git(opts.worktree, "rev-parse", "HEAD").stdout.strip()
    if head != opts.sha:
        result.refusals.append(f"{opts.sha} is not the worktree HEAD ({head}); the gates run in the lane worktree")
    if _git(opts.worktree, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        result.refusals.append("lane worktree has uncommitted changes")
    integration_head = _git(opts.integration, "rev-parse", "HEAD").stdout.strip()
    base = _git(opts.worktree, "merge-base", integration_head, opts.sha).stdout.strip()

    result.refusals += diff_refusals(opts, base)
    evidence, texts = evidence_refusals(opts, base)
    result.refusals += evidence
    reds, table_problems = red_tests({name: texts.get(name, "") for name in ("findings.md", "handoff.md")})
    integrity = red_integrity(opts, base, reds)
    result.refusals += table_problems + integrity.problems
    unverified = list(integrity.unverified)
    if opts.lane == LEASED_LANE and (problem := leased_pg_problem(opts)):
        unverified.append(problem)
    if opts.accept_unverified:
        result.unverified = unverified
    else:
        result.refusals += [f"{line} (pass --accept-unverified to record it as unverified)" for line in unverified]
    if result.refusals:
        result.refusals.append("red replay and gate re-run skipped: fix the refusals above first")
        return result
    result.refusals += replay_refusals(opts, integrity.replayable, run_pytest)
    if not opts.no_rerun:
        result.refusals += gate_refusals(opts, run_gate)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("lane")
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--sha")
    parser.add_argument("--integration", type=Path, default=Path.cwd())
    parser.add_argument("--accept-unverified", action="store_true")
    parser.add_argument("--no-rerun", action="store_true", help="test fixture lanes only")
    args = parser.parse_args(argv)
    worktree: Path = args.worktree or WORKTREE_ROOT / f"0.4.0-{args.lane}"
    sha: str = args.sha or _git(worktree, "rev-parse", "HEAD").stdout.strip()
    opts = Options(args.lane, worktree, sha, args.integration, args.accept_unverified, args.no_rerun)
    result = evaluate(opts, run_gate=run_gate_command, run_pytest=run_pytest_in(opts.integration))
    for line in result.unverified:
        print(f"unverified: {line}")
    for line in result.refusals:
        print(f"REFUSED: {line}")
    print(f"lane {opts.lane} @ {sha}: {'REFUSED' if result.refusals else 'ACCEPTED'}")
    return 1 if result.refusals else 0


if __name__ == "__main__":
    sys.exit(main())
