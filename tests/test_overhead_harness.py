"""The overhead harness must measure capture, not the machine.

A fake machine stands in for the clock, so each case is exact: capture really costs ``TRUE`` per operation, and the
machine adds noise in a known pattern. A correct harness reports ``TRUE`` whatever the pattern.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.overhead import Paired, check_budget, paired

OFF, TRUE, NOISE, ROUNDS = 100.0, 10.0, 50.0, 6


def machine(noise: Callable[[int], float]) -> tuple[Callable[[], float], Callable[[], float]]:
    """``noise(call)`` is what the machine adds to the n-th round run, whichever side it belongs to."""
    calls = 0

    def run(cost: float) -> float:
        nonlocal calls
        calls += 1
        return cost + noise(calls)

    return (lambda: run(OFF)), (lambda: run(OFF + TRUE))


def test_a_machine_that_slows_down_midway_is_not_counted_as_overhead():
    """CI runners slow down for seconds at a time. Timing all "off" rounds, then all "on" rounds, put the whole
    slowdown on the "on" side: this case reported 60 per operation for a true cost of 10."""
    off, on = machine(lambda call: NOISE if call > ROUNDS else 0.0)
    assert paired(off, on, ROUNDS).overhead == TRUE


def test_a_slow_first_round_of_each_pair_does_not_hide_overhead():
    """Whatever runs first after a switch can pay for a cold cache. Always running "off" first would charge that to
    "off" and hide a real cost: this case would report -40 for a true cost of 10."""
    off, on = machine(lambda call: NOISE if call % 2 else 0.0)
    assert paired(off, on, ROUNDS).overhead == TRUE


# check_budget on hand-built results: off min 100 and on min 100 + X, so the overhead is exactly X; noise is 10 on both.
BUDGET = 10.0
SUSPECT = "suspect a busy machine"


def result(overhead: float) -> Paired:
    return Paired(off=[100.0, 110.0, 120.0], on=[100.0 + overhead, 110.0 + overhead, 120.0 + overhead])


@pytest.fixture(autouse=True)
def isolate_overhead_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHARPIT_OVERHEAD_LOG", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    log, summary = tmp_path / "log.jsonl", tmp_path / "summary.md"
    monkeypatch.setenv("SHARPIT_OVERHEAD_LOG", str(log))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    return log, summary


def test_a_result_within_budget_passes_and_leaves_one_record(records: tuple[Path, Path]):
    log, summary = records
    check_budget("hook", result(5.0), BUDGET, "us", 1.0)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "name": "hook",
        "verdict": "ok",
        "budget": BUDGET,
        "overhead": 5.0,
        "noise": 10.0,
        "off": [100.0, 110.0, 120.0],
        "on": [105.0, 115.0, 125.0],
        "unit": "us",
        "scale": 1.0,
    }
    rows = summary.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert "| ok |" in rows[0]


def test_a_result_over_budget_fails_but_still_leaves_its_record(records: tuple[Path, Path]):
    log, summary = records
    measured = result(25.0)
    with pytest.raises(AssertionError):
        check_budget("hook", measured, BUDGET, "us", 1.0)
    assert log.exists(), "a failed budget check wrote no log line"  # an assertion, not a crash, when it breaks
    assert summary.exists(), "a failed budget check wrote no summary row"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["verdict"] == "OVER"
    rows = summary.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert "| OVER |" in rows[0]


@pytest.mark.parametrize(("overhead", "suspected"), [(15.0, True), (20.0, True), (21.0, False), (40.0, False)])
def test_a_busy_machine_is_suspected_only_when_the_overshoot_is_within_the_noise(overhead: float, suspected: bool):
    """Noise is 10 and the budget 10: an overshoot of 5 and exactly 10 are within it, 11 and 30 are not."""
    measured = result(overhead)
    with pytest.raises(AssertionError) as failure:
        check_budget("hook", measured, BUDGET, "us", 1.0)
    assert (SUSPECT in str(failure.value)) is suspected


def test_noise_is_taken_from_the_noisier_side():
    quiet, noisy = [100.0, 101.0, 102.0], [100.0, 110.0, 120.0]
    assert Paired(off=quiet, on=noisy).noise == 10.0
    assert Paired(off=noisy, on=quiet).noise == 10.0


# Many short rounds: each side's rounds spread widely, but the fastest round is the same in both halves of the run.
WIDE_BUT_STABLE = [100.0, 300.0, 100.0, 300.0, 100.0, 300.0]


def test_noise_is_small_when_the_minimum_is_stable_however_wide_the_rounds_spread():
    """Median minus min read 100 here: a spread of single rounds, not how far the minimum could move."""
    assert Paired(off=WIDE_BUT_STABLE, on=WIDE_BUT_STABLE).noise == 0.0


def test_noise_is_how_far_the_minimum_moves_when_the_machine_slows_for_half_the_run():
    """The second half ran 50 slower, so a minimum taken from either half alone would be 50 apart."""
    slowed = [100.0, 101.0, 100.0, 150.0, 151.0, 150.0]
    assert Paired(off=slowed, on=slowed).noise == 50.0


def test_a_real_regression_measured_in_many_short_rounds_is_not_blamed_on_the_machine():
    """The review of PR #56 found every injected regression printed "suspect a busy machine" (noise 124-274 us)."""
    measured = Paired(off=WIDE_BUT_STABLE, on=[v + 40.0 for v in WIDE_BUT_STABLE])
    with pytest.raises(AssertionError) as failure:
        check_budget("hook", measured, BUDGET, "us", 1.0)
    assert SUSPECT not in str(failure.value)


