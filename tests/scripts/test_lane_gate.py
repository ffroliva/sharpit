"""scripts/dev/lane_gate.py: the mechanical 0.4.0 merge gate (spec §10.3, council C2/F1c/F1f/R2/R7/round 4).

Each test builds a throwaway integration repo plus a lane worktree in ``tmp_path``. Git runs for real; the four gates
and the pytest replays are injected fakes, so these tests never run the real suite.
"""

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from _load import load_script

lane_gate = load_script("scripts/dev/lane_gate.py")

OVERHEAD_MODULE = "BUDGET_MS = 0.2\n\n\ndef test_request_overhead_budget():\n    assert 0.1 < BUDGET_MS\n"
RED_TEST = "def test_widget():\n    assert widget() == 2\n"
TEST_ID = "tests/test_widget.py::test_widget"
BASELINE = {"src/a.py": 3, "src/b.py": 2}


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


@dataclass
class Fixture:
    integration: Path
    worktree: Path
    lane: str
    red: str = ""
    head: str = ""
    outcomes: dict[str, str] = field(default_factory=dict)  # sha -> pass|failure|typeerror|error|skip|absent
    failing_gates: set[str] = field(default_factory=set)
    gate_calls: list[str] = field(default_factory=list)
    replays: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    @property
    def folder(self) -> str:
        return f".superpowers/sdd/0.4.0/lanes/{self.lane}"

    def commit(self, files: dict[str, str], message: str) -> str:
        _write(self.worktree, files)
        _git(self.worktree, "add", *files)
        _git(self.worktree, "commit", "-q", "-m", message)
        self.head = _git(self.worktree, "rev-parse", "HEAD")
        return self.head

    def evidence(self, *, skip: str = "", handoff_extra: str = "") -> str:
        files = {
            f"{self.folder}/handoff.md": (
                f"# handoff\n\nImplementer: codex-x\n\n| Test id | Red SHA | Assertion message |\n|---|---|---|\n"
                f"| `{TEST_ID}` | `{self.red}` | `assert widget() == 2` |\n{handoff_extra}"
            ),
            f"{self.folder}/findings.md": (
                "| Finding | Test | Red SHA | Assertion message | Disposition |\n|---|---|---|---|---|\n"
                f"| widget is wrong | `{TEST_ID}` | `{self.red}` | `assert widget() == 2` | Fixed in fix commit |\n"
            ),
            f"{self.folder}/field-map.md": "N/A — not a panel lane\n",
            f"{self.folder}/checklist.md": "| # | Item | Evidence |\n|---|---|---|\n"
            + "".join(f"| {n} | item {n} | {'`src/widget.py`' if n == 1 else 'N/A — r'} |\n" for n in range(1, 11)),
        }
        files.pop(f"{self.folder}/{skip}", None)
        return self.commit(files, "docs: lane evidence")

    def review(self, body: str | None = None) -> None:
        text = body if body is not None else f"Reviewer: claude-reviewer\nHead: {self.head}\n\nVERDICT: APPROVE\n"
        _write(self.integration, {f"{self.folder}/review.md": text})
        names = ("lowest-direct", "no-sqlalchemy")
        logs = {f"{self.folder}/gate/{name}.log": f"{self.head}\n$ cmd\nok\nexit 0\n" for name in names}
        _write(self.integration, logs)

    def options(self, **overrides: object) -> object:
        values: dict[str, object] = {
            "lane": self.lane,
            "worktree": self.worktree,
            "sha": self.head,
            "integration": self.integration,
        }
        values.update(overrides)
        return lane_gate.Options(**values)

    def run_gate(self, name: str, command: Sequence[str], cwd: Path) -> tuple[int, str]:
        self.gate_calls.append(name)
        return (1, "boom") if name in self.failing_gates else (0, "ok")

    def run_pytest(self, tree: Path, nodeids: Sequence[str], junit: Path) -> None:
        sha = _git(tree, "rev-parse", "HEAD")
        self.replays.append((sha, tuple(nodeids)))
        outcome = self.outcomes.get(sha, "failure" if sha == self.red else "pass")
        cases = []
        for nodeid in nodeids:
            module, *rest = nodeid.split("::")
            classname = ".".join([module.removesuffix(".py").replace("/", "."), *rest[:-1]])
            name = rest[-1]
            body = {
                "pass": "",
                "failure": f'<failure message="AssertionError: assert 1 == 2">E\n{module}:2: AssertionError</failure>',
                "helper-did-not-raise": '<failure message="Failed: DID NOT RAISE">E\ntests/h.py:4: Failed</failure>',
                "typeerror": '<failure message="TypeError: bad">trace</failure>',
                # real pytest: a rewritten assert's message names no exception; --tb=long ends "<file>:<line>: <type>"
                "rewritten": f'<failure message="assert 1 == 2">E   assert 1\n{module}:2: AssertionError</failure>',
                "helper-assert": '<failure message="assert 0">E   x\ntests/overhead.py:9: AssertionError</failure>',
                "did-not-raise": f'<failure message="Failed: DID NOT RAISE">E   Failed\n{module}:2: Failed</failure>',
                "pytest-fail": f'<failure message="Failed: nope">E   Failed: nope\n{module}:2: Failed</failure>',
                "src-assert": '<failure message="assert 0">E   assert 0\nsrc/widget.py:2: AssertionError</failure>',
                "bare-assert": '<failure message="assert 0 == 2">no traceback tail</failure>',
                "typed": '<failure type="AssertionError" message="custom text">no traceback tail</failure>',
                "rpcerror": '<failure message="pkg.RpcError: x">E   pkg.RpcError: x\nt.py:2: RpcError</failure>',
                "error": '<error message="failed on setup">trace</error>',
                "skip": '<skipped message="skip" />',
                "scripts-assert": '<failure message="assert 0">E   x\nscripts/helper.py:2: AssertionError</failure>',
                "abs-helper": f'<failure message="assert 0">E\n{tree}\\tests\\helpers.py:3: AssertionError</failure>',
                "abs-src-assert": f'<failure message="assert 0">E\n{tree}\\src\\widget.py:2: AssertionError</failure>',
                "teardown": f'<failure message="assert 0">E   x\n{module}:2: AssertionError</failure>'
                '<error message="failed on teardown with &quot;RuntimeError&quot;">trace</error>',
            }
            if outcome == "mixed-params":  # one parametrisation fails as a red should, the other passes
                cases.append(f'<testcase classname="{classname}" name="{name}[a]">{body["rewritten"]}</testcase>')
                cases.append(f'<testcase classname="{classname}" name="{name}[b]"></testcase>')
            elif outcome != "absent":
                cases.append(f'<testcase classname="{classname}" name="{name}">{body[outcome]}</testcase>')
        junit.write_text(f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>", encoding="utf-8")

    def evaluate(self, **overrides: object) -> object:
        return lane_gate.evaluate(self.options(**overrides), run_gate=self.run_gate, run_pytest=self.run_pytest)


def _base_files() -> dict[str, str]:
    return {
        "src/widget.py": "def widget():\n    return 0\n",
        "tests/complexity_baseline.json": json.dumps(BASELINE, indent=2) + "\n",
        "sonar-baseline.txt": "7\n",
        "scripts/dev/lane_gate.py": "# gate\n",
        "tests/engine/test_import_boundary.py": "RULES = {}\n",
        "tests/fastapi/test_capture_overhead.py": OVERHEAD_MODULE,
        "tests/overhead.py": "def check_budget():\n    pass\n",
        "pyproject.toml": '[project]\nname = "x"\ndependencies = ["starlette"]\n',
        "uv.lock": "lock\n",
    }


def _fixture(tmp_path: Path, lane: str = "test-fixture-x", *, review: bool = True) -> Fixture:
    integration = tmp_path / "integration"
    integration.mkdir()
    _git(integration, "init", "-q", "-b", "release")
    _git(integration, "config", "user.email", "t@example.com")
    _git(integration, "config", "user.name", "t")
    _git(integration, "config", "core.hooksPath", str(tmp_path / "no-hooks"))  # the owner's global hooks are slow
    _write(integration, _base_files())
    _git(integration, "add", ".")
    _git(integration, "commit", "-q", "-m", "base")
    worktree = tmp_path / "lane"
    _git(integration, "worktree", "add", "-q", "-b", f"lane/{lane}", str(worktree))
    fx = Fixture(integration, worktree, lane)
    fx.red = fx.commit(
        {
            "tests/test_widget.py": "from src.widget import widget\n\n\n" + RED_TEST,
            "src/widget.py": "def widget():\n    return 1\n",
        },
        "test: pin widget",
    )
    fx.commit({"src/widget.py": "def widget():\n    return 2\n"}, "feat: widget")
    fx.evidence()
    if review:
        fx.review()
    return fx


def _refusals(result: object) -> list[str]:
    return list(result.refusals)  # type: ignore[attr-defined]


def _refused(result: object, needle: str) -> bool:
    return any(needle in reason for reason in _refusals(result))


# --- controls ---------------------------------------------------------------------------------------------------------


def test_lane_gate_accepts_complete_evidence(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    result = fx.evaluate()
    assert _refusals(result) == []
    assert fx.gate_calls == ["ruff-check", "ruff-format", "pyright", "pytest"]
    assert (fx.red, (TEST_ID,)) in fx.replays
    assert (fx.head, (TEST_ID,)) in fx.replays
    log = (fx.integration / fx.folder / "gate" / "pytest.log").read_text(encoding="utf-8")
    assert log.splitlines()[0] == fx.head


def test_lane_gate_allows_only_decreasing_complexity_baseline(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({"tests/complexity_baseline.json": json.dumps({"src/a.py": 2}) + "\n"}, "refactor: simplify")
    fx.review()
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_main_exits_zero_only_when_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fx = _fixture(tmp_path)
    monkeypatch.setattr(lane_gate, "run_gate_command", fx.run_gate)
    monkeypatch.setattr(lane_gate, "run_pytest_in", lambda integration: fx.run_pytest)
    argv = [fx.lane, "--worktree", str(fx.worktree), "--integration", str(fx.integration)]
    assert lane_gate.main(argv) == 0
    (fx.integration / fx.folder / "review.md").unlink()
    assert lane_gate.main(argv) == 1


# --- reviewer verdict and evidence ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ("Reviewer: r\nHead: {head}\n", "VERDICT: APPROVE"),
        ("Reviewer: r\nHead: {head}\nVERDICT: APPROVE\nlater text\n", "VERDICT: APPROVE"),
        ("Reviewer: r\nHead: 0000000\nVERDICT: APPROVE\n", "head SHA"),
        ("Head: {head}\nVERDICT: APPROVE\n", "reviewer"),
        ("Reviewer: codex-x\nHead: {head}\nVERDICT: APPROVE\n", "reviewer is the implementer"),
    ],
)
def test_lane_gate_refuses_missing_verdict_or_wrong_reviewer_or_sha(tmp_path: Path, body: str, needle: str) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.review(body.format(head=fx.head))
    assert _refused(fx.evaluate(), needle)


@pytest.mark.parametrize("missing", ["handoff.md", "findings.md", "field-map.md", "checklist.md"])
def test_lane_gate_refuses_missing_field_map_handoff_or_checklist(tmp_path: Path, missing: str) -> None:
    fx = _fixture(tmp_path, review=False)
    _git(fx.worktree, "rm", "-q", f"{fx.folder}/{missing}")
    fx.commit({"src/other.py": "x = 1\n"}, "chore: drop evidence")
    fx.review()
    assert _refused(fx.evaluate(), f"missing evidence: {missing}")


def test_lane_gate_refuses_checklist_item_without_evidence(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    rows = "".join(f"| {n} | item {n} | {'`src/nope.py`' if n == 1 else 'N/A — r'} |\n" for n in range(1, 10))
    fx.commit({f"{fx.folder}/checklist.md": "| # | Item | Evidence |\n|---|---|---|\n" + rows}, "docs: checklist")
    fx.review()
    result = fx.evaluate()
    assert _refused(result, "checklist.md: item 1 has no existing evidence path")
    assert _refused(result, "checklist.md: item 10 missing")


@pytest.mark.parametrize("disposition", ["", "open", "fixed", "parked"])
def test_lane_gate_refuses_unresolved_finding(tmp_path: Path, disposition: str) -> None:
    fx = _fixture(tmp_path, review=False)
    test_cell = "" if disposition == "fixed" else f"`{TEST_ID}`"
    table = "| Finding | Test | Red SHA | Assertion message | Disposition |\n|---|---|---|---|---|\n"
    fx.commit({f"{fx.folder}/findings.md": f"{table}| f | {test_cell} | | | {disposition} |\n"}, "docs: findings")
    fx.review()
    assert _refused(fx.evaluate(), "findings.md: unresolved finding")


def test_lane_gate_refuses_gate_log_for_other_sha(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    _write(fx.integration, {f"{fx.folder}/gate/lowest-direct.log": "0123abc\nok\n"})
    assert _refused(fx.evaluate(), "gate/lowest-direct.log does not name head")


# --- protected diff ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body", "needle"),
    [
        (".superpowers/sdd/0.4.0/lanes/test-fixture-x/review.md", "VERDICT: APPROVE\n", "reviewer-owned"),
        (".superpowers/sdd/0.4.0/lanes/other/gate/pytest.log", "x\n", "reviewer-owned"),
        (".superpowers/sdd/0.4.0/lanes/test-fixture-x/live-verify.md", "x\n", "reviewer-owned"),
        ("scripts/dev/lane_gate.py", "# changed\n", "protected"),
        ("sonar-baseline.txt", "8\n", "protected"),
        ("tests/engine/test_import_boundary.py", "RULES = {'x': 1}\n", "protected"),
        ("tests/fastapi/test_capture_overhead.py", "BUDGET_MS = 0.4\n", "overhead budget"),
        ("uv.lock", "lock2\n", "protected"),
        ("pyproject.toml", '[project]\nname = "x"\ndependencies = ["starlette", "rich"]\n', "dependency"),
    ],
)
def test_lane_gate_refuses_protected_diff(tmp_path: Path, path: str, body: str, needle: str) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({path: body}, "chore: touch")
    fx.review()
    assert _refused(fx.evaluate(), needle)


def test_lane_gate_allows_pyproject_change_outside_dependency_lists(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({"pyproject.toml": '[project]\nname = "x"\ndependencies = ["starlette"]\n\n[tool.x]\ny = 1\n'}, "chore")
    fx.review()
    assert _refusals(fx.evaluate()) == []


@pytest.mark.parametrize("change", [{"src/a.py": 4, "src/b.py": 2}, {"src/a.py": 3, "src/b.py": 2, "src/c.py": 1}])
def test_lane_gate_refuses_complexity_baseline_increase(tmp_path: Path, change: dict[str, int]) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({"tests/complexity_baseline.json": json.dumps(change) + "\n"}, "chore: baseline")
    fx.review()
    assert _refused(fx.evaluate(), "complexity baseline")


def test_lane_gate_lets_lane_f_rekey_baseline_without_raising_total(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, lane="F", review=False)
    fx.commit({"tests/complexity_baseline.json": json.dumps({"src/a2.py": 3, "src/b.py": 2}) + "\n"}, "refactor")
    fx.commit({"scripts/dev/lane_gate.py": "# the gate itself\n"}, "feat: gate")
    fx.review()
    assert _refusals(fx.evaluate()) == []


# --- re-run gates ----------------------------------------------------------------------------------------------------


def test_lane_gate_refuses_when_rerun_gate_fails(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.failing_gates = {"ruff-check"}
    result = fx.evaluate()
    assert _refused(result, "gate ruff-check failed")
    log = (fx.integration / fx.folder / "gate" / "ruff-check.log").read_text(encoding="utf-8")
    assert log.splitlines()[0] == fx.head


def test_lane_gate_no_rerun_refused_for_real_lane(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, lane="A-data")
    result = fx.evaluate(no_rerun=True)
    assert _refused(result, "--no-rerun")


def test_lane_gate_no_rerun_skips_gates_for_fixture_lane(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    result = fx.evaluate(no_rerun=True)
    assert _refusals(result) == []
    assert fx.gate_calls == []


def test_lane_gate_refuses_sha_that_is_not_worktree_head(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    result = fx.evaluate(sha=fx.red)
    assert _refused(result, "is not the worktree HEAD")


# --- red replay (R2) and red integrity (round 4) ----------------------------------------------------------------------


def test_lane_gate_refuses_fake_red(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "pass"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: passed at red SHA")


@pytest.mark.parametrize(("outcome", "needle"), [("error", "error"), ("skip", "skipped"), ("typeerror", "TypeError")])
def test_lane_gate_refuses_error_as_red(tmp_path: Path, outcome: str, needle: str) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = outcome
    result = fx.evaluate()
    assert _refused(result, f"red {TEST_ID}: {needle}")


def test_lane_gate_refuses_collection_error_as_red(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "absent"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: not collected at red SHA")


def test_lane_gate_refuses_red_that_does_not_pass_at_head(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.head] = "failure"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: does not pass at head")


def test_lane_gate_refuses_missing_red_test(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    ghost = "tests/test_widget.py::test_ghost"
    fx.evidence(handoff_extra=f"| `{ghost}` | `{fx.red}` | `assert ghost` |\n")
    fx.review()
    assert _refused(fx.evaluate(), f"red {ghost}: test missing at red SHA")


def test_lane_gate_refuses_unknown_or_foreign_red_sha(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    base = _git(fx.integration, "rev-parse", "release")
    extra = f"| `{TEST_ID}` | `deadbeef` | `x` |\n| `{TEST_ID}` | `{base}` | `x` |\n"
    fx.evidence(handoff_extra=extra)
    fx.review()
    result = fx.evaluate()
    assert _refused(result, "red SHA deadbeef is unknown")
    assert _refused(result, f"red SHA {base} is not a lane commit")


def test_lane_gate_refuses_lane_without_red_tests(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({f"{fx.folder}/handoff.md": "# handoff\n", f"{fx.folder}/findings.md": "none\n"}, "docs: empty")
    fx.review()
    assert _refused(fx.evaluate(), "no red tests recorded")


def test_lane_gate_refuses_red_test_changed_after_red_commit(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    weakened = "from src.widget import widget\n\n\ndef test_widget():\n    assert widget() in (1, 2)\n"
    fx.commit({"tests/test_widget.py": weakened}, "test: loosen")
    fx.review()
    assert _refused(fx.evaluate(), f"red {TEST_ID}: test body changed after red commit")


def test_lane_gate_ignores_changes_outside_the_red_test_body(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    extra = "from src.widget import widget\n\n\n" + RED_TEST + "\n\ndef test_more():\n    assert widget() == 2\n"
    fx.commit({"tests/test_widget.py": extra}, "test: more")
    fx.review()
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_needs_accept_unverified_for_non_pytest_red(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    vitest = "ui/tests/unit/nav.test.ts::keeps panels out"
    ui_table = "\n## UI reds (manual replay)\n\n| Vitest test | Red SHA | Observed |\n|---|---|---|\n"
    ui_table += f"| `{vitest}` | `{fx.red}` | x |\n"
    fx.evidence(handoff_extra=ui_table)
    fx.review()
    assert _refused(fx.evaluate(), f"red {vitest}: not a pytest test")
    accepted = fx.evaluate(accept_unverified=True)
    assert _refusals(accepted) == []
    assert any(vitest in line for line in accepted.unverified)  # type: ignore[attr-defined]


# --- leased database (R7) ---------------------------------------------------------------------------------------------

LEASED_TESTS = ("test_read_only_wrapper_rejects_write", "test_autocommit_engine_is_unavailable")


def _leased_log(fx: Fixture, head: str, outcome: str = "PASSED") -> None:
    lines = [head, *(f"tests/engine/test_pg.py::{name} {outcome}" for name in LEASED_TESTS)]
    _write(fx.integration, {f"{fx.folder}/gate/leased-pg.log": "\n".join(lines) + "\n"})


@pytest.mark.parametrize("case", ["missing", "skipped", "other-sha"])
def test_lane_gate_refuses_postgresql_without_leased_db_log(tmp_path: Path, case: str) -> None:
    fx = _fixture(tmp_path, lane="A-postgresql")
    if case != "missing":
        _leased_log(fx, fx.head if case == "skipped" else "0123abc", "SKIPPED" if case == "skipped" else "PASSED")
    assert _refused(fx.evaluate(), "leased-pg")
    accepted = fx.evaluate(accept_unverified=True)
    assert _refusals(accepted) == []
    assert any("leased-pg" in line for line in accepted.unverified)  # type: ignore[attr-defined]


def test_lane_gate_accepts_postgresql_with_leased_db_log(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, lane="A-postgresql")
    _leased_log(fx, fx.head)
    result = fx.evaluate()
    assert _refusals(result) == []
    assert list(result.unverified) == []  # type: ignore[attr-defined]


# --- real pytest junit shapes (found replaying lane F's own reds) -----------------------------------------------------


def test_lane_gate_accepts_rewritten_assert_failure_as_red(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "rewritten"
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_refuses_non_assertion_failure_with_assert_like_message(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "rpcerror"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: RpcError failure")


def test_lane_gate_replays_with_long_tracebacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(lane_gate.subprocess, "run", lambda command, **kwargs: calls.append(command))
    lane_gate.run_pytest_in(tmp_path)(tmp_path, [TEST_ID], tmp_path / "junit.xml")
    assert "--tb=long" in calls[0]


def test_lane_gate_replay_syncs_the_test_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # F-rest item 3: `uv run --frozen` alone syncs the integration venv without pytest
    calls: list[list[str]] = []
    monkeypatch.setattr(lane_gate.subprocess, "run", lambda command, **kwargs: calls.append(command))
    lane_gate.run_pytest_in(tmp_path)(tmp_path, [TEST_ID], tmp_path / "junit.xml")
    assert calls[0][:7] == ["uv", "run", "--project", str(tmp_path), "--frozen", "--extra", "test"]


@pytest.mark.parametrize("outcome", ["bare-assert", "typed"])
def test_lane_gate_refuses_assertion_without_a_traceback_frame(tmp_path: Path, outcome: str) -> None:
    # fail closed (round 2): with no last frame nobody can tell the assert was not in src/
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = outcome
    assert _refused(fx.evaluate(), f"red {TEST_ID}: AssertionError with no traceback frame")


def test_lane_gate_reads_first_code_span_and_parametrized_ids(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    row = f"| `{TEST_ID}[case]` (1 param) | `{fx.red}` (parent of fix `{fx.head}`) | `assert x` |\n"
    fx.evidence(handoff_extra=row)
    fx.review()
    assert _refusals(fx.evaluate()) == []
    assert (fx.red, (TEST_ID, f"{TEST_ID}[case]")) in fx.replays


# --- review round 1 (review-gate.md) ----------------------------------------------------------------------------------


def _merge_release(fx: Fixture, files: dict[str, str]) -> None:
    """Commit ``files`` on the integration branch and merge it into the lane, moving the merge-base past them."""
    _write(fx.integration, files)
    _git(fx.integration, "add", *files)
    _git(fx.integration, "commit", "-q", "-m", "integration change")
    _git(fx.worktree, "merge", "-q", "--no-edit", "release")


def test_lane_gate_refuses_red_test_already_on_integration_branch(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    _merge_release(fx, {"tests/test_old.py": "def test_old():\n    assert 1\n"})
    red = fx.commit({"src/widget.py": "def widget():\n    return 3\n"}, "test: break src only")
    fx.commit({"src/widget.py": "def widget():\n    return 2\n"}, "fix: restore src")
    fx.outcomes[red] = "failure"  # the broken src really fails the old test
    fx.evidence(handoff_extra=f"| `tests/test_old.py::test_old` | `{red}` | `assert 1` |\n")
    fx.review()
    assert _refused(fx.evaluate(), "red tests/test_old.py::test_old: test unchanged from the integration branch")


def test_lane_gate_refuses_assertion_raised_outside_the_test(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "src-assert"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: AssertionError raised outside the test file")


FINDINGS_HEAD = "| Finding | Test | RED SHA (commit) | Assertion message | Disposition |\n|---|---|---|---|---|\n"


@pytest.mark.parametrize("sha_cell", ["", "n/a", "`n/a (not a red)`"])
def test_lane_gate_refuses_fixed_finding_without_red_sha(tmp_path: Path, sha_cell: str) -> None:
    fx = _fixture(tmp_path, review=False)
    rows = f"| ok | `{TEST_ID}` | `{fx.red}` | x | Fixed |\n"
    rows += f"| skipped | `tests/test_widget.py::test_x` | {sha_cell} | x | Fixed |\n"
    fx.commit({f"{fx.folder}/findings.md": FINDINGS_HEAD + rows}, "docs: findings")
    fx.review()
    assert _refused(fx.evaluate(), "tests/test_widget.py::test_x")


def test_lane_gate_refuses_findings_table_without_red_sha_column(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    table = (
        f"| Finding | Test | Red commit | Disposition |\n|---|---|---|---|\n| f | `{TEST_ID}` | `{fx.red}` | Fixed |\n"
    )
    fx.commit({f"{fx.folder}/findings.md": table}, "docs: findings")
    fx.review()
    assert _refused(fx.evaluate(), "findings.md: a findings table has no Red SHA column")


def test_lane_gate_allows_parked_finding_without_red_sha(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    rows = f"| ok | `{TEST_ID}` | `{fx.red}` | x | Fixed |\n| later | | | | Parked: needs the owner |\n"
    fx.commit({f"{fx.folder}/findings.md": FINDINGS_HEAD + rows}, "docs: findings")
    fx.review()
    assert _refusals(fx.evaluate()) == []


def _own_red(fx: Fixture, files: dict[str, str], later: dict[str, str], test_id: str) -> str:
    """A second red in the fixture lane: ``files`` at its red commit, ``later`` committed after it."""
    red = fx.commit(files, "test: another red")
    fx.commit(later, "fix: after the red")
    fx.evidence(handoff_extra=f"| `{test_id}` | `{red}` | `x` |\n")
    fx.review()
    return red


CONST_RED = "EXPECTED = 2\n\n\ndef test_c():\n    assert 2 == EXPECTED\n"
FIXTURE_TEST = "def test_f(value):\n    assert value == 2\n"
FIXTURE_DEF = "import pytest\n\n\n@pytest.fixture\ndef value():\n    return {}\n"


def test_lane_gate_refuses_red_module_constant_changed_after_red_commit(tmp_path: Path) -> None:
    # coordinator ruling: a top-level name the red test references may not change after the red commit
    fx = _fixture(tmp_path, review=False)
    later = {"tests/test_const.py": CONST_RED.replace("EXPECTED = 2", "EXPECTED = 3")}
    _own_red(fx, {"tests/test_const.py": CONST_RED}, later, "tests/test_const.py::test_c")
    assert _refused(fx.evaluate(), "red tests/test_const.py::test_c: referenced name EXPECTED changed")


@pytest.mark.parametrize("where", ["tests/conftest.py", "tests/test_fix.py"])
def test_lane_gate_refuses_conftest_changed_after_red_commit(tmp_path: Path, where: str) -> None:
    # coordinator ruling: a fixture the red test requests may not change, in a conftest or in its own file
    fx = _fixture(tmp_path, review=False)
    before, after = FIXTURE_DEF.format(2), FIXTURE_DEF.format(3)
    own = where == "tests/test_fix.py"
    files = {"tests/test_fix.py": (before + "\n\n" if own else "") + FIXTURE_TEST}
    later = {"tests/test_fix.py": after + "\n\n" + FIXTURE_TEST} if own else {where: after}
    if not own:
        files[where] = before
    _own_red(fx, files, later, "tests/test_fix.py::test_f")
    assert _refused(fx.evaluate(), "red tests/test_fix.py::test_f: ")
    assert _refused(fx.evaluate(), "value changed")


@pytest.mark.parametrize(
    "addition",
    ["import os\n", "def helper():\n    return 1\n", "LIMIT = 3\n", "class Helper:\n    pass\n"],
)
def test_lane_gate_allows_added_imports_and_new_top_level_names(tmp_path: Path, addition: str) -> None:
    fx = _fixture(tmp_path, review=False)
    grown = "from src.widget import widget\n" + addition + "\n\n" + RED_TEST
    fx.commit({"tests/test_widget.py": grown}, "test: grow the red file")
    fx.review()
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_allows_conftest_edits_the_red_test_does_not_request(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({"tests/conftest.py": FIXTURE_DEF.format(1)}, "test: an unrelated fixture")
    fx.review()
    assert _refusals(fx.evaluate(allow_paths=("tests/conftest.py",))) == []  # tests/conftest.py is protected


def test_lane_gate_refuses_red_decorator_changed_after_red_commit(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    red = "import pytest\n\n\n@pytest.mark.parametrize('x', [1, 2])\ndef test_d(x):\n    assert x > 1\n"
    later = {"tests/test_dec.py": red.replace("[1, 2]", "[2]")}
    _own_red(fx, {"tests/test_dec.py": red}, later, "tests/test_dec.py::test_d")
    assert _refused(fx.evaluate(), "red tests/test_dec.py::test_d: test body changed after red commit")


def test_lane_gate_runs_gates_in_a_fresh_tree_at_head(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    (fx.worktree / "tests" / "conftest_untracked.py").write_text("x = 1\n", encoding="utf-8")
    seen: list[tuple[Path, str, bool]] = []
    synced: list[Path] = []

    def gate(name: str, command: Sequence[str], cwd: Path) -> tuple[int, str]:
        seen.append((cwd, _git(cwd, "rev-parse", "HEAD"), (cwd / "tests" / "conftest_untracked.py").exists()))
        return 0, "ok"

    def prepare(tree: Path) -> tuple[int, str]:
        synced.append(tree)
        return 0, "synced"

    opts = fx.options()
    result = lane_gate.evaluate(opts, run_gate=gate, run_pytest=fx.run_pytest, prepare_env=prepare)
    assert _refusals(result) == []
    assert {cwd for cwd, _head, _untracked in seen} == set(synced)
    assert synced[0] != fx.worktree
    assert {head for _cwd, head, _untracked in seen} == {fx.head}
    assert not any(untracked for _cwd, _head, untracked in seen)
    assert not synced[0].exists()


def test_lane_gate_refuses_when_the_fresh_environment_fails_to_sync(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    opts = fx.options()
    result = lane_gate.evaluate(opts, run_gate=fx.run_gate, run_pytest=fx.run_pytest, prepare_env=lambda t: (1, "no"))
    assert _refused(result, "environment sync failed")
    assert fx.gate_calls == []


# --- review round 1 minors --------------------------------------------------------------------------------------------


def test_lane_gate_accepts_review_with_short_head_sha(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.review(f"# Review: lane x @ {fx.head[:7]}\nReviewer: claude-reviewer\n\nVERDICT: APPROVE\n")
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_refuses_review_with_too_short_or_wrong_prefix(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.review(f"# Review @ {fx.head[:6]} and {fx.red[:9]}\nReviewer: claude-reviewer\n\nVERDICT: APPROVE\n")
    assert _refused(fx.evaluate(), "review.md: does not name the head SHA")


def test_lane_gate_refuses_failed_sha_log(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    _write(fx.integration, {f"{fx.folder}/gate/no-sqlalchemy.log": f"{fx.head}\n$ cmd\nexit 1\nboom\n"})
    assert _refused(fx.evaluate(), "gate/no-sqlalchemy.log does not record exit 0")


def test_lane_gate_refuses_handoff_without_implementer(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    handoff = (fx.worktree / fx.folder / "handoff.md").read_text(encoding="utf-8").replace("Implementer: codex-x\n", "")
    fx.commit({f"{fx.folder}/handoff.md": handoff}, "docs: drop implementer")
    fx.review()
    assert _refused(fx.evaluate(), "handoff.md: no 'Implementer: <id>' line")


def test_lane_gate_refuses_bare_na_checklist_item(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    rows = "".join(f"| {n} | item {n} | {'N/A' if n == 2 else 'N/A — r'} |\n" for n in range(1, 11))
    fx.commit({f"{fx.folder}/checklist.md": "| # | Item | Evidence |\n|---|---|---|\n" + rows}, "docs: checklist")
    fx.review()
    assert _refused(fx.evaluate(), "checklist.md: item 2 has N/A without a reason")


def test_lane_gate_refuses_leased_log_with_prefix_match_only(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, lane="A-postgresql")
    lines = [fx.head, *(f"tests/engine/test_pg.py::{name}_other PASSED" for name in LEASED_TESTS)]
    _write(fx.integration, {f"{fx.folder}/gate/leased-pg.log": "\n".join(lines) + "\n"})
    assert _refused(fx.evaluate(), "leased-pg")


# --- coverage for checks that had no test (review finding 6) ---------------------------------------------------------


def test_lane_gate_refuses_red_sha_that_is_not_an_ancestor_of_head(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    _write(fx.integration, {"other.txt": "x\n"})
    _git(fx.integration, "add", "other.txt")
    _git(fx.integration, "commit", "-q", "-m", "side commit")
    side = _git(fx.integration, "rev-parse", "HEAD")
    fx.evidence(handoff_extra=f"| `{TEST_ID}` | `{side}` | `x` |\n")
    fx.review()
    assert _refused(fx.evaluate(), f"red SHA {side} is not an ancestor of head")


def test_lane_gate_refuses_red_test_missing_at_head(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({"tests/test_widget.py": "from src.widget import widget\n"}, "test: drop the red")
    fx.review()
    assert _refused(fx.evaluate(), f"red {TEST_ID}: test missing at head")


def test_lane_gate_refuses_dirty_worktree(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    (fx.worktree / "src" / "widget.py").write_text("def widget():\n    return 9\n", encoding="utf-8")
    assert _refused(fx.evaluate(), "lane worktree has uncommitted changes")


def test_lane_gate_refuses_handoff_not_updated_by_the_lane(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    handoff = f"{fx.folder}/handoff.md"
    _merge_release(fx, {handoff: (fx.worktree / handoff).read_text(encoding="utf-8")})
    fx.head = _git(fx.worktree, "rev-parse", "HEAD")
    fx.review()
    assert _refused(fx.evaluate(), "handoff.md is not current")


def test_lane_gate_refuses_lane_f_rekey_that_raises_the_total(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, lane="F", review=False)
    fx.commit({"tests/complexity_baseline.json": json.dumps({"src/a2.py": 4, "src/b.py": 2}) + "\n"}, "refactor")
    fx.review()
    assert _refused(fx.evaluate(), "complexity baseline total rose")


def test_lane_gate_refuses_bare_id_when_one_parametrisation_passes_at_red(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "mixed-params"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: passed at red SHA")


def test_lane_gate_removes_the_replay_tree_when_pytest_raises(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)

    def boom(tree: Path, nodeids: Sequence[str], junit: Path) -> None:
        raise RuntimeError("replay crashed")

    options = fx.options()
    run_gate = fx.run_gate
    with pytest.raises(RuntimeError, match="replay crashed"):
        lane_gate.evaluate(options, run_gate=run_gate, run_pytest=boom)
    assert len(_git(fx.integration, "worktree", "list").splitlines()) == 2


# --- gate run on lane F, and review-gate round 2 minors -------------------------------------------------------------


@pytest.mark.parametrize(
    ("lane", "path"), [("test-fixture-x", "scripts/dev/tool.py"), ("F", "scripts/dev/lane_gate.py")]
)
def test_lane_gate_ignores_budget_names_outside_overhead_modules(tmp_path: Path, lane: str, path: str) -> None:
    fx = _fixture(tmp_path, lane=lane, review=False)
    fx.commit({path: "import re\n\nBUDGET_LINE = re.compile('BUDGET_MS = 0.2')\n"}, "feat: mention a budget name")
    fx.review()
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_refuses_new_definition_shadowing_a_requested_fixture(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    files = {"tests/conftest.py": FIXTURE_DEF.format(2), "tests/test_fix.py": FIXTURE_TEST}
    later = {"tests/test_fix.py": FIXTURE_DEF.format(3) + "\n\n" + FIXTURE_TEST}
    _own_red(fx, files, later, "tests/test_fix.py::test_f")
    assert _refused(fx.evaluate(), "red tests/test_fix.py::test_f: referenced name value changed")


# --- code-review xhigh round (priority A: valid lanes refused) --------------------------------------------------------


def test_lane_gate_accepts_assertion_from_a_shared_test_helper(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "helper-assert"
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_accepts_did_not_raise_from_the_test_file(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "did-not-raise"
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_still_refuses_pytest_fail_as_red(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "pytest-fail"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: Failed failure")


def test_lane_gate_reads_parked_disposition_with_code_span(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    rows = f"| ok | `{TEST_ID}` | `{fx.red}` | x | Fixed |\n"
    rows += "| later | `tests/test_widget.py::test_x` | | x | Parked: needs `F-rest` |\n"
    fx.commit({f"{fx.folder}/findings.md": FINDINGS_HEAD + rows}, "docs: findings")
    fx.review()
    assert _refusals(fx.evaluate()) == []


CLASS_RED = "class TestK:\n    LIMIT = 2\n\n    def test_k(self):\n        assert self.LIMIT == 2\n"


def test_lane_gate_allows_new_methods_in_the_red_test_class(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    grown = CLASS_RED + "\n    def test_more(self):\n        assert True\n"
    red = _own_red(fx, {"tests/test_k.py": CLASS_RED}, {"tests/test_k.py": grown}, "tests/test_k.py::TestK::test_k")
    fx.outcomes[red] = "rewritten"
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_refuses_class_attribute_the_red_method_uses(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    later = {"tests/test_k.py": CLASS_RED.replace("LIMIT = 2", "LIMIT = 3")}
    _own_red(fx, {"tests/test_k.py": CLASS_RED}, later, "tests/test_k.py::TestK::test_k")
    assert _refused(fx.evaluate(), "red tests/test_k.py::TestK::test_k: referenced name LIMIT changed")


def test_lane_gate_skips_gates_after_a_replay_refusal(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "pass"
    assert _refused(fx.evaluate(), "passed at red SHA")
    assert fx.gate_calls == []
    assert not (fx.integration / fx.folder / "gate" / "pytest.log").exists()


def test_lane_gate_main_resolves_the_integration_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fx = _fixture(tmp_path)
    seen: list[Path] = []

    def factory(integration: Path) -> object:
        seen.append(integration)
        return fx.run_pytest

    monkeypatch.setattr(lane_gate, "run_gate_command", fx.run_gate)
    monkeypatch.setattr(lane_gate, "run_pytest_in", factory)
    monkeypatch.chdir(tmp_path)
    assert lane_gate.main([fx.lane, "--worktree", str(fx.worktree), "--integration", "integration"]) == 0
    assert seen[0].is_absolute()


# --- code-review xhigh round (priority B: bypasses) -------------------------------------------------------------------


def test_lane_gate_refuses_sha_log_whose_last_line_is_not_exit_0(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    _write(fx.integration, {f"{fx.folder}/gate/lowest-direct.log": f"{fx.head}\n$ cmd\nexit 0\nboom\nexit 1\n"})
    assert _refused(fx.evaluate(), "gate/lowest-direct.log does not record exit 0")


def test_lane_gate_refuses_na_with_an_empty_reason(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    rows = "".join(f"| {n} | item {n} | {'N/A — ' if n == 2 else 'N/A — r'} |\n" for n in range(1, 11))
    fx.commit({f"{fx.folder}/checklist.md": "| # | Item | Evidence |\n|---|---|---|\n" + rows}, "docs: checklist")
    fx.review()
    assert _refused(fx.evaluate(), "checklist.md: item 2 has N/A without a reason")


def test_lane_gate_refuses_non_pytest_red_outside_a_manual_table(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.evidence(handoff_extra=f"| `test_models_hook_rejects_a_string` | `{fx.red}` | `x` |\n")
    fx.review()
    result = fx.evaluate(accept_unverified=True)
    assert _refused(result, "red test_models_hook_rejects_a_string: not a pytest node id")


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("tests/overhead.py", "def check_budget():\n    return None\n"),
        ("tests/fastapi/test_capture_overhead.py", OVERHEAD_MODULE.replace("0.1 < BUDGET_MS", "0.1 <= BUDGET_MS")),
    ],
)
def test_lane_gate_refuses_overhead_module_changes(tmp_path: Path, path: str, body: str) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({path: body}, "chore: touch overhead")
    fx.review()
    assert _refused(fx.evaluate(), path)


def test_lane_gate_allows_new_tests_in_an_overhead_module(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    grown = OVERHEAD_MODULE + "\n\ndef test_another_budget():\n    assert BUDGET_MS > 0\n"
    fx.commit({"tests/fastapi/test_capture_overhead.py": grown}, "test: another budget test")
    fx.review()
    assert _refusals(fx.evaluate()) == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("tests/test_code_shape.py", "MAX_LINES = 2000\n"),
        ("tests/conftest.py", "import pytest\n"),
        ("pyproject.toml", '[project]\nname = "x"\ndependencies = ["starlette"]\n\n[tool.ruff]\nline-length = 200\n'),
        ("pyproject.toml", '[project]\nname = "x"\ndependencies = ["starlette"]\n\n[tool.pytest.ini_options]\nx = 1\n'),
    ],
)
def test_lane_gate_refuses_gate_config_changes_unless_allowed(tmp_path: Path, path: str, body: str) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({path: body}, "chore: touch gate config")
    fx.review()
    assert _refused(fx.evaluate(), path)
    allowed = fx.evaluate(allow_paths=(path,))
    assert _refusals(allowed) == []
    assert any(path in note for note in allowed.notes)  # type: ignore[attr-defined]


def test_lane_gate_refuses_findings_without_a_disposition_table(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    table = f"| Finding | Test | Red SHA |\n|---|---|---|\n| f | `{TEST_ID}` | `{fx.red}` |\n"
    fx.commit({f"{fx.folder}/findings.md": table}, "docs: findings")
    fx.review()
    assert _refused(fx.evaluate(), "findings.md: no table with a Disposition column")


# --- red rule: an assertion counts only when its last frame is under tests/ (G1G2 audit review) -----------------------


def test_lane_gate_refuses_assert_raised_in_scripts(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "scripts-assert"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: AssertionError raised outside the test file, not under tests/")


def test_lane_gate_refuses_assert_raised_in_src_by_absolute_path(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "abs-src-assert"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: AssertionError raised outside the test file, not under tests/")


def test_lane_gate_accepts_helper_under_tests_by_absolute_path(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "abs-helper"
    assert _refusals(fx.evaluate()) == []


def test_lane_gate_refuses_failure_with_teardown_error(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "teardown"
    assert _refused(fx.evaluate(), f"red {TEST_ID}: error at red SHA")


def test_lane_gate_exposes_the_one_accept_rule() -> None:
    is_red = getattr(lane_gate, "is_red", None)
    assert callable(is_red), "lane_gate exposes no public is_red for red_check to share"
    assert is_red(("failure", "AssertionError")) is True
    assert is_red(("failure", "TypeError")) is False
    assert callable(getattr(lane_gate, "red_verdicts", None)), "lane_gate exposes no public red_verdicts"


def test_lane_gate_accepts_did_not_raise_from_a_helper_under_tests(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    fx.outcomes[fx.red] = "helper-did-not-raise"
    assert _refusals(fx.evaluate()) == []


# --- overhead module detection by AST (release gate false positive on this lane) --------------------------------------


@pytest.mark.parametrize(
    ("source", "counted"),
    [
        ('BODY = "tests/overhead.py:9: check_budget(name)"\n', False),  # (a) only inside a string literal
        ("from overhead import check_budget\n\n\ndef test_x():\n    check_budget('x', 1, 2, 'ms', 1)\n", True),  # (b)
        ("import overhead\n\n\ndef test_x():\n    overhead.check_budget('x', 1, 2, 'ms', 1)\n", True),  # (b) attribute
        ("BUDGET_NS = 50\n", True),  # (c)
        ("BUDGET_MS: float = 0.2\n", True),  # (c) annotated
        ("def test_x():\n    BUDGET_MS = 0.2\n    assert BUDGET_MS\n", True),  # (d) function-local: fail closed
        ("def check_budget():\n    pass\n", True),  # the module that defines the check
        ("BUDGET_MS = (\n", True),  # (e) unparsable: the text rule, fail closed
    ],
)
def test_overhead_module_is_decided_by_ast(source: str, counted: bool) -> None:
    assert lane_gate._is_overhead_module("tests/test_x.py", source) is counted, source


def test_lane_gate_allows_changes_to_a_module_that_mentions_check_budget_only_in_a_string(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    path = "tests/test_strings.py"
    fx.commit({path: 'BODY = "tests/overhead.py:9: check_budget("\n\n\ndef test_s():\n    assert BODY\n'}, "test: s")
    base = fx.head
    _git(fx.integration, "merge", "-q", "--ff-only", base)  # the module is on the integration branch: a "before"
    fx.commit({path: 'BODY = "tests/overhead.py:10: check_budget("\n\n\ndef test_s():\n    assert BODY\n'}, "test: s2")
    fx.review()
    assert not _refused(fx.evaluate(), "overhead budget module changed"), _refusals(fx.evaluate())


def test_check_budget_inside_a_string_is_not_an_overhead_module() -> None:
    source = "FAKE = '<failure>tests/overhead.py:9: check_budget(name)</failure>'\n"
    assert lane_gate._is_overhead_module("tests/test_x.py", source) is False, "a string made it an overhead module"


def test_function_local_budget_counts_as_an_overhead_module() -> None:
    source = "def test_x():\n    BUDGET_MS = 0.2\n    assert BUDGET_MS\n"
    assert lane_gate._is_overhead_module("tests/test_x.py", source) is True, "a function-local BUDGET was not counted"


def test_async_check_budget_definition_counts_as_an_overhead_module() -> None:
    source = "async def check_budget(name):\n    return None\n"
    assert lane_gate._is_overhead_module("tests/test_x.py", source) is True, "async def check_budget was not counted"


# --- 0.5.0: lane F5-gate (spec 2026-11-03 §4.0) -----------------------------------------------------------------------

SHA_LOG_NAMES = ("lowest-direct", "no-sqlalchemy")


def _evidence_for_release(fx: Fixture, release: str) -> str:
    """Copy the lane evidence to ``release``'s folder and write that release's review and SHA logs."""
    old, new = fx.folder, fx.folder.replace("/0.4.0/", f"/{release}/")
    names = ("handoff.md", "findings.md", "field-map.md", "checklist.md")
    fx.commit({f"{new}/{n}": (fx.worktree / old / n).read_text(encoding="utf-8") for n in names}, "docs: evidence")
    logs = {f"{new}/gate/{name}.log": f"{fx.head}\n$ cmd\nok\nexit 0\n" for name in SHA_LOG_NAMES}
    _write(fx.integration, {f"{new}/review.md": f"Reviewer: claude-reviewer\nHead: {fx.head}\n\nVERDICT: APPROVE\n"})
    _write(fx.integration, logs)
    return new


def test_lane_gate_release_is_a_parameter(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    assert _refused(fx.evaluate(release="0.5.0"), "missing evidence: handoff.md (at .superpowers/sdd/0.5.0/lanes/")
    new = _evidence_for_release(fx, "0.5.0")
    assert _refusals(fx.evaluate(release="0.5.0")) == []
    assert (fx.integration / new / "gate" / "pytest.log").is_file()


def test_lane_gate_refuses_unresolvable_release(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    _write(fx.integration, {".superpowers/sdd/0.5.0/lanes/other/review.md": "x\n"})  # two releases, as the real tree
    _git(fx.integration, "switch", "-q", "--detach")
    assert _refused(fx.evaluate(), "cannot resolve the release")
    _git(fx.integration, "branch", "-q", "-D", "release")  # refs/heads/release would block release/<x>
    _git(fx.integration, "switch", "-q", "-c", "release/0.4.0")
    assert not _refused(fx.evaluate(), "cannot resolve the release")


@pytest.mark.parametrize("name", ["review.md", "live-verify.md", "gate/pytest.log"])
def test_reviewer_owned_paths_follow_release(tmp_path: Path, name: str) -> None:
    fx = _fixture(tmp_path, review=False)
    path = f".superpowers/sdd/0.5.0/lanes/X/{name}"
    fx.commit({path: "VERDICT: APPROVE\n"}, "chore: touch a reviewer-owned path")
    fx.review()
    assert _refused(fx.evaluate(release="0.5.0"), f"reviewer-owned path changed: {path}")


PROTECTED_ALLOWED_05 = {
    "F": {"scripts/dev/lane_gate.py", "tests/engine/test_import_boundary.py", "uv.lock"},
    "F5a-harness": {"tests/conftest.py", "uv.lock", "tests/engine/test_import_boundary.py"},
    "F5b": {"tests/engine/test_import_boundary.py"},
    "U20-memory": {"uv.lock"},
    "W-workload": {"uv.lock"},
}


def _lane_fixture(tmp_path: Path, lane: str) -> Fixture:
    """A fixture lane in its own folder, so one test can compare lanes."""
    (tmp_path / lane).mkdir()
    return _fixture(tmp_path / lane, lane=lane, review=False)


@pytest.mark.parametrize(
    ("lane", "path"), [(lane, path) for lane, paths in PROTECTED_ALLOWED_05.items() for path in sorted(paths)]
)
def test_protected_allowed_per_lane(tmp_path: Path, lane: str, path: str) -> None:
    table = {name: set(paths) for name, paths in lane_gate.PROTECTED_ALLOWED.items()}
    assert table == PROTECTED_ALLOWED_05
    assert path in lane_gate.PROTECTED
    for who in (lane, "C-fastapi"):
        fx = _lane_fixture(tmp_path, who)
        fx.commit({path: "# changed by the lane\n"}, "chore: touch a protected file")
        fx.review()
        assert _refused(fx.evaluate(), f"protected path changed: {path}") is (who == "C-fastapi"), who


DEPENDENCY_PYPROJECT = (
    '[project]\nname = "x"\ndependencies = ["starlette"]\n\n[project.optional-dependencies]\ntest = ["pymysql"]\n'
)


def test_dependency_change_allowed_per_lane(tmp_path: Path) -> None:
    lanes = {
        "F5a-harness": True,
        "F": True,
        "U20-memory": True,
        "W-workload": True,
        "C-fastapi": False,
        "F5a-core": False,
    }
    for lane, allowed in lanes.items():
        fx = _lane_fixture(tmp_path, lane)
        fx.commit({"pyproject.toml": DEPENDENCY_PYPROJECT}, "build: pymysql for the tests")
        fx.review()
        assert _refused(fx.evaluate(), "dependency list changed: pyproject.toml") is not allowed, lane
        config = DEPENDENCY_PYPROJECT + "\n[tool.pytest.ini_options]\nx = 1\n"
        fx.commit({"pyproject.toml": config}, "chore: pytest config")
        fx.review()
        assert _refused(fx.evaluate(), "gate config changed: pyproject.toml [tool.pytest]"), lane


GETENV_SCAN = "src/sharpit/engine/collectors/config/getenv_scan.py"


def test_baseline_rekey_only_for_foundation_lanes() -> None:
    before = json.dumps({GETENV_SCAN: 4, "src/a.py": 3})
    rekeyed = json.dumps({GETENV_SCAN: 4, "src/sharpit/engine/advisors/scan.py": 3})
    raised = json.dumps({GETENV_SCAN: 4, "src/sharpit/engine/advisors/scan.py": 5})
    assert lane_gate._baseline_refusals("F5a-core", before, rekeyed) == []
    assert lane_gate._baseline_refusals("F5a-source", before, json.dumps({"src/a.py": 3})) == []
    for lane in ("F5a-core", "F5a-source"):
        assert lane_gate._baseline_refusals(lane, before, raised) == ["complexity baseline total rose: 7 -> 9"], lane
    assert lane_gate._baseline_refusals("C-fastapi", before, rekeyed) != []
    assert set(lane_gate.FOUNDATION) == {"F", "F5a-harness", "F5a-source", "F5a-core", "F5b"}


ADV = "tests/fastapi/test_database_advisor_leased.py"
LEASED_05 = {
    "A-postgresql": (("leased-pg.log", LEASED_TESTS),),  # 0.4.0's bare names, matched as `::<name>` as before
    "F5b": (
        (
            "leased-mysql.log",
            (
                "tests/fastapi/test_mysql_read_only_leased.py::test_mysql_read_only_wrapper_rejects_write",
                "tests/fastapi/test_mysql_read_only_leased.py::test_mysql_autocommit_engine_refused",
            ),
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
        ("leased-pg.log", (f"{ADV}::test_read_only_wrapper_rejects_write[postgresql]",)),
        ("leased-mysql.log", (f"{ADV}::test_read_only_wrapper_rejects_write[mysql]",)),
    ),
    "A-dbadv-2": (
        ("leased-pg.log", (f"{ADV}::test_pg_vendor_rules_against_server",)),
        ("leased-mysql.log", (f"{ADV}::test_mysql_vendor_rules_against_server",)),
    ),
}


def test_leased_check_uses_full_node_ids(tmp_path: Path) -> None:
    assert lane_gate.LEASED == LEASED_05
    fx = _fixture(tmp_path, lane="A-mysql")
    log = f"{fx.folder}/gate/leased-mysql.log"
    other = "tests/engine/test_sqla_read_only.py::test_read_only_wrapper_rejects_write PASSED"  # same name, other file
    full = "tests/fastapi/test_mysql_leased.py::test_full_read_against_mysql_84 PASSED"
    _write(fx.integration, {log: f"{fx.head}\n{other}\n{full}\n"})
    wanted = "tests/fastapi/test_mysql_leased.py::test_read_only_wrapper_rejects_write"
    assert _refused(fx.evaluate(), f"leased-mysql: {wanted} not PASSED")
    _write(fx.integration, {log: f"{fx.head}\n{wanted} PASSED\n{full}\n"})
    accepted = fx.evaluate()
    assert _refusals(accepted) == []
    assert list(accepted.unverified) == []  # type: ignore[attr-defined]


def _plan(fx: Fixture, index: str, plans: dict[str, str]) -> Path:
    """PLAN.md (its Lanes table) and the lane plan files, in the integration worktree; returns PLAN.md's path."""
    _write(
        fx.integration,
        {"plans/PLAN.md": f"# plan\n\n## Lanes\n\n{index}\n", **{f"plans/{n}": t for n, t in plans.items()}},
    )
    return fx.integration / "plans" / "PLAN.md"


LANES_TABLE = "| Lane | Plan file | Council | Class |\n|---|---|---|---|\n"
MULTI_PLAN = (
    "# Lanes x and y\n\n| | |\n|---|---|\n| **Council** | not required |\n\n## Must-cover\n\n"
    f"test-fixture-x: `{TEST_ID}`.\n\ntest-fixture-y: `{TEST_ID}`.\n\n## Tasks\n"
)
COUNCIL = (
    "# Council\n\nHead: {head}\n\nReviewer: claude (claude-opus-5-5): ran\nReviewer: codex (gpt-6-luna): ran\n"
    "Reviewer: agy (gemini-4-argon-high): ran\n\nVERDICT: APPROVE\n"
)


def test_council_required_read_per_lane_from_plan_table(tmp_path: Path) -> None:
    index = (
        LANES_TABLE
        + "| test-fixture-x | `multi.md` | required | c |\n| test-fixture-y | `multi.md` | not required | c |\n"
    )
    (tmp_path / "x").mkdir()
    fx = _fixture(tmp_path / "x")
    plan = _plan(fx, index, {"multi.md": MULTI_PLAN})
    assert _refused(fx.evaluate(plan_index=plan), "council.md")
    _write(fx.integration, {f"{fx.folder}/council.md": COUNCIL.format(head=fx.head)})  # the coordinator writes it
    assert _refusals(fx.evaluate(plan_index=plan)) == []
    (tmp_path / "y").mkdir()
    other = _fixture(tmp_path / "y", lane="test-fixture-y")
    assert _refusals(other.evaluate(plan_index=_plan(other, index, {"multi.md": MULTI_PLAN}))) == []
    unknown = _plan(other, LANES_TABLE + "| test-fixture-x | `multi.md` | required | c |\n", {"multi.md": MULTI_PLAN})
    assert _refused(other.evaluate(plan_index=unknown), "test-fixture-y is not in the Lanes table")


@pytest.mark.parametrize(
    "body",
    [
        "Models: claude opus, codex gpt-6-luna\nHead: {head}\n",  # no VERDICT line
        "Models: claude opus, codex gpt-6-luna\nHead: {head}\n\nVERDICT: BLOCK\n",  # a verdict that is not APPROVE
        "Models: claude opus, claude sonnet\nHead: {head}\n\nVERDICT: APPROVE\n",  # one model family
        "Models: claude opus, codex gpt-6-luna\nHead: 0000000\n\nVERDICT: APPROVE\n",  # not the head SHA
    ],
)
def test_lane_gate_refuses_shallow_council_file(tmp_path: Path, body: str) -> None:
    fx = _fixture(tmp_path, review=False)
    plan = _plan(fx, LANES_TABLE + "| test-fixture-x | `multi.md` | required | c |\n", {"multi.md": MULTI_PLAN})
    fx.commit({f"{fx.folder}/x.txt": "x\n"}, "docs: the head the council names")
    fx.commit({f"{fx.folder}/council.md": body.format(head=fx.head)}, "docs: council")
    fx.review()
    assert _refused(fx.evaluate(plan_index=plan), "council.md: ")


COVER = "tests/test_cover.py"
COVER_TESTS = (
    "def test_a():\n    assert True\n\n\ndef test_twin():\n    assert True\n\n\ndef test_skip():\n    assert True\n"
    "\n\nclass TestK:\n    def test_m(self):\n        assert True\n"
)
LEASED_MYSQL = "tests/fastapi/test_mysql_leased.py::test_read_only_wrapper_rejects_write"


def _cover_runner(fx: Fixture, at_head: dict[str, str]) -> object:
    """fx.run_pytest, except ``at_head`` decides chosen node ids at the head: ``failure`` or ``skip:<reason>``."""

    def run(tree: Path, nodeids: Sequence[str], junit: Path) -> None:
        if _git(tree, "rev-parse", "HEAD") != fx.head or not set(nodeids) & set(at_head):
            fx.run_pytest(tree, nodeids, junit)
            return
        fx.replays.append((fx.head, tuple(nodeids)))
        cases = []
        for nodeid in nodeids:
            module, *rest = nodeid.split("::")
            classname = ".".join([module.removesuffix(".py").replace("/", "."), *rest[:-1]])
            outcome = at_head.get(nodeid, "pass")
            body = ""
            if outcome == "failure":
                body = f'<failure message="assert 0">E\n{module}:2: AssertionError</failure>'
            elif outcome.startswith("skip:"):
                body = f'<skipped type="pytest.skip" message="{outcome[5:]}" />'
            cases.append(f'<testcase classname="{classname}" name="{rest[-1]}">{body}</testcase>')
        junit.write_text(f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>", encoding="utf-8")

    return run


def _cover_check(fx: Fixture, names: str, at_head: dict[str, str] | None = None, **overrides: object) -> object:
    index = LANES_TABLE + f"| {fx.lane} | `x.md` | not required | c |\n"
    plan = _plan(fx, index, {"x.md": f"# x\n\n## Must-cover\n\n{names}\n\n## Tasks\n"})
    opts = fx.options(plan_index=plan, **overrides)
    return lane_gate.evaluate(opts, run_gate=fx.run_gate, run_pytest=_cover_runner(fx, at_head or {}))


def test_must_cover_uses_full_node_ids_and_refuses_skips(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    fx = _fixture(tmp_path / "x", review=False)
    fx.commit({COVER: COVER_TESTS, "tests/test_twin.py": "def test_twin():\n    assert True\n"}, "test: cover")
    fx.review()
    assert _refused(_cover_check(fx, "`test_absent`"), "must-cover test_absent: not defined")
    assert _refused(_cover_check(fx, "`test_twin`"), "must-cover test_twin: ambiguous")
    assert _refused(_cover_check(fx, "`tests/test_gone.py::test_x`"), "must-cover tests/test_gone.py::test_x: not at")
    listed = f"`test_a`, `test_m` and `{TEST_ID}`"
    assert _refusals(_cover_check(fx, listed)) == []
    assert (fx.head, (f"{COVER}::test_a", f"{COVER}::TestK::test_m", TEST_ID)) in fx.replays
    failing = _cover_check(fx, listed, {f"{COVER}::test_a": "failure"})
    assert _refused(failing, f"must-cover {COVER}::test_a: failure at the lane head")
    skipped = _cover_check(fx, "`test_skip`", {f"{COVER}::test_skip": "skip:needs a server"})
    assert _refused(skipped, f"must-cover {COVER}::test_skip: skipped (needs a server)")
    golden_skip = {f"{COVER}::test_skip": "skip:post-scan golden absent (G0)"}
    unflagged = _cover_check(fx, "`test_skip`", golden_skip)
    assert _refused(unflagged, f"must-cover {COVER}::test_skip: skipped (post-scan golden absent (G0)) (pass --accept")
    golden = _cover_check(fx, "`test_skip`", golden_skip, accept_unverified=True)
    assert _refusals(golden) == []
    assert any(f"{COVER}::test_skip" in line for line in golden.unverified)  # type: ignore[attr-defined]
    (tmp_path / "m").mkdir()
    leased = _fixture(tmp_path / "m", lane="A-mysql", review=False)
    leased.commit({LEASED_MYSQL.split("::")[0]: "def test_read_only_wrapper_rejects_write():\n    assert 1\n"}, "test")
    leased.review()
    run = _cover_check(
        leased, "`test_read_only_wrapper_rejects_write`", {LEASED_MYSQL: "skip:no server"}, accept_unverified=True
    )
    assert _refusals(run) == []


FINDINGS_05 = (
    "| finding | test (node id) | red SHA | red output (last assertion line) | disposition |\n|---|---|---|---|---|\n"
)


def test_findings_accept_pin_and_na_rows() -> None:
    rows = (
        f"| a | `{TEST_ID}` | `abc1234` | `assert 1 == 2` | fixed |\n"
        "| b | `tests/test_w.py::test_pin` | | | pin: reverted widget() to 1, failed on assert widget() == 2 |\n"
        "| c | `tests/test_w.py::test_p2` | `abc1234` | | pin: reverted the guard, failed on assert refused |\n"
        "| d | | | | N/A — deletion |\n"
        "| e | | | | parked: needs the owner |\n"
    )
    assert lane_gate._findings_refusals(FINDINGS_05 + rows) == []
    reds, problems = lane_gate.red_tests({"findings.md": FINDINGS_05 + rows})
    assert problems == []
    assert [red.test for red in reds] == [TEST_ID]  # pin and N/A rows are never replayed
    for bad in ("pin", "pin:", "pin: ", "N/A", "N/A —", "n/a: "):
        row = f"| x | `tests/test_w.py::test_x` | | | {bad} |\n"
        assert lane_gate._findings_refusals(FINDINGS_05 + row) != [], bad


PROTECTIONS = [
    ("protected", {"uv.lock": "lock2\n"}, "protected path changed: uv.lock"),
    ("protected", {"tests/conftest.py": "import pytest\n"}, "protected path changed: tests/conftest.py"),
    ("protected", {"sonar-baseline.txt": "8\n"}, "protected path changed: sonar-baseline.txt"),
    ("budget", {"tests/fastapi/test_capture_overhead.py": "BUDGET_MS = 0.4\n"}, "overhead budget module changed"),
    ("baseline", {"tests/complexity_baseline.json": '{"src/a.py": 4, "src/b.py": 2}\n'}, "complexity baseline raised"),
    ("dependency", {"pyproject.toml": DEPENDENCY_PYPROJECT}, "dependency list changed"),
    ("reviewer", {".superpowers/sdd/0.4.0/lanes/X/review.md": "x\n"}, "reviewer-owned path changed"),
    ("crash red", {}, f"red {TEST_ID}: TypeError failure"),
    ("passing red", {}, f"red {TEST_ID}: passed at red SHA"),
    ("verdict", {}, "review.md: last line is not VERDICT: APPROVE"),
]


@pytest.mark.parametrize(("kind", "files", "needle"), PROTECTIONS)
def test_existing_protections_still_refuse(tmp_path: Path, kind: str, files: dict[str, str], needle: str) -> None:
    # mutation guard (spec §4.0): with every 0.5.0 option in play, today's refusals still fire
    fx = _fixture(tmp_path, lane="C-fastapi", review=False)
    if files:
        fx.commit(files, "chore: a change the gate must refuse")
    fx.review(f"Reviewer: r\nHead: {fx.head}\n" if kind == "verdict" else None)
    fx.outcomes[fx.red] = {"crash red": "typeerror", "passing red": "pass"}.get(kind, "failure")
    index = LANES_TABLE + "| C-fastapi | `x.md` | not required | c |\n"
    plan = _plan(fx, index, {"x.md": f"# x\n\n## Must-cover\n\n`{TEST_ID}`\n"})
    assert _refused(fx.evaluate(release="0.4.0", plan_index=plan), needle)


# --- 0.5.0: lane F5-gate, fix round 1 (the lane's council) ------------------------------------------------------------

REQUIRED_INDEX = LANES_TABLE + "| test-fixture-x | `multi.md` | required | c |\n"
RAN = (
    "Reviewer: claude (claude-opus-5-5): ran\nReviewer: codex (gpt-6-luna): ran\n"
    "Reviewer: agy (gemini-4-argon-high): ran\n"
)


def _council(fx: Fixture, body: str, head: str = "") -> None:
    """council.md where the coordinator writes it: the integration worktree (a reviewer-owned path)."""
    _write(fx.integration, {f"{fx.folder}/council.md": body.format(head=head or fx.head, ran=RAN)})


def test_council_md_in_the_lane_tree_is_refused(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    plan = _plan(fx, REQUIRED_INDEX, {"multi.md": MULTI_PLAN})
    fx.commit({f"{fx.folder}/council.md": f"Head: {fx.head}\n{RAN}\nVERDICT: APPROVE\n"}, "docs: council")
    fx.review()
    result = fx.evaluate(plan_index=plan)
    assert _refused(result, f"reviewer-owned path changed: {fx.folder}/council.md")
    assert _refused(result, "council.md: missing")


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ("Head: {head}\n{ran}\nVERDICT: APPROVE\n\n## Round 2\n\nVERDICT: BLOCK\n", "the final VERDICT"),
        ("Head: {head}\n{ran}\nVERDICT: APPROVE WITH CHANGES\n", "the final VERDICT"),
        ("Head: {head}\n{ran}\n**VERDICT: APPROVE**\n", "the final VERDICT"),
        (
            "Head: {head}\nReviewer: claude (claude-opus-5-5): ran\nReviewer: codex (gpt-6-luna): not run (quota)\n"
            "Gemini and agy were asked too.\n\nVERDICT: APPROVE\n",
            "fewer than two model families ran",
        ),
        (
            "Head: {head}\nReviewer: claude (claude-opus-5-5): ran\nReviewer: agy (claude-opus-5-5-high): ran\n\n"
            "VERDICT: APPROVE\n",
            "fewer than two model families ran",
        ),
    ],
)
def test_council_reads_the_final_verdict_and_only_reviewers_that_ran(tmp_path: Path, body: str, needle: str) -> None:
    fx = _fixture(tmp_path)
    plan = _plan(fx, REQUIRED_INDEX, {"multi.md": MULTI_PLAN})
    _council(fx, body)
    assert _refused(fx.evaluate(plan_index=plan), f"council.md: {needle}")


@pytest.mark.parametrize(
    "body",
    [
        "Head: {head}\n{ran}\nVERDICT: APPROVE WITH CHANGES\n\n## Round 2\n\nVERDICT: APPROVE\n",
        "Head: {head}\n{ran}\nVERDICT: APPROVE WITH NITS\n",
        "Head: {head}\nReviewer: claude (claude-opus-5-5): ran\nReviewer: agy (gpt-oss-120b-medium): ran, BLOCK\n"
        "Reviewer: codex (gpt-6-luna): not run\n\nVERDICT: APPROVE\n",
    ],
)
def test_council_accepts_a_later_approve_round_and_nits(tmp_path: Path, body: str) -> None:
    fx = _fixture(tmp_path)
    plan = _plan(fx, REQUIRED_INDEX, {"multi.md": MULTI_PLAN})
    _council(fx, body)
    assert _refusals(fx.evaluate(plan_index=plan)) == []


@pytest.mark.parametrize("cell", ["**required**", "yes", "", "required-ish"])
def test_council_cell_must_be_required_not_required_or_a_dash(tmp_path: Path, cell: str) -> None:
    fx = _fixture(tmp_path)
    plan = _plan(fx, LANES_TABLE + f"| test-fixture-x | `multi.md` | {cell} | c |\n", {"multi.md": MULTI_PLAN})
    assert _refused(fx.evaluate(plan_index=plan), "Council cell")


def test_golden_skip_of_a_must_cover_test_needs_accept_unverified(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    fx.commit({COVER: COVER_TESTS}, "test: cover")
    fx.review()
    golden = {f"{COVER}::test_skip": "skip:post-scan golden absent (G0)"}
    needle = f"must-cover {COVER}::test_skip: skipped (post-scan golden absent (G0)) (pass --accept-unverified"
    assert _refused(_cover_check(fx, "`test_skip`", golden), needle)
    accepted = _cover_check(fx, "`test_skip`", golden, accept_unverified=True)
    assert _refusals(accepted) == []
    assert any(f"{COVER}::test_skip" in line for line in accepted.unverified)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "path", ["docs/superpowers/plans/2026-11-03-sharpit-0.5.0/PLAN.md", "Docs/Superpowers/Plans/x.md", "plans/x.md"]
)
def test_plan_files_are_protected_in_every_lane_diff(tmp_path: Path, path: str) -> None:
    fx = _fixture(tmp_path, lane="C-fastapi", review=False)
    fx.commit({path: "| Lane | Plan file | Council |\n"}, "docs: rewrite the plan")
    fx.review()
    index = LANES_TABLE + "| C-fastapi | `x.md` | not required | c |\n"
    plan = _plan(fx, index, {"x.md": f"# x\n\n## Must-cover\n\n`{TEST_ID}`\n"})
    assert _refused(fx.evaluate(plan_index=plan), f"plan file changed: {path}")


def test_plan_index_and_plan_must_be_in_the_integration_worktree(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    plan_text = f"# x\n\n## Must-cover\n\n`{TEST_ID}`\n"
    index = _plan(fx, LANES_TABLE + "| test-fixture-x | `x.md` | not required | c |\n", {"x.md": plan_text})
    assert _refusals(fx.evaluate(plan_index=index)) == []
    for outside in (tmp_path / "elsewhere", fx.worktree / "plans"):
        _write(outside, {"PLAN.md": index.read_text(encoding="utf-8"), "x.md": plan_text})
        assert _refused(fx.evaluate(plan_index=outside / "PLAN.md"), "PLAN.md must be in the integration worktree")
        assert _refused(fx.evaluate(plan_index=index, plan=outside / "x.md"), "must be in the integration worktree")


F5B_LEASED = (
    "tests/fastapi/test_mysql_read_only_leased.py::test_mysql_read_only_wrapper_rejects_write",
    "tests/fastapi/test_mysql_read_only_leased.py::test_mysql_autocommit_engine_refused",
)


def test_f5b_leased_log_needs_both_leased_tests(tmp_path: Path) -> None:
    assert lane_gate.LEASED["F5b"] == (("leased-mysql.log", F5B_LEASED),)
    fx = _fixture(tmp_path, lane="F5b")
    log = f"{fx.folder}/gate/leased-mysql.log"
    _write(fx.integration, {log: f"{fx.head}\n{F5B_LEASED[0]} PASSED\n"})
    assert _refused(fx.evaluate(), f"leased-mysql: {F5B_LEASED[1]} not PASSED")
    _write(fx.integration, {log: f"{fx.head}\n{F5B_LEASED[0]} PASSED\n{F5B_LEASED[1]} PASSED\n"})
    assert _refusals(fx.evaluate()) == []


SCOPED_PYPROJECTS = (
    '[project]\nname = "x"\ndependencies = ["starlette", "requests"]\n',  # runtime
    '[project]\nname = "x"\ndependencies = ["starlette"]\n\n[build-system]\nrequires = ["hatchling"]\n',  # build
    '[project]\nname = "x"\ndependencies = ["starlette"]\n\n[project.optional-dependencies]\nfastapi = ["fastapi"]\n',
)


def test_dependency_lanes_change_only_the_test_extra(tmp_path: Path) -> None:
    for lane, allowed in {"F5a-harness": False, "U20-memory": False, "W-workload": False, "F": True}.items():
        fx = _lane_fixture(tmp_path, lane)
        for pyproject in SCOPED_PYPROJECTS:
            fx.commit({"pyproject.toml": pyproject}, "build: a dependency outside the test extra")
            fx.review()
            refused = _refused(fx.evaluate(), "dependency list changed: pyproject.toml")
            assert refused is not allowed, f"{lane}: {pyproject}"


def test_pin_and_na_rows_skip_reds_only_in_findings_md() -> None:
    table = "| Test id | Red SHA | Disposition |\n|---|---|---|\n| `tests/test_w.py::test_pin` | | pin: reverted x |\n"
    _reds, problems = lane_gate.red_tests({"handoff.md": table})
    assert problems == ["handoff.md: red table row for tests/test_w.py::test_pin has no Red SHA"]
    row = "| x | | | | pin: reverted widget() to 1, failed on assert widget() == 2 |\n"
    assert lane_gate._findings_refusals(FINDINGS_05 + row) != []  # a pin row names the test it pins


@pytest.mark.parametrize("release", ["../0.4.0", "..", "0.4.0/../x", ""])
def test_release_name_is_validated(tmp_path: Path, release: str) -> None:
    fx = _fixture(tmp_path)
    assert _refused(fx.evaluate(release=release), "invalid release name")


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        ("Tests/conftest.py", "protected path changed"),
        ("UV.lock", "protected path changed"),
        (".superpowers/sdd/0.5.0/lanes/X/Review.md", "reviewer-owned path changed"),
    ],
)
def test_protected_and_reviewer_owned_paths_compare_case_insensitively(tmp_path: Path, path: str, needle: str) -> None:
    fx = _fixture(tmp_path, lane="C-fastapi")
    assert lane_gate._path_refusals(fx.options(release="0.4.0"), fx.head, path) == [f"{needle}: {path}"]


# council finding 7: one test per rule that survived the mutation run (each killed in a scratch copy, findings.md)


def test_council_head_must_be_followed_only_by_lane_evidence(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    code = fx.head  # the evidence commit: only the lane folder changes after it
    fx.commit({f"{fx.folder}/notes.md": "x\n"}, "docs: more evidence")
    fx.review()
    plan = _plan(fx, REQUIRED_INDEX, {"multi.md": MULTI_PLAN})
    _council(fx, "Head: {head}\n{ran}\nVERDICT: APPROVE\n", head=code)
    assert _refusals(fx.evaluate(plan_index=plan)) == []
    _council(fx, "Head: {head}\n{ran}\nVERDICT: APPROVE\n", head=fx.red)  # src/widget.py changed after it
    assert _refused(fx.evaluate(plan_index=plan), "council.md: does not name the head SHA")


@pytest.mark.parametrize("plan_text", ["# x\n\n## Tasks\n\n`test_widget`\n", "# x\n\n## Must-cover\n\nnone yet\n"])
def test_lane_plan_without_must_cover_tests_is_refused(tmp_path: Path, plan_text: str) -> None:
    fx = _fixture(tmp_path)
    plan = _plan(fx, LANES_TABLE + "| test-fixture-x | `x.md` | not required | c |\n", {"x.md": plan_text})
    assert _refused(fx.evaluate(plan_index=plan), "x.md: no ## Must-cover tests for lane test-fixture-x")


def test_bare_must_cover_name_resolves_only_in_the_lane_diff(tmp_path: Path) -> None:
    fx = _fixture(tmp_path, review=False)
    _merge_release(fx, {"tests/test_old.py": "def test_old():\n    assert 1\n"})  # at the head, not in the lane diff
    fx.head = _git(fx.worktree, "rev-parse", "HEAD")
    fx.review()
    assert _refusals(_cover_check(fx, "`test_widget`")) == []
    assert _refused(_cover_check(fx, "`test_old`"), "must-cover test_old: not defined in a test file of the lane diff")


def test_multi_lane_plan_counts_only_the_lanes_own_paragraphs(tmp_path: Path) -> None:
    lanes = {"test-fixture-x", "test-fixture-y"}
    text = f"# x\n\n## Must-cover\n\ntest-fixture-x: `{TEST_ID}`.\n\ntest-fixture-y: `test_absent`.\n\n## Tasks\n"
    assert lane_gate.must_cover_names(text, "test-fixture-x", lanes) == [TEST_ID]
    fx = _fixture(tmp_path)
    index = LANES_TABLE + "| test-fixture-x | `x.md` | not required | c |\n| test-fixture-y | `x.md` | not required | c |\n"
    assert _refusals(fx.evaluate(plan_index=_plan(fx, index, {"x.md": text}))) == []


@pytest.mark.parametrize("count", [0, 2])
def test_main_refuses_a_real_lane_without_a_single_plan_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], count: int
) -> None:
    fx = _fixture(tmp_path, lane="C-fastapi")
    monkeypatch.setattr(lane_gate, "run_gate_command", fx.run_gate)
    monkeypatch.setattr(lane_gate, "run_pytest_in", lambda integration: fx.run_pytest)
    for n in range(count):
        _write(fx.integration, {f"docs/superpowers/plans/2026-0{n + 1}-01-sharpit-0.4.0/PLAN.md": "# plan\n"})
    argv = [fx.lane, "--release", "0.4.0", "--worktree", str(fx.worktree), "--integration", str(fx.integration)]
    assert lane_gate.main(argv) == 1
    assert "REFUSED: no single PLAN.md for release 0.4.0" in capsys.readouterr().out
