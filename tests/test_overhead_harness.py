"""The overhead harness must measure capture, not the machine.

A fake machine stands in for the clock, so each case is exact: capture really costs ``TRUE`` per operation, and the
machine adds noise in a known pattern. A correct harness reports ``TRUE`` whatever the pattern.
"""

from __future__ import annotations

from collections.abc import Callable

from tests.overhead import paired

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
