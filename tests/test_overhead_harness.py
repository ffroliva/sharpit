"""The overhead harness must measure capture, not the machine.

A fake machine stands in for the clock, so each case is exact: capture really costs ``TRUE`` per operation, and the
machine adds noise in a known pattern. A correct harness reports ``TRUE`` whatever the pattern.
"""

from __future__ import annotations

import json
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


def test_nothing_is_written_when_neither_variable_is_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("SHARPIT_OVERHEAD_LOG", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)
    check_budget("hook", result(5.0), BUDGET, "us", 1.0)
    measured = result(25.0)
    with pytest.raises(AssertionError):
        check_budget("hook", measured, BUDGET, "us", 1.0)
    assert list(tmp_path.iterdir()) == []
