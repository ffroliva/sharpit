"""W5a P-log overhead: what offering the ``log`` journal event adds to a WARN record the log handler sees.

The same handler with the journal set against the journal unset (the log tail line is built in both), the sides
alternating through tests/overhead.py. One test for a template the handler has masked before (a cache hit), one for a
template it has not (a miss: more distinct templates than the cache holds, taken in turn). How to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator

import pytest
from tests.overhead import Paired, check_budget, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.adapter import SharpitHandle

# set from the paired runs (hit 13 to 44 µs, miss 76 to 103 µs; the numbers and the machine load are in
# docs/development/overhead-budgets.md): the miss at about 2x its largest run, the hit at 60 µs. A lost cache is guarded
# by test_log_journal_a_template_with_arguments_is_masked_once, not by these budgets. Never raised.
HIT_BUDGET_NS = 60_000
MISS_BUDGET_NS = 200_000
ROUNDS, PER_ROUND = 45, 300
DISTINCT = 1_024  # more than the handler's 256 cached templates: each record in turn is a miss
TEMPLATE = (
    "Order {tag}: payment for %s of customer %s retried after gateway returned a status %s"  # 84 characters, tag filled
)


@pytest.fixture
def handle() -> Iterator[SharpitHandle]:
    installed = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False)
    yield installed
    installed.uninstall_capture()


def _record(template: str) -> logging.LogRecord:
    return logging.LogRecord(
        "com.example.orders.OrderService", logging.WARNING, __file__, 1, template, (42, "c-7", 502), None
    )


def _measure(handle: SharpitHandle, records: list[logging.LogRecord]) -> tuple[Paired, int]:
    capture = handle.context.capture
    assert capture.wiring is not None
    handler = capture.wiring.log_handler
    journal = capture.journal
    assert handler is not None
    assert journal is not None
    turn = [0]

    def run() -> int:
        started = time.perf_counter_ns()
        for _ in range(PER_ROUND):
            turn[0] += 1
            handler.handle(records[turn[0] % len(records)])
        return (time.perf_counter_ns() - started) // PER_ROUND

    run()  # warm

    def side(on: bool) -> Callable[[], int]:
        def timed() -> int:
            handler.journal = journal if on else None
            return run()

        return timed

    try:
        result = paired(side(False), side(True), ROUNDS)
    finally:
        handler.journal = journal
    return result, journal.status()["recorded"].get("log", 0)


def test_log_journal_event_overhead_budget(handle: SharpitHandle):
    """A cache hit: the same template again and again (a call site that logs repeatedly)."""
    result, recorded = _measure(handle, [_record(TEMPLATE.format(tag="0000"))])
    assert recorded >= PER_ROUND, "the log event never ran: the number means nothing"
    check_budget("log journal event per WARN record, cached template", result, HIT_BUDGET_NS, "µs", 1000)


def test_log_journal_event_on_a_template_never_seen_overhead_budget(handle: SharpitHandle):
    """A cache miss: 1,024 distinct 84-character templates in turn, past the 256 the handler keeps."""
    records = [_record(TEMPLATE.format(tag=f"{number:04d}")) for number in range(DISTINCT)]
    assert {len(str(r.msg)) for r in records} == {84}
    result, recorded = _measure(handle, records)
    assert recorded >= PER_ROUND, "the log event never ran: the number means nothing"
    check_budget("log journal event per WARN record, template not cached", result, MISS_BUDGET_NS, "µs", 1000)
