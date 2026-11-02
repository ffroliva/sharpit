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

    with pytest.raises(RuntimeError, match="replay crashed"):
        lane_gate.evaluate(fx.options(), run_gate=fx.run_gate, run_pytest=boom)
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
        ('BODY = "E\ntests/overhead.py:9: check_budget(name)"\n', False),  # (a) only inside a string literal
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
