"""Mechanical lane merge gate (0.4.0 spec §10.3; council C2, F1c, F1f, R2, R7, round 4; 0.5.0 spec §4.0).

Run the release branch's copy from the integration worktree, never a lane's copy:

    uv run python scripts/dev/lane_gate.py <lane-id> [--release X] [--worktree PATH] [--sha SHA] [--integration PATH]
                                           [--accept-unverified] [--no-rerun]

The release (evidence under ``.superpowers/sdd/<release>/lanes/<lane-id>/``) is ``--release``, else the integration
branch ``release/<x>``, else the only release folder in the integration worktree; otherwise the gate refuses.

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
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

GateRunner = Callable[[str, Sequence[str], Path], tuple[int, str]]
PytestRunner = Callable[[Path, Sequence[str], Path], None]
EnvPreparer = Callable[[Path], tuple[int, str]]

WORKTREE_ROOT = Path(r"C:\development\github\sharpit-wt")
SDD = ".superpowers/sdd"  # <SDD>/<release>/lanes/<lane id>/
EVIDENCE = ("handoff.md", "findings.md", "field-map.md", "checklist.md")
SHA_LOGS = ("lowest-direct", "no-sqlalchemy")  # run by the coordinator in a throwaway copy, pinned to the head SHA
GATES: tuple[tuple[str, tuple[str, ...], int], ...] = (  # run in a fresh tree after SYNC built its env
    ("ruff-check", ("uv", "run", "--no-sync", "ruff", "check"), 300),
    ("ruff-format", ("uv", "run", "--no-sync", "ruff", "format", "--check"), 300),
    ("pyright", ("uv", "run", "--no-sync", "pyright"), 900),
    ("pytest", ("uv", "run", "--no-sync", "pytest", "-q", "-n", "4"), 1800),
)
SYNC = ("uv", "sync", "--frozen", "--extra", "test")
PROTECTED = (
    "scripts/dev/lane_gate.py",
    "sonar-baseline.txt",
    "tests/engine/test_import_boundary.py",
    "uv.lock",
    "tests/overhead.py",
    "tests/test_code_shape.py",
    "tests/conftest.py",
    "conftest.py",
)
GATE_CONFIG = ("ruff", "pyright", "pytest", "uv")  # [tool.<x>] sections of pyproject.toml
BASELINE = "tests/complexity_baseline.json"
FIXTURE_PREFIX = "test-fixture"
# lane -> the PROTECTED files it may change (0.5.0 spec §4.0); every other lane changes none
PROTECTED_ALLOWED: dict[str, frozenset[str]] = {
    "F": frozenset({"scripts/dev/lane_gate.py", "tests/engine/test_import_boundary.py", "uv.lock"}),
    "F5a-harness": frozenset({"tests/conftest.py", "uv.lock", "tests/engine/test_import_boundary.py"}),
    "F5b": frozenset({"tests/engine/test_import_boundary.py"}),
    "U20-memory": frozenset({"uv.lock"}),  # inert until the owner's O4
    "W-workload": frozenset({"uv.lock"}),  # inert until the owner's O5
}
DEPENDENCY_ALLOWED = frozenset({"F", "F5a-harness", "U20-memory", "W-workload"})  # pyproject.toml dependency lists
FOUNDATION = frozenset({"F", "F5a-harness", "F5a-source", "F5a-core", "F5b"})  # may re-key the complexity baseline
LEASED_TESTS = ("test_read_only_wrapper_rejects_write", "test_autocommit_engine_is_unavailable")
_ADVISOR = "tests/fastapi/test_database_advisor_leased.py"
# lane -> ((coordinator-written gate log, node ids that must be PASSED in it), ...). A full node id matches only itself;
# A-postgresql keeps 0.4.0's bare names, matched as `::<name>` (its lane merged under that rule).
LEASED: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "A-postgresql": (("leased-pg.log", LEASED_TESTS),),
    "F5b": (
        (
            "leased-mysql.log",
            ("tests/fastapi/test_mysql_read_only_leased.py::test_mysql_read_only_wrapper_rejects_write",),
        ),
    ),
    "A-mysql": (
        (
            "leased-mysql.log",
            (
                "tests/fastapi/test_mysql_leased.py::test_read_only_wrapper_rejects_write",
                "tests/fastapi/test_mysql_leased.py::test_full_read_against_mysql_84",
            ),
        ),
    ),
    "A-dbadv-1": (
        ("leased-pg.log", (f"{_ADVISOR}::test_read_only_wrapper_rejects_write[postgresql]",)),
        ("leased-mysql.log", (f"{_ADVISOR}::test_read_only_wrapper_rejects_write[mysql]",)),
    ),
    "A-dbadv-2": (
        ("leased-pg.log", (f"{_ADVISOR}::test_pg_vendor_rules_against_server",)),
        ("leased-mysql.log", (f"{_ADVISOR}::test_mysql_vendor_rules_against_server",)),
    ),
}
# every release's reviewer-owned paths, so a lane of one release cannot plant another release's review either
REVIEWER_OWNED = re.compile(rf"^{re.escape(SDD)}/[^/]+/lanes/[^/]+/(review\.md|live-verify\.md|gate/.*)$")
UNRESOLVED = (
    f"cannot resolve the release: the integration HEAD is not on release/<x> and its worktree does not hold exactly"
    f" one {SDD}/<x>/lanes folder; pass --release"
)
BUDGET_LINE = re.compile(r"^(BUDGET\w*)\s*(?::[^=]*)?=\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Options:
    lane: str
    worktree: Path
    sha: str
    integration: Path
    accept_unverified: bool = False
    no_rerun: bool = False
    allow_paths: tuple[str, ...] = ()
    release: str | None = None  # None: resolved from the integration worktree (resolve_release)
    plan_index: Path | None = None  # PLAN.md with the Lanes table; None: no council or must-cover check
    plan: Path | None = None  # the lane plan file; None: PLAN.md's "Plan file" column


@dataclass
class Result:
    refusals: list[str] = field(default_factory=list[str])
    unverified: list[str] = field(default_factory=list[str])
    notes: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class Red:
    test: str
    sha: str
    manual: bool = False  # from a table under a UI/manual heading: a non-pytest id there is `unverified`


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


def resolve_release(integration: Path) -> tuple[str | None, str]:
    """(release or None, how it was found) when ``--release`` is absent: the integration branch ``release/<x>``, else
    the one ``<SDD>/<x>/lanes`` folder in the integration worktree. Anything else does not resolve: never a default."""
    branch = _git(integration, "branch", "--show-current", check=False).stdout.strip()
    if branch.startswith("release/"):
        return branch.removeprefix("release/"), f"release {branch.removeprefix('release/')} from branch {branch}"
    found = sorted(path.parent.name for path in (integration / SDD).glob("*/lanes") if path.is_dir())
    if len(found) == 1:
        return found[0], f"release {found[0]} from the only {SDD}/<x>/lanes folder in {integration}"
    return None, UNRESOLVED


def _folder(opts: Options) -> str:
    """The lane's evidence folder, relative to a worktree root."""
    if opts.release is None:
        raise ValueError("Options.release is unresolved: evaluate() resolves it")
    return f"{SDD}/{opts.release}/lanes/{opts.lane}"


