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
        logs = {f"{self.folder}/gate/{name}.log": f"{self.head}\nok\n" for name in ("lowest-direct", "no-sqlalchemy")}
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
            module, name = nodeid.split("::")
            classname = module.removesuffix(".py").replace("/", ".")
            body = {
                "pass": "",
                "failure": '<failure message="AssertionError: assert 1 == 2">trace</failure>',
                "typeerror": '<failure message="TypeError: bad">trace</failure>',
                # real pytest: a rewritten assert's message names no exception; --tb=long ends "<file>:<line>: <type>"
                "rewritten": '<failure message="assert 1 == 2">E   assert 1 == 2\nt.py:2: AssertionError</failure>',
                "rpcerror": '<failure message="pkg.RpcError: x">E   pkg.RpcError: x\nt.py:2: RpcError</failure>',
                "error": '<error message="failed on setup">trace</error>',
                "skip": '<skipped message="skip" />',
            }
            if outcome != "absent":
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
        "tests/fastapi/test_capture_overhead.py": "BUDGET_MS = 0.2\n",
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
    fx.evidence(handoff_extra=f"| `{vitest}` | `{fx.red}` | `expect(x)` |\n")
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
