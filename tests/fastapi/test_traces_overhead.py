"""Traces overhead budget: the span processor adds at most 20 µs per ended span (lane A-traces, Task 3).

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from tests.overhead import check_budget, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.capture.traces import SpanBuffer, span_buffer
from sharpit.engine.masking import Exposure, Masker
from sharpit.fastapi.capture import wiring_of

BUDGET_NS = 20_000
ROUNDS, PER_ROUND = 45, 2_000
SPAN = SimpleNamespace(name="GET /", attributes={"http.route": "/"})
AI_SPAN = SimpleNamespace(
    context=SimpleNamespace(trace_id=1, span_id=2),
    kind=SimpleNamespace(name="INTERNAL"),
    name="chat",
    start_time=60_000_000_000,
    end_time=61_000_000_000,
    status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET")),
    attributes={"gen_ai.operation.name": "chat", "gen_ai.provider.name": "openai"},
)
PLAIN_SPAN = SimpleNamespace(
    context=SimpleNamespace(trace_id=1, span_id=3),
    kind=SimpleNamespace(name="INTERNAL"),
    name="SELECT users",
    attributes={"db.statement": "SELECT 1", "db.name": "app"},
)


def _round(processor: otel.SharpitSpanProcessor) -> int:
    started = time.perf_counter_ns()
    for _ in range(PER_ROUND):
        processor.on_end(SPAN)
    return (time.perf_counter_ns() - started) // PER_ROUND


def _round_of(processor: otel.SharpitSpanProcessor, span: Any) -> int:
    started = time.perf_counter_ns()
    for _ in range(PER_ROUND):
        processor.on_end(span)
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


def _journal_buffer() -> tuple[SpanBuffer, RuntimeJournal]:
    handle = install(
        FastAPI(),
        enabled="ON",
        show_banner=False,
        config_scan=False,
        runtime_journal_sources=("ai",),
    )
    buffer = span_buffer(handle.context)
    journal = handle.context.capture.journal
    assert journal is not None
    return buffer, journal


def test_on_end_overhead_budget_with_ai_journal():
    buffer, journal = _journal_buffer()
    idle, armed = otel.SharpitSpanProcessor(), otel.SharpitSpanProcessor()
    armed.sinks = (buffer,)
    armed.on_end(AI_SPAN)
    assert len(journal.records("ai")) == 1
    result = paired(lambda: _round(idle), lambda: _round_of(armed, AI_SPAN), ROUNDS)
    check_budget("span processor per ended GenAI span with journal", result, BUDGET_NS, "µs", 1000)


def test_on_end_overhead_budget_non_ai_span_with_ai_journal():
    buffer, journal = _journal_buffer()
    idle, armed = otel.SharpitSpanProcessor(), otel.SharpitSpanProcessor()
    armed.sinks = (buffer,)
    armed.on_end(PLAIN_SPAN)
    assert buffer._spans[-1] is PLAIN_SPAN  # pyright: ignore[reportPrivateUsage]
    assert journal.records("ai") == ()
    result = paired(lambda: _round(idle), lambda: _round_of(armed, PLAIN_SPAN), ROUNDS)
    check_budget("span processor per ended non-GenAI span with journal", result, BUDGET_NS, "µs", 1000)
