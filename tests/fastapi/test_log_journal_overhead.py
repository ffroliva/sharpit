"""W5a P-log overhead: what offering the ``log`` journal event adds to a WARN record the log handler sees.

The same handler with the journal set against the journal unset (the log tail line is built in both), the sides
alternating through tests/overhead.py. How to read a failure: docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import pytest
from tests.overhead import check_budget, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.adapter import SharpitHandle

BUDGET_NS = 20_000
ROUNDS, PER_ROUND = 45, 300


@pytest.fixture
def handle() -> Iterator[SharpitHandle]:
    installed = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False)
    yield installed
    installed.uninstall_capture()


def test_log_journal_event_overhead_budget(handle: SharpitHandle):
    capture = handle.context.capture
    assert capture.wiring is not None
    handler = capture.wiring.log_handler
    journal = capture.journal
    assert handler is not None
    assert journal is not None
    record = logging.LogRecord(
        "com.example.orders.OrderService", logging.WARNING, __file__, 1, "Payment for order %s retried", (42,), None
    )

    def run() -> int:
        started = time.perf_counter_ns()
        for _ in range(PER_ROUND):
            handler.handle(record)
        return (time.perf_counter_ns() - started) // PER_ROUND

    run()  # warm

    def on() -> int:
        handler.journal = journal
        return run()

    def off() -> int:
        handler.journal = None
        return run()

    try:
        result = paired(off, on, ROUNDS)
    finally:
        handler.journal = journal
    assert journal.status()["recorded"].get("log", 0) >= PER_ROUND, "the log event never ran: the number means nothing"
    check_budget("log journal event per WARN record", result, BUDGET_NS, "µs", 1000)