# --- markdown tables --------------------------------------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _code(cell: str) -> str:
    """The first `code span` in a cell (a cell may add notes after it), else the cell's text."""
    found = re.search(r"`([^`]+)`", cell)
    return found.group(1).strip() if found else cell.strip()


def _tables(text: str) -> Iterator[tuple[list[str], list[list[str]]]]:
    """Yield (lower-cased header, rows) for every markdown table in ``text``."""
    for _heading, header, rows in _headed_tables(text):
        yield header, rows


def _headed_tables(text: str) -> Iterator[tuple[str, list[str], list[list[str]]]]:
    """Yield (nearest markdown heading above, lower-cased header, rows) for every table in ``text``."""
    lines = text.splitlines()
    heading = ""
    i = 0
    while i < len(lines):
        if lines[i].startswith("#"):
            heading = lines[i]
        is_head = lines[i].lstrip().startswith("|") and i + 1 < len(lines)
        if is_head and re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", lines[i + 1]) and "-" in lines[i + 1]:
            header = [cell.lower() for cell in _cells(lines[i])]
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            yield heading, header, rows
        else:
            i += 1


def _column(header: list[str], *names: str) -> int | None:
    return next((header.index(name) for name in names if name in header), None)


def _test_column(header: list[str]) -> int | None:
    """``Test id``/``Test``, else the first header with the word ``test`` (``Vitest test``, ``test (node id)``)."""
    found = _column(header, "test id", "test")
    return found if found is not None else next((i for i, name in enumerate(header) if "test" in name.split()), None)


def _not_a_red(disposition: str) -> bool:
    """A ``pin: <mutation>`` or ``N/A — <reason>`` findings row (0.5.0 PLAN.md): no red SHA, never replayed."""
    return bool(re.match(r"(pin\b|n/a\b)", disposition.strip().lower()))


def _cell(row: list[str], col: int | None) -> str:
    return _code(row[col]) if col is not None and col < len(row) else ""


def red_tests(texts: Mapping[str, str]) -> tuple[list[Red], list[str]]:
    """Every (test, red SHA) pair from tables with a ``Test id``/``Test`` column and a column whose header contains
    ``Red SHA``, de-duplicated, plus the problems: a row naming a test with a blank Red SHA (unless parked), and a
    findings table (one with a ``Disposition`` column) without a Red SHA column."""
    reds: dict[Red, None] = {}
    problems: list[str] = []
    for label, text in texts.items():
        for heading, header, rows in _headed_tables(text):
            test_col = _test_column(header)
            manual = bool(re.search(r"\b(ui|manual)\b", heading, re.IGNORECASE))
            sha_col = next((i for i, name in enumerate(header) if "red sha" in name), None)
            disp_col = _column(header, "disposition")
            if sha_col is None and disp_col is not None:
                problems.append(f"{label}: a findings table has no Red SHA column")
            if test_col is None or sha_col is None:
                continue
            for row in rows:
                test, sha = _cell(row, test_col), _cell(row, sha_col)
                disposition = row[disp_col] if disp_col is not None and disp_col < len(row) else ""
                parked = not sha and disposition.lower().startswith("parked")  # raw cell, as in findings
                if not test or parked or _not_a_red(disposition):
                    continue
                if sha:
                    reds[Red(test, sha, manual)] = None
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
    if lane in FOUNDATION:  # F1c: a foundation lane may re-key moved code; the per-finding total must not rise
        rose = sum(new.values()) > sum(old.values())
        return [f"complexity baseline total rose: {sum(old.values())} -> {sum(new.values())}"] if rose else []
    problems = [f"complexity baseline entry added: {key}" for key in new if key not in old]
    problems += [f"complexity baseline raised: {key}" for key in new if key in old and new[key] > old[key]]
    return problems


def _gate_config(text: str | None) -> dict[str, object]:
    tool = tomllib.loads(text or "").get("tool", {})
    return {name: tool.get(name) for name in GATE_CONFIG}


