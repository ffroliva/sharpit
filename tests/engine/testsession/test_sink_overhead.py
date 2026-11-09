"""Test-session sink overhead budget (lane P-sink-mask-memo, bench U7): ``on_sql`` on repeated statements.

A test suite runs the same few statements over and over; the sink must not re-mask the same normalised text each time.
Measured on the memo'd sink at about 11 µs per statement (un-memo'd about 50 µs; Windows 11, CPython 3.14); the budget
leaves headroom for slower CI runners. "off" is a no-op hook called the same way, so the overhead is ``on_sql`` itself.

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from tests.overhead import check_budget, paired

from engine.testsession.tsfakes import NODE, event
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.testsession.sink import TestSessionSink

BUDGET_NS = 30_000
ROUNDS, PER_ROUND = 60, 300
EVENTS = [
    event("SELECT pets.id, pets.name, pets.owner_id FROM pets WHERE pets.id = ?"),
    event("SELECT owners.id, owners.name FROM owners WHERE owners.id IN (?, ?, ?)"),
    event("UPDATE pets SET name = ? WHERE pets.id = ?"),
]


def _noop(sql: SqlEvent, test: tuple[str, int, str] | None) -> None:
    del sql, test


def test_sink_on_sql_repeated_statement_overhead_budget() -> None:
    sink = TestSessionSink("gw0")
    tag = (NODE, sink.begin_test(NODE), "call")

    def round_of(hook: Callable[[SqlEvent, tuple[str, int, str]], None]) -> float:
        started = time.perf_counter_ns()
        for i in range(PER_ROUND):
            hook(EVENTS[i % 3], tag)
        return (time.perf_counter_ns() - started) / PER_ROUND

    round_of(sink.on_sql)  # first sight of each statement is not the repeated cost
    result = paired(lambda: round_of(_noop), lambda: round_of(sink.on_sql), ROUNDS)
    assert sink.current_test is not None
    assert sink.current_test.phases["call"].queries == (ROUNDS + 1) * PER_ROUND
    check_budget("test-session sink on_sql per repeated statement", result, BUDGET_NS, "µs", 1000)