def test_a_single_round_has_no_noise_estimate():
    assert Paired(off=[100.0], on=[110.0]).noise == 0.0


def test_nothing_is_written_when_neither_variable_is_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("SHARPIT_OVERHEAD_LOG", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)
    check_budget("hook", result(5.0), BUDGET, "us", 1.0)
    measured = result(25.0)
    with pytest.raises(AssertionError):
        check_budget("hook", measured, BUDGET, "us", 1.0)
    assert list(tmp_path.iterdir()) == []


def test_harness_self_tests_leave_the_real_log_alone(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "overhead.jsonl"
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("SHARPIT_OVERHEAD_LOG", str(log))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    result = pytester.runpytest_subprocess(str(Path(__file__).resolve()), "-k", "not leave_the_real_log")
    assert result.ret == 0
    assert not log.exists()
    assert not summary.exists()


class _ActiveCoverage:
    """Stands in for the ``coverage`` module while a tracer is running."""

    class Coverage:
        @staticmethod
        def current() -> object:
            return object()


def test_timing_is_skipped_while_a_coverage_tracer_runs(monkeypatch: pytest.MonkeyPatch):
    # the coverage job traces every line, which distorts on-vs-off timing; the plain test jobs enforce the budget
    monkeypatch.setitem(__import__("sys").modules, "coverage", _ActiveCoverage)
    with pytest.raises(pytest.skip.Exception, match="coverage"):
        paired(lambda: 1.0, lambda: 1.0, rounds=1)


def _timing_modules() -> tuple[str, ...]:
    """tests/conftest.py's TIMING_MODULES, read from source: sys.modules["conftest"] may be a pytester fixture app's."""
    import ast

    tree = ast.parse((Path(__file__).parent / "conftest.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TIMING_MODULES" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("tests/conftest.py no longer defines TIMING_MODULES as a literal")


def test_every_budget_module_runs_last() -> None:
    # a budget timed mid-suite meets every xdist worker busy; tests/conftest.py orders TIMING_MODULES last
    timed = {
        p.name
        for p in Path(__file__).parent.rglob("test_*.py")
        if re.search(r"^from tests\.overhead import .*\bcheck_budget\b", p.read_text(encoding="utf-8"), re.MULTILINE)
    }
    assert "test_capture_overhead.py" in timed  # the scan sees a known budget module
    missing = timed - set(_timing_modules()) - {Path(__file__).name}  # this file times a fake clock
    assert not missing, sorted(missing)


def test_budget_order_check_survives_a_fixture_conftest(monkeypatch: pytest.MonkeyPatch) -> None:
    # pytester runs fixture apps in-process, and a fixture app's own conftest.py then owns sys.modules["conftest"]
    import types

    monkeypatch.setitem(__import__("sys").modules, "conftest", types.ModuleType("conftest"))
    try:
        test_every_budget_module_runs_last()
    except ImportError as error:
        raise AssertionError(f"the budget-order check re-imports conftest at run time: {error}") from error


def test_harness_never_imports_the_bare_conftest_module() -> None:
    # sys.modules["conftest"] is whichever conftest.py pytester loaded last in this worker, at collection or run time
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    bare = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "conftest"]
    assert bare == [], f"test_overhead_harness.py imports the bare 'conftest' module at lines {bare}"