def diff_refusals(opts: Options, base: str) -> tuple[list[str], list[str]]:
    """(refusals, notes): a refusal for a path named by ``--allow-path`` becomes a note instead."""
    problems: list[str] = []
    notes: list[str] = []
    for path in _diff_paths(opts.worktree, base, opts.sha):
        found = _path_refusals(opts, base, path)
        if path in opts.allow_paths:
            notes += [f"allowed by --allow-path: {problem}" for problem in found]
        else:
            problems += found
    return problems, notes


def _path_refusals(opts: Options, base: str, path: str) -> list[str]:
    before, after = _show(opts.worktree, base, path), _show(opts.worktree, opts.sha, path)
    if REVIEWER_OWNED.match(path):
        return [f"reviewer-owned path changed: {path}"]
    if path in PROTECTED and path not in PROTECTED_ALLOWED.get(opts.lane, frozenset()):
        return [f"protected path changed: {path}"]
    if path == BASELINE:
        return _baseline_refusals(opts.lane, before, after)
    if path == "pyproject.toml":
        old, new = _gate_config(before), _gate_config(after)
        problems = [f"gate config changed: pyproject.toml [tool.{n}]" for n in GATE_CONFIG if old[n] != new[n]]
        if opts.lane not in DEPENDENCY_ALLOWED and _dependency_lists(before) != _dependency_lists(after):
            problems.append("dependency list changed: pyproject.toml")
        return problems
    return _overhead_problems(path, before or "", after or "") if _is_overhead_module(path, before) else []


def _is_overhead_module(path: str, before: str | None) -> bool:
    """An overhead test module: under tests/, assigns a ``BUDGET*`` name, or calls or defines ``check_budget``, by AST,
    so text inside a string literal never counts. Only these files are scanned, so a script that merely mentions a
    budget name (this gate) is not one. Unparsable source falls back to the text rule."""
    if not (path.startswith("tests/") and path.endswith(".py") and before):
        return False
    try:
        tree = ast.parse(before)
    except SyntaxError:  # fail closed: the text rule
        return bool(BUDGET_LINE.search(before) or "check_budget(" in before)
    for node in ast.walk(tree):  # a function-local BUDGET counts too: fail closed
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id.startswith("BUDGET") for t in targets):
                return True
        func = node.func if isinstance(node, ast.Call) else None
        called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        defined = node.name if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) else ""
        if "check_budget" in (called, defined):
            return True
    return False


def _overhead_problems(path: str, before: str, after: str) -> list[str]:
    """In an overhead module only new test functions may be added: no existing top-level name may change."""
    old, new = _definitions(before), _definitions(after)
    names = sorted(n for n in old if new.get(n) != old[n])
    names += sorted(n for n in new if n not in old and not n.startswith("test"))
    return [f"overhead budget module changed: {path} ({', '.join(names)})"] if names else []


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
        elif re.search(r"N/A\s*[—–:-]+\s*[^\s|]", line) or any(
            _evidence_path_exists(opts, t) for t in re.findall(r"`([^`]+)`", line)
        ):
            continue
        elif "N/A" in line:
            problems.append(f"checklist.md: item {n} has N/A without a reason (write N/A — <reason>)")
        else:
            problems.append(f"checklist.md: item {n} has no existing evidence path")
    return problems


def _findings_refusals(text: str) -> list[str]:
    problems: list[str] = []
    tables = list(_tables(text))
    if any(rows for _header, rows in tables) and not any("disposition" in header for header, _rows in tables):
        problems.append("findings.md: no table with a Disposition column (every finding needs one)")
    for header, rows in tables:
        disp_col, test_col = _column(header, "disposition"), _test_column(header)
        if disp_col is None:
            continue
        for row in rows:
            disposition = row[disp_col] if len(row) > disp_col else ""
            test = row[test_col] if test_col is not None and len(row) > test_col else ""
            word = disposition.lower()
            fixed = word.startswith("fixed") and bool(test)
            parked = word.startswith("parked") and bool(disposition[6:].strip(" :-—–()"))
            pinned = bool(re.match(r"pin\b[\s:—–-]*[^\s:—–-]", word))  # pin: <the mutation, the assertion it failed>
            not_applicable = bool(re.match(r"n/a\s*[—–:-]+\s*[^\s:—–-]", word))  # N/A — <reason>
            if not (fixed or parked or pinned or not_applicable):
                problems.append(f"findings.md: unresolved finding: {' | '.join(row)}")
    return problems


def _review_refusals(opts: Options, handoff: str) -> list[str]:
    path = opts.integration / _folder(opts) / "review.md"
    if not path.is_file():
        return [f"missing review: {path}"]
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    problems: list[str] = []
    if not lines or lines[-1] != "VERDICT: APPROVE":
        problems.append("review.md: last line is not VERDICT: APPROVE")
    if not any(opts.sha.startswith(token) for token in re.findall(r"\b[0-9a-f]{7,40}\b", text)):
        problems.append(f"review.md: does not name the head SHA {opts.sha} (or a prefix of 7+ characters)")
    reviewer = re.search(r"^Reviewer:\s*(\S+)", text, re.MULTILINE)
    implementer = re.search(r"^Implementer:\s*(\S+)", handoff, re.MULTILINE)
    if implementer is None:
        problems.append("handoff.md: no 'Implementer: <id>' line (needed to check the reviewer is someone else)")
    if reviewer is None:
        problems.append("review.md: no reviewer id (a 'Reviewer: <id>' line)")
    elif implementer is not None and reviewer.group(1) == implementer.group(1):
        problems.append(f"review.md: reviewer is the implementer ({reviewer.group(1)})")
    return problems


