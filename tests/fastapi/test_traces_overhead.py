"""Traces overhead budget: the span processor adds at most 20 µs per ended span (lane A-traces, Task 3).

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from types import SimpleNamespace

from fastapi import FastAPI

from tests.overhead import check_budget, paired

from sharpit import install
from sharpit.engine import otel
from sharpit.engine.capture.traces import SpanBuffer
from sharpit.engine.masking import Exposure, Masker
from sharpit.fastapi.capture import wiring_of

BUDGET_NS = 20_000
ROUNDS, PER_ROUND = 45, 2_000
SPAN = SimpleNamespace(name="GET /", attributes={"http.route": "/"})


def _round(processor: otel.SharpitSpanProcessor) -> int:
    started = time.perf_counter_ns()
    for _ in range(PER_ROUND):
        processor.on_end(SPAN)
    return (time.perf_counter_ns() - started) // PER_ROUND


def test_on_end_overhead_budget():
    buffer = SpanBuffer(Masker(Exposure.MASKED, True), application=lambda: None, capacity=1000)
    idle, armed = otel.SharpitSpanProcessor(), otel.SharpitSpanProcessor()
    armed.sinks = (buffer,)
    result = paired(lambda: _round(idle), lambda: _round(armed), ROUNDS)
    assert len(buffer._spans) == 1000  # pyright: ignore[reportPrivateUsage] - every span reached the bounded buffer
    check_budget("span processor per ended span", result, BUDGET_NS, "µs", 1000)


def test_suspended_on_end_overhead_budget():
    """Plan scenario 2: the traces hook suspended disarms its sink (the lane's remover); ``on_end`` stays in budget."""
    buffer = SpanBuffer(Masker(Exposure.MASKED, True), application=lambda: None, capacity=1000)
    idle, suspended = otel.SharpitSpanProcessor(), otel.SharpitSpanProcessor()
    handle = install(FastAPI(), enabled="ON", show_banner=False)
    wiring = wiring_of(handle.context)
    assert wiring is not None

    def arm() -> Callable[[], None]:
        suspended.sinks = (buffer,)
        return lambda: otel.disarm(buffer, suspended)

    wiring.add_lane(handle.context, "traces", arm)
    wiring.on_first_request(handle.context)  # arms the lane's sink
    assert suspended.sinks == (buffer,)
    next(h for h in handle.context.capture.hooks.hooks() if h.name == "traces").suspend()  # the registry hook
    assert suspended.sinks == ()
    result = paired(lambda: _round(idle), lambda: _round(suspended), ROUNDS)
    assert len(buffer._spans) == 0, "the suspended path recorded"  # pyright: ignore[reportPrivateUsage]
    check_budget("span processor per ended span, suspended", result, BUDGET_NS, "µs", 1000)
