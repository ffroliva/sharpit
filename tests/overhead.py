"""Paired on/off timing for the overhead budget tests: what capture adds, and how noisy the measurement was."""

from __future__ import annotations

import json
import os
import statistics
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Paired:
    off: list[float]
    on: list[float]

    @property
    def overhead(self) -> float:
        """Fastest "on" round minus fastest "off" round: contention only ever slows a round down."""
        return min(self.on) - min(self.off)

    @property
    def noise(self) -> float:
        """How far a typical round sits above the fastest, on the noisier side: what contention cost this run."""
        return max(statistics.median(side) - min(side) for side in (self.off, self.on))

    def report(self, unit: str, scale: float) -> str:
        def side(rounds: list[float]) -> str:
            low, mid, high = (v / scale for v in (min(rounds), statistics.median(rounds), max(rounds)))
            return f"min {low:.3f} median {mid:.3f} max {high:.3f}"

        return (
            f"overhead {self.overhead / scale:.3f} {unit}, noise {self.noise / scale:.3f} {unit}; "
            f"off {side(self.off)}; on {side(self.on)}"
        )


def check_budget(name: str, result: Paired, budget: float, unit: str, scale: float) -> None:
    """Assert ``result`` is within ``budget`` and leave a record either way.

    On CI every run appends a row to the job summary, so the overhead and the noise can be compared across runs. A
    failure whose noise is as large as the margin to the budget is the signature of a busy machine, not a slower hook:
    docs/development/overhead-budgets.md says how to tell the two apart.
    """
    verdict = "ok" if result.overhead <= budget else "OVER"
    if log := os.environ.get("SHARPIT_OVERHEAD_LOG"):  # scripts/dev/overhead_check.py reads this, one JSON per line
        record = {"name": name, "verdict": verdict, "budget": budget, "overhead": result.overhead}
        record |= {"noise": result.noise, "off": result.off, "on": result.on}
        with open(log, "a", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as out:
            out.write(
                f"| overhead budget | {name} | {verdict} | {result.overhead / scale:.3f} {unit} "
                f"| {budget / scale:.3f} {unit} | {result.noise / scale:.3f} {unit} |\n"
            )
    over = result.overhead - budget
    suspect = " The overshoot is within the noise: suspect a busy machine." if result.noise >= over else ""
    assert result.overhead <= budget, (
        f"{name}: {result.report(unit, scale)}; budget {budget / scale:.3f} {unit}.{suspect} "
        "Never raise the budget to pass: docs/development/overhead-budgets.md"
    )


def paired(off: Callable[[], float], on: Callable[[], float], rounds: int) -> Paired:
    """Time ``rounds`` rounds of each side; each callable runs one round and returns its time per operation.

    The sides alternate, so a machine that slows down for a while slows both alike, and the side that goes first
    swaps every round, so the cost of whatever runs first after a switch is not always charged to one side.
    """
    off_rounds: list[float] = []
    on_rounds: list[float] = []
    for i in range(rounds):
        if i % 2:
            on_rounds.append(on())
            off_rounds.append(off())
        else:
            off_rounds.append(off())
            on_rounds.append(on())
    return Paired(off_rounds, on_rounds)