def evidence_refusals(opts: Options, base: str) -> tuple[list[str], dict[str, str]]:
    folder = _folder(opts)
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
        lines = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
        if not lines or opts.sha not in lines[0]:
            problems.append(f"gate/{name}.log does not name head {opts.sha} on line 1 (missing or stale)")
        elif [line.strip() for line in lines if line.strip()][-1] != "exit 0":
            problems.append(f"gate/{name}.log does not record exit 0 as its last line (a failed run)")
    return problems, found


def leased_problem(opts: Options, log_name: str, node_ids: Sequence[str]) -> str | None:
    tag = log_name.removesuffix(".log")
    log = opts.integration / _folder(opts) / "gate" / log_name
    if not log.is_file():
        return f"{tag}: {log} missing"
    lines = log.read_text(encoding="utf-8").splitlines()
    if not lines or opts.sha not in lines[0]:
        return f"{tag}: gate/{log_name} line 1 does not name the head SHA"
    for nodeid in node_ids:
        found = rf"(?:^|\s){re.escape(nodeid)}" if "::" in nodeid else rf"::{re.escape(nodeid)}"
        if not any(re.search(rf"{found}\s+PASSED\b", ln) for ln in lines[1:]):
            return f"{tag}: {nodeid} not PASSED (missing or skipped)"
    return None


# --- council and must-cover (0.5.0 spec §4.0) -------------------------------------------------------------------------

FAMILIES = {  # model family -> words that name it in council.md
    "anthropic": ("claude", "opus", "sonnet", "haiku", "fable"),
    "openai": ("codex", "gpt"),
    "google": ("gemini", "agy", "argon"),
}
TEST_TOKEN = re.compile(r"^(?:[\w./-]+\.py::)?(?:\w+::)*test\w*(?:\[[^\]]*\])?$")
GOLDEN_SKIP = "post-scan golden absent"  # a must-cover skip the gate reports as unverified, not refused


def _lane_row(plan_index: Path, lane: str) -> tuple[dict[str, str] | None, set[str]]:
    """(the lane's row, every lane id) of PLAN.md's Lanes table: the first table with Lane, Plan file and Council."""
    for header, rows in _tables(plan_index.read_text(encoding="utf-8")):
        if {"lane", "plan file", "council"} <= set(header):
            lanes = {_code(row[0]): dict(zip(header, row, strict=False)) for row in rows}
            return lanes.get(lane), set(lanes)
    return None, set()


def _council_names_head(opts: Options, token: str) -> bool:
    """``token`` is a commit whose code is the head's: an ancestor followed only by changes to the lane's evidence."""
    sha = _resolve(opts.worktree, token)
    if sha is None or not _is_ancestor(opts.worktree, sha, opts.sha):
        return False
    return all(path.startswith(f"{_folder(opts)}/") for path in _diff_paths(opts.worktree, sha, opts.sha))


def _council_refusals(opts: Options) -> list[str]:
    text = _show(opts.worktree, opts.sha, f"{_folder(opts)}/council.md")
    if text is None:
        return [f"council.md missing: PLAN.md's Lanes table says Council: required for {opts.lane}"]
    problems: list[str] = []
    if not re.search(r"^VERDICT:\s*APPROVE\b", text, re.MULTILINE):
        problems.append("council.md: no 'VERDICT: APPROVE' line")
    words = set(re.findall(r"[a-z]+", text.lower()))
    families = [family for family, names in FAMILIES.items() if words & set(names)]
    if len(families) < 2:
        problems.append(f"council.md: fewer than two model families ({', '.join(families) or 'none named'})")
    if not any(_council_names_head(opts, token) for token in re.findall(r"\b[0-9a-f]{7,40}\b", text)):
        problems.append(f"council.md: does not name the head SHA {opts.sha} (or a commit followed only by evidence)")
    return problems


def must_cover_names(plan_text: str, lane: str, lanes: set[str]) -> list[str] | None:
    """The tests named in the plan's ``## Must-cover`` section, or None without one. In a multi-lane plan file (a
    paragraph starts ``<lane id>:``) only the lane's own paragraphs count."""
    found = re.search(r"^## Must-cover[^\n]*\n(.*?)(?=^#{1,2} |\Z)", plan_text, re.MULTILINE | re.DOTALL)
    if found is None:
        return None
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", found.group(1)) if p.strip()]
    owner = {p: m.group(1) for p in paragraphs if (m := re.match(r"([\w.-]+):\s", p)) and m.group(1) in lanes}
    if owner:
        paragraphs = [p for p in paragraphs if owner.get(p) == lane]
    names = (token.strip() for p in paragraphs for token in re.findall(r"`([^`]+)`", p))
    return list(dict.fromkeys(name for name in names if TEST_TOKEN.match(name)))


def _defined_tests(source: str) -> list[tuple[str, ...]]:
    """(enclosing class names..., function name) of every function in ``source``."""
    try:
        body = ast.parse(source).body
    except SyntaxError:
        return []
    found: list[tuple[str, ...]] = []

    def walk(nodes: list[ast.stmt], classes: tuple[str, ...]) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                walk(node.body, (*classes, node.name))
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                found.append((*classes, node.name))

    walk(body, ())
    return found


