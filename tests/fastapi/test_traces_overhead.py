"""Traces overhead budget: the span processor adds at most 20 µs per ended span (lane A-traces, Task 3).

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from tests.overhead import check_budget, paired

from sharpit.engine import otel
from sharpit.engine.capture.traces import SpanBuffer
from sharpit.engine.masking import Exposure, Masker

BUDGET_NS = 20_000
ROUNDS, PER_ROUND = 45, 2_000
SPAN = SimpleNamespace(name="GET /", attributes={"http.route": "/"})


def _round(processor: otel.SharpitSpanProcessor) -> int:
    started = time.perf_counter_ns()
    for _ in range(PER_ROUND):
        processor.on_end(SPAN)
    return (time.perf_counter_ns() - started) // PER_ROUND


def test_on_end_overhead_budget():
    buffer = SpanBuffer(Masker(Exposure.MASKED, True), capacity=1000)
    idle, armed = otel.SharpitSpanProcessor(), otel.SharpitSpanProcessor()
    armed.sinks = (buffer,)
    result = paired(lambda: _round(idle), lambda: _round(armed), ROUNDS)
    assert len(buffer._spans) == 1000  # pyright: ignore[reportPrivateUsage] - every span reached the bounded buffer
    check_budget("span processor per ended span", result, BUDGET_NS, "µs", 1000)