def must_cover_ids(opts: Options, base: str, names: Sequence[str]) -> tuple[list[str], list[str]]:
    """(node ids, refusals): a full node id must exist at the head; a bare name resolves only among the test files
    in the lane diff, and is refused when absent or ambiguous."""
    files = [p for p in _diff_paths(opts.worktree, base, opts.sha) if p.startswith("tests/") and p.endswith(".py")]
    ids: list[str] = []
    problems: list[str] = []
    for name in names:
        if ".py::" in name:
            if _test_node(_show(opts.worktree, opts.sha, name.split("::", 1)[0]) or "", name) is None:
                problems.append(f"must-cover {name}: not at the lane head")
            else:
                ids.append(name)
            continue
        bare = name.split("[", 1)[0]
        parts = tuple(bare.split("::"))
        hits = [
            "::".join((path, *found)) + name[len(bare) :]
            for path in files
            for found in _defined_tests(_show(opts.worktree, opts.sha, path) or "")
            if found[-len(parts) :] == parts
        ]
        if not hits:
            problems.append(f"must-cover {name}: not defined in a test file of the lane diff")
        elif len(hits) > 1:
            problems.append(f"must-cover {name}: ambiguous ({', '.join(hits)}); name it by full node id")
        else:
            ids.append(hits[0])
    return ids, problems


def plan_refusals(opts: Options, base: str) -> tuple[list[str], list[str]]:
    """(refusals, must-cover node ids) from PLAN.md's Lanes table and the lane plan file."""
    if opts.plan_index is None or not opts.plan_index.is_file():
        return [f"PLAN.md not found: {opts.plan_index}"], []
    row, lanes = _lane_row(opts.plan_index, opts.lane)
    if row is None:
        return [f"lane {opts.lane} is not in the Lanes table of {opts.plan_index}"], []
    problems = _council_refusals(opts) if row.get("council", "").lower().startswith("required") else []
    plan = opts.plan or opts.plan_index.parent / _code(row.get("plan file", ""))
    if not plan.is_file():
        return [*problems, f"lane plan not found: {plan}"], []
    names = must_cover_names(plan.read_text(encoding="utf-8"), opts.lane, lanes)
    if not names:
        return [*problems, f"{plan.name}: no ## Must-cover tests for lane {opts.lane}"], []
    ids, more = must_cover_ids(opts, base, names)
    return problems + more, ids


def _is_leased(nodeid: str, leased: Sequence[str]) -> bool:
    """A must-cover id the leased log decides: the same test (or one of its parametrisations), or a 0.4.0 bare name."""
    bare = nodeid.split("[", 1)[0]
    return any(
        nodeid == lid or lid.startswith(f"{nodeid}[") or ("::" not in lid and bare.endswith(f"::{lid}"))
        for lid in leased
    )


def must_cover_refusals(opts: Options, ids: Sequence[str], run_pytest: PytestRunner) -> tuple[list[str], list[str]]:
    """(refusals, unverified): every must-cover test passes at the head. A skip is refused unless the test is leased
    (the leased log decides) or skipped as ``post-scan golden absent`` (reported unverified)."""
    leased = [nodeid for _log, nodeids in LEASED.get(opts.lane, ()) for nodeid in nodeids]
    problems: list[str] = []
    unverified: list[str] = []
    for nodeid, outcomes in _replay(opts, opts.sha, ids, run_pytest).items():
        for outcome, detail in outcomes:
            if outcome == "passed" or (outcome == "skipped" and _is_leased(nodeid, leased)):
                continue
            if outcome == "skipped" and detail.startswith(GOLDEN_SKIP):
                unverified.append(f"must-cover {nodeid}: skipped ({detail})")
            elif outcome == "skipped":
                problems.append(f"must-cover {nodeid}: skipped ({detail})")
            else:
                problems.append(f"must-cover {nodeid}: {outcome} at the lane head")
    return problems, unverified


# --- red integrity and replay -----------------------------------------------------------------------------------------


def _function_source(source: str, nodeid: str) -> str | None:
    """The red test function's source, decorators and signature included."""
    found = _test_node(source, nodeid)
    return _segment(source, found[0]) if found else None


def _segment(source: str, node: ast.stmt) -> str:
    decorators = getattr(node, "decorator_list", [])
    start = min([node.lineno, *(d.lineno for d in decorators)])
    return "\n".join(source.splitlines()[start - 1 : node.end_lineno])


def _bound_names(node: ast.stmt) -> list[str]:
    """Names a top-level def, class or assignment binds."""
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [node.name]
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign | ast.AugAssign):
        targets = [node.target]
    return [n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name)]


def _definitions(source: str, body: list[ast.stmt] | None = None) -> dict[str, str]:
    """Each top-level name (or each name in ``body``, e.g. a class body) -> the source of its last definition (def,
    class, assignment, or one import alias)."""
    if body is None:
        try:
            body = ast.parse(source).body
        except SyntaxError:
            return {}
    defs: dict[str, str] = {}
    for node in body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            module = node.module if isinstance(node, ast.ImportFrom) else ""
            for alias in node.names:  # per alias, so adding a name to an import line changes nothing referenced
                defs[alias.asname or alias.name.split(".")[0]] = f"from {module} import {alias.name} as {alias.asname}"
        else:
            defs.update(dict.fromkeys(_bound_names(node), _segment(source, node)))
    return defs


def _class_definitions(source: str, classes: list[str]) -> dict[str, str]:
    try:
        body: list[ast.stmt] = ast.parse(source).body
    except SyntaxError:
        return {}
    for cls in classes:
        node = next((n for n in body if isinstance(n, ast.ClassDef) and n.name == cls), None)
        if node is None:
            return {}
        body = node.body
    return _definitions(source, body)


def _test_node(source: str, nodeid: str) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[str]] | None:
    """The red test's function node and the names of its enclosing classes."""
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
    return (func, classes) if func is not None else None


def _red_file_problems(opts: Options, sha: str, path: str, nodeid: str) -> list[str]:
    """Coordinator ruling on round 4: after the red commit, a top-level name the red test references (in its body,
    decorators or fixture arguments) may not change or disappear, in its file; a fixture it requests may not change
    in a conftest.py on its path. Added imports, new names and edits to unreferenced code are allowed."""
    red_source = _show(opts.worktree, sha, path) or ""
    found = _test_node(red_source, nodeid)
    if found is None:
        return ["test missing at red SHA"]
    func, classes = found
    args = [a.arg for a in (*func.args.posonlyargs, *func.args.args, *func.args.kwonlyargs) if a.arg != "self"]
    referenced = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)} | set(args)
    head_source = _show(opts.worktree, opts.sha, path) or ""
    before, after = _definitions(red_source), _definitions(head_source)
    problems = [
        f"referenced name {name} changed after the red commit"
        for name in sorted(referenced - {func.name})
        if after.get(name) != before.get(name)  # absent at the red SHA and defined later = a shadow
    ]
    if classes:  # a method red: its class may grow, but class names it uses (self.X, fixtures) stay frozen
        attrs = {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
        old_cls, new_cls = _class_definitions(red_source, classes), _class_definitions(head_source, classes)
        problems += [
            f"referenced name {name} changed after the red commit"
            for name in sorted((referenced | attrs) - {func.name})
            if name in old_cls and new_cls.get(name) != old_cls[name]
        ]
    parts = path.split("/")[:-1]
    for conftest in ("/".join([*parts[:i], "conftest.py"]) for i in range(len(parts) + 1)):
        old = _definitions(_show(opts.worktree, sha, conftest) or "")
        new = _definitions(_show(opts.worktree, opts.sha, conftest) or "")
        problems += [
            f"{conftest}: fixture {arg} changed after the red commit"
            for arg in args
            if arg not in before and old.get(arg) != new.get(arg)
        ]
    return problems


@dataclass
class _Integrity:
    replayable: list[Red] = field(default_factory=list[Red])
    problems: list[str] = field(default_factory=list[str])
    unverified: list[str] = field(default_factory=list[str])


def _sha_problem(opts: Options, base: str, red: Red) -> tuple[str | None, str]:
    """(problem or None, the resolved red SHA)."""
    sha = _resolve(opts.worktree, red.sha)
    if sha is None:
        return f"red SHA {red.sha} is unknown", ""
    if not _is_ancestor(opts.worktree, sha, opts.sha):
        return f"red SHA {red.sha} is not an ancestor of head", sha
    if _is_ancestor(opts.worktree, sha, base):
        return f"red SHA {red.sha} is not a lane commit (already in the integration branch)", sha
    return None, sha


def _source_problems(opts: Options, base: str, red: Red, sha: str) -> list[str]:
    path = red.test.split("::", 1)[0]
    at_red = _function_source(_show(opts.worktree, sha, path) or "", red.test)
    at_head = _function_source(_show(opts.worktree, opts.sha, path) or "", red.test)
    if at_red is None:
        return [f"test missing at red SHA {red.sha}"]
    if at_head is None:
        return ["test missing at head"]
    if at_red != at_head:
        return [f"test body changed after red commit {red.sha}"]
    if _function_source(_show(opts.worktree, base, path) or "", red.test) == at_red:
        # council r2: the red test must be in the lane diff; an old test plus a broken src is a fake red
        return ["test unchanged from the integration branch (a red must add or change it)"]
    return [f"{problem} {red.sha}" for problem in _red_file_problems(opts, sha, path, red.test)]


def red_integrity(opts: Options, base: str, reds: Sequence[Red]) -> _Integrity:
    out = _Integrity()
    if not reds:
        out.problems.append("no red tests recorded in findings.md/handoff.md (table: | Test id | Red SHA | ... |)")
    for red in reds:
        tag = f"red {red.test}"
        if ".py::" not in red.test and red.manual:
            out.unverified.append(f"{tag}: not a pytest test; replay it by hand at {red.sha}")
            continue
        if ".py::" not in red.test:
            out.problems.append(f"{tag}: not a pytest node id (path.py::name) and not in a UI/manual table")
            continue
        problem, sha = _sha_problem(opts, base, red)
        problems = [problem] if problem else _source_problems(opts, base, red, sha)
        out.problems += [f"{tag}: {p}" for p in problems]
        if not problems:
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


def _is_under_tests(frame_file: str, root: Path | None) -> bool:
    """A test file or a shared test helper (``tests/overhead.py::check_budget``). An ``assert`` anywhere else (``src``,
    ``scripts``, an installed package) is a disguised stub. An absolute frame is judged relative to ``root``."""
    frame = frame_file.replace("\\", "/")
    if root is not None:
        base = str(root).replace("\\", "/").rstrip("/") + "/"
        if frame.lower().startswith(base.lower()):  # Windows paths compare case-insensitively
            frame = frame[len(base) :]
    return frame.startswith("tests/")


def _classify(name: str, frame: str, root: Path | None) -> str:
    """The detail a red is judged by: "AssertionError" when it counts as an assertion red.

    An ``assert`` or a ``pytest.raises`` DID NOT RAISE counts only when its last frame is under ``tests/`` (the test
    file or a shared helper). Without a frame nobody can tell it was not raised in ``src``: that fails closed.
    """
    if name not in ("AssertionError", "DidNotRaise"):
        return name
    shown = "AssertionError" if name == "AssertionError" else "pytest.raises DID NOT RAISE"
    if not frame:
        return f"{shown} with no traceback frame (cannot tell where it was raised)"
    if not _is_under_tests(frame, root):
        return f"{shown} raised outside the test file, not under tests/ ({frame})"
    return "AssertionError"


Outcome = tuple[str, str]  # (passed|failure|error|skipped|not collected, a failure's exception class name)


def is_red(outcome: Outcome) -> bool:
    """The one accept rule, shared with scripts/dev/red_check.py: a failure judged an assertion red."""
    return outcome == ("failure", "AssertionError")


def red_verdicts(junit: Path, nodeids: Sequence[str], root: Path | None = None) -> dict[str, list[Outcome]]:
    """nodeid -> the outcome of every matching case: a bare function id matches all its parametrisations.

    ``root`` is the tree pytest ran in, so an absolute traceback frame can be judged as under ``tests/`` or not.
    A setup/teardown error outranks a failure in the same case: a red with a teardown error is not clean.
    """
    cases = ET.parse(junit).getroot().iter("testcase") if junit.is_file() else iter(())
    by_key: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for case in cases:
        outcome, message, frame = "passed", "", ""
        for kind in ("error", "failure", "skipped"):
            child = case.find(kind)
            if child is not None:
                outcome = kind
                message, frame = _exception_name(child) if kind == "failure" else (child.get("message", ""), "")
                if message == "Failed" and child.get("message", "").startswith("Failed: DID NOT RAISE"):
                    message = "DidNotRaise"
                break
        name = case.get("name", "")
        for key in {name, name.split("[", 1)[0]}:
            by_key.setdefault((case.get("classname", ""), key), []).append((outcome, message, frame))
    result: dict[str, list[Outcome]] = {}
    for nodeid in nodeids:
        path, *rest = nodeid.split("::")
        classname = ".".join([path.removesuffix(".py").replace("/", "."), *rest[:-1]])
        result[nodeid] = [
            (o, _classify(m, f, root) if o == "failure" else m)
            for o, m, f in by_key.get((classname, rest[-1]), [("not collected", "", "")])
        ]
    return result


@contextlib.contextmanager
def _temp_tree(opts: Options, sha: str) -> Generator[Path]:
    """A detached worktree at ``sha`` in a temp folder: only committed files, removed (and pruned) afterwards."""
    scratch = Path(tempfile.mkdtemp(prefix="lane-gate-"))
    tree = scratch / "tree"
    try:
        _git(opts.worktree, "worktree", "add", "--detach", "--quiet", str(tree), sha)
        yield tree
    finally:
        _git(opts.worktree, "worktree", "remove", "--force", str(tree), check=False)
        shutil.rmtree(scratch, ignore_errors=True)
        _git(opts.worktree, "worktree", "prune", check=False)


def _replay(opts: Options, sha: str, nodeids: Sequence[str], run_pytest: PytestRunner) -> dict[str, list[Outcome]]:
    with _temp_tree(opts, sha) as tree:
        junit = tree.parent / "junit.xml"
        run_pytest(tree, nodeids, junit)
        return red_verdicts(junit, nodeids, tree)


def replay_refusals(opts: Options, reds: Sequence[Red], run_pytest: PytestRunner) -> list[str]:
    problems: list[str] = []
    for sha in dict.fromkeys(red.sha for red in reds):
        ids = [red.test for red in reds if red.sha == sha]
        for nodeid, outcomes in _replay(opts, sha, ids, run_pytest).items():
            bad = [(o, m) for o, m in outcomes if not is_red((o, m))]
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


def gate_refusals(opts: Options, run_gate: GateRunner, prepare_env: EnvPreparer) -> list[str]:
    """The four gates in a fresh detached tree at the head, never the implementer's tree or virtualenv (untracked
    files, a planted ``.pth``); the tree's environment is synced from the lane's own lock first."""
    logs = opts.integration / _folder(opts) / "gate"
    logs.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with _temp_tree(opts, opts.sha) as tree:
        code, output = prepare_env(tree)
        (logs / "uv-sync.log").write_text(f"{opts.sha}\n$ {' '.join(SYNC)}\nexit {code}\n{output}", encoding="utf-8")
        if code != 0:
            return [f"environment sync failed in the fresh tree (exit {code}); see {logs / 'uv-sync.log'}"]
        for name, command, _timeout in GATES:
            code, output = run_gate(name, command, tree)
            log = logs / f"{name}.log"
            log.write_text(f"{opts.sha}\n$ {' '.join(command)}\nexit {code}\n{output}", encoding="utf-8")
            if code != 0:
                problems.append(f"gate {name} failed (exit {code}); see {log}")
    return problems


def _env(**extra: str) -> dict[str, str]:
    # uv's default hardlinks hit Windows' per-file link limit on a busy cache (os error 1142); copying always works.
    # A caller's activated venv must not stand in for the tree's own .venv.
    env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}}
    return {"UV_LINK_MODE": "copy", **env, **extra}


def run_gate_command(name: str, command: Sequence[str], cwd: Path) -> tuple[int, str]:
    timeout = next((t for n, _c, t in GATES if n == name), 900)  # uv-sync: 900 s
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
        # the integration venv was never synced with the test extra: `--extra test` keeps pytest installed
        command = ["uv", "run", "--project", str(integration), "--frozen", "--extra", "test", "python", "-m", "pytest"]
        command += ["-q", "-p", "no:cacheprovider", "-p", "no:randomly", "--tb=long", f"--junitxml={junit}", *nodeids]
        subprocess.run(command, cwd=tree, env=env, capture_output=True, timeout=900, check=False)

    return run


# --- entry points -----------------------------------------------------------------------------------------------------


def _with_release(opts: Options, result: Result) -> Options | None:
    """``opts`` with its release resolved (noted), or None with the refusal recorded."""
    if opts.release is not None:
        return opts
    release, how = resolve_release(opts.integration)
    (result.notes if release else result.refusals).append(how)
    return replace(opts, release=release) if release else None


def _worktree_refusals(opts: Options) -> list[str]:
    problems: list[str] = []
    if opts.no_rerun and not opts.lane.startswith(FIXTURE_PREFIX):
        problems.append(f"--no-rerun is only for test fixture lanes ({FIXTURE_PREFIX}-*), not {opts.lane}")
    head = _git(opts.worktree, "rev-parse", "HEAD").stdout.strip()
    if head != opts.sha:
        problems.append(f"{opts.sha} is not the worktree HEAD ({head}); gate the commit you mean")
    if _git(opts.worktree, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        problems.append("lane worktree has uncommitted changes")
    return problems


def _record_unverified(opts: Options, result: Result, integrity: _Integrity) -> None:
    """Non-pytest reds and leased-database gaps: recorded with --accept-unverified, else refused."""
    unverified = list(integrity.unverified)
    for log_name, node_ids in LEASED.get(opts.lane, ()):
        if problem := leased_problem(opts, log_name, node_ids):
            unverified.append(problem)
    if opts.accept_unverified:
        result.unverified = unverified
    else:
        result.refusals += [f"{line} (pass --accept-unverified to record it as unverified)" for line in unverified]


def evaluate(
    opts: Options,
    *,
    run_gate: GateRunner,
    run_pytest: PytestRunner,
    prepare_env: EnvPreparer = lambda tree: (0, ""),
) -> Result:
    result = Result()
    resolved = _with_release(opts, result)
    if resolved is None:
        return result
    opts = resolved
    result.refusals += _worktree_refusals(opts)
    integration_head = _git(opts.integration, "rev-parse", "HEAD").stdout.strip()
    base = _git(opts.worktree, "merge-base", integration_head, opts.sha).stdout.strip()

    diff_problems, notes = diff_refusals(opts, base)
    result.notes += notes
    result.refusals += diff_problems
    evidence, texts = evidence_refusals(opts, base)
    result.refusals += evidence
    reds, table_problems = red_tests({name: texts.get(name, "") for name in ("findings.md", "handoff.md")})
    integrity = red_integrity(opts, base, reds)
    result.refusals += table_problems + integrity.problems
    _record_unverified(opts, result, integrity)
    plan_problems, cover = plan_refusals(opts, base) if opts.plan_index is not None else ([], [])
    result.refusals += plan_problems
    if result.refusals:
        result.refusals.append("red replay and gate re-run skipped: fix the refusals above first")
        return result
    result.refusals += replay_refusals(opts, integrity.replayable, run_pytest)
    if result.refusals:  # keep the last gate logs: a refused replay must not overwrite them
        result.refusals.append("gate re-run skipped: the red replay refused")
        return result
    cover_problems, cover_unverified = must_cover_refusals(opts, cover, run_pytest) if cover else ([], [])
    result.unverified += cover_unverified  # post-scan golden absent: reported, never refused
    if cover_problems:
        result.refusals += [*cover_problems, "gate re-run skipped: a must-cover test refused"]
        return result
    if not opts.no_rerun:
        result.refusals += gate_refusals(opts, run_gate, prepare_env)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("lane")
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--sha")
    parser.add_argument("--integration", type=Path, default=Path.cwd())
    parser.add_argument("--accept-unverified", action="store_true")
    parser.add_argument("--no-rerun", action="store_true", help="test fixture lanes only")
    parser.add_argument("--allow-path", action="append", default=[], help="protected path this lane may change")
    parser.add_argument("--release", help="default: the integration branch release/<x>, else refused")
    parser.add_argument("--plan-index", type=Path, help="PLAN.md (Lanes table); default: the release's plan folder")
    parser.add_argument("--plan", type=Path, help="the lane plan file; default: PLAN.md's Plan file column")
    args = parser.parse_args(argv)
    integration: Path = args.integration.resolve()
    release, how = (args.release, "") if args.release else resolve_release(integration)
    if release is None:
        print(f"REFUSED: {how}")
        return 1
    worktree: Path = args.worktree or WORKTREE_ROOT / f"{release}-{args.lane}"
    plans = sorted(integration.glob(f"docs/superpowers/plans/*-sharpit-{release}/PLAN.md"))
    plan_index: Path | None = args.plan_index or (plans[0] if len(plans) == 1 else None)
    if plan_index is None and not args.lane.startswith(FIXTURE_PREFIX):  # council and must-cover need it
        print(f"REFUSED: no single PLAN.md for release {release} under docs/superpowers/plans/; pass --plan-index")
        return 1
    sha: str = args.sha or _git(worktree, "rev-parse", "HEAD").stdout.strip()
    allow = tuple(args.allow_path)
    opts = Options(
        args.lane,
        worktree.resolve(),
        sha,
        integration,
        args.accept_unverified,
        args.no_rerun,
        allow,
        release,
        plan_index.resolve() if plan_index else None,
        args.plan.resolve() if args.plan else None,
    )
    result = evaluate(
        opts,
        run_gate=run_gate_command,
        run_pytest=run_pytest_in(opts.integration),
        prepare_env=lambda tree: run_gate_command("uv-sync", SYNC, tree),  # the fresh tree's own .venv, lane's lock
    )
    for line in result.notes:
        print(f"note: {line}")
    for line in result.unverified:
        print(f"unverified: {line}")
    for line in result.refusals:
        print(f"REFUSED: {line}")
    print(f"lane {opts.lane} @ {sha}: {'REFUSED' if result.refusals else 'ACCEPTED'}")
    return 1 if result.refusals else 0


if __name__ == "__main__":
    sys.exit(main())
