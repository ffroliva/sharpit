"""Runtime Insights K9: ``ai-usage-by-route`` and ``work-after-response`` over the journal.

The http source has no producer on this base, so the tests record it by widening ``PRODUCED_SOURCES``; the http record
shape (``requestId``, ``traceId``, ``route``) is the one the kind reads, for the W5a producer to meet.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.service import InsightsService, insights_service

MS = 1_000_000
KIND = "ai-usage-by-route"
ASSISTANT = "GET /api/assistant"
Row = dict[str, object]


@pytest.fixture(autouse=True)
def http_recorded(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"ai", "http"}))
    yield


def chat(input_tokens: int | None, output_tokens: int | None, finish: str = "stop", **extra: object) -> Row:
    return {
        "source": "ai", "operation": "chat", "provider": "openai", "model": "gpt-4o", "inputTokens": input_tokens,
        "outputTokens": output_tokens, "finishReason": finish, "failed": False, "durationNanos": 40 * MS, **extra,
    }  # fmt: skip


def tool() -> Row:
    return {"source": "ai", "operation": "tool", "failed": False, "durationNanos": 40 * MS}


class Run:
    def __init__(self, **kwargs: int) -> None:
        self.journal = RuntimeJournal(**kwargs)  # type: ignore[arg-type]
        self.requests = 0

    def request(self, route: str, trace: str | None, *operations: Row, stamp: bool = False) -> str:
        request_id = f"r{self.requests + 1}"
        self.requests += 1
        self.journal.offer({"source": "http", "requestId": request_id, "traceId": trace, "route": route})
        for operation in operations:
            self.journal.offer({**operation, **({"requestId": request_id} if stamp else {"traceId": trace})})
        return request_id

    def report(self, ai_token_threshold: int = 8000) -> Row:
        return InsightsService(self.journal, ai_token_threshold=ai_token_threshold).report()

    def check(self, kind: str = KIND) -> Row:
        return next(c for c in self.report()["checks"] if c["kind"] == kind)  # type: ignore[attr-defined]

    def rows(self, ai_token_threshold: int = 8000) -> list[Row]:
        report = self.report(ai_token_threshold)
        return [o for o in report["observations"] if o["kind"] == KIND]  # type: ignore[attr-defined]


# ported: AiUsageByRouteTests.aToolRoundTripWhoseInputBarelyGrewIsNotCalledGrowth
def test_a_tool_round_trip_whose_input_barely_grew_is_not_called_growth() -> None:
    run = Run()
    for i in range(2):
        run.request("GET /api/messages", f"t{i}", chat(800, 30, "tool_calls"), chat(830, 40))
    rows = run.rows()
    assert len(rows) == 1
    row = rows[0]
    sentence = str(row["sentence"])
    assert "grew" not in sentence
    assert "1.0 times" not in sentence
    checks = row["whatToCheck"]
    assert not any("trim" in c for c in checks)  # type: ignore[attr-defined]
    assert "one tool call and its answer" in checks[0]  # type: ignore[index]


# ported: AiUsageByRouteTests.aiOperationsAreLinkedToTheirRequestByTraceIdWithAgentLoopsGrowthAndLengthLimitedStops
def test_ai_operations_are_linked_by_trace_id_with_agent_loops_growth_and_length_limited_stops() -> None:
    run = Run()
    run.request(ASSISTANT, "t1", chat(1000, 100), tool(), chat(2500, 150), chat(4000, 4096, "length"))
    run.request(ASSISTANT, "t2", chat(900, 80))
    run.request("GET /api/orders", "t3")
    run.journal.offer({**chat(10, 10), "traceId": "t-unknown"})  # a trace no retained request carries stays unlinked
    rows = run.rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "OBSERVED"
    assert row["minimumTier"] == "TRACE_ID"
    assert row["sentence"] == (
        "`GET /api/assistant` made 5 AI operations in 2 of 2 requests: 4 model calls, up to 3 in one request, a median "
        "40 ms each, 8400 input and 4426 output tokens (reported by 4 of 4 calls). Input tokens grew by half or more "
        "across successive model calls in 1 request, up to 4.0 times the first call's. "
        "1 call stopped at the length limit."
    )
    assert len(row["whatToCheck"]) == 3  # type: ignore[arg-type]
    assert "agent or tool loop" in row["whatToCheck"][0]  # type: ignore[index]
    assert row["exemplarRequestIds"][0] == "r1"  # type: ignore[index]
    assert (
        "5 operations of 5 came from GenAI spans, linked to their request by trace id and time; such an operation "
        "outside a traced request is not counted."
    ) in row["limitations"]  # type: ignore[operator]
    assert run.check()["eligibleRequests"] == 3


# ported: AiUsageByRouteTests.operationsTheAiFrameworkStampedWithTheirRequestAreLinkedByRequestIdWithoutATraceLimitation
def test_operations_stamped_with_their_request_are_linked_by_request_id_without_a_trace_limitation() -> None:
    run = Run()
    for _ in range(3):
        run.request(ASSISTANT, None, chat(100, 10), stamp=True)
    rows = run.rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "OBSERVED"
    assert row["minimumTier"] == "REQUEST_ID"
    assert not any("trace id" in limitation for limitation in row["limitations"])  # type: ignore[attr-defined]


# ported: AiUsageByRouteTests.withoutTracingAiUsageIsNotApplicableRatherThanNone
def test_without_tracing_ai_usage_is_not_applicable_rather_than_none() -> None:
    run = Run()
    run.request(ASSISTANT, None)
    check = run.check()
    assert check["status"] == "NOT_APPLICABLE"
    assert "Without tracing" in str(check["reason"])


def test_ai_usage_by_route_seeded_case_and_counterexample() -> None:
    run = Run()
    run.request(ASSISTANT, "t1", chat(100, 10), chat(100, 10), chat(100, 10))  # seeded: three operations
    run.request("GET /api/quiet", "t2", chat(100, 10))  # counterexample: one cheap call, below every floor
    run.request("GET /api/none", "t3")  # counterexample: no AI work, no finding
    rows = {str(r["subject"]): r for r in run.rows()}
    assert set(rows) == {ASSISTANT, "GET /api/quiet"}
    assert rows[ASSISTANT]["status"] == "OBSERVED"
    assert rows["GET /api/quiet"]["status"] == "INSUFFICIENT"
    assert "Reported from 3 operations" in str(rows["GET /api/quiet"]["sentence"])


def test_a_single_call_above_the_token_threshold_is_enough_and_the_setting_is_read() -> None:
    run = Run()
    run.request(ASSISTANT, "t1", chat(9000, 10))
    default, raised = run.rows(8000), run.rows(20_000)
    assert [r["status"] for r in default] == ["OBSERVED"]
    assert [r["status"] for r in raised] == ["INSUFFICIENT"]


def test_insights_service_passes_the_ai_token_threshold_setting() -> None:
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False, runtime_insights_ai_token_threshold=50
    )
    service = insights_service(handle.context)
    assert service.ai_token_threshold == 50


@pytest.mark.parametrize("invalid", [0, -5])
def test_an_invalid_ai_token_threshold_takes_the_default(invalid: int) -> None:
    assert InsightsService(None, ai_token_threshold=invalid).ai_token_threshold == 8000


def test_ai_usage_by_route_not_applicable_when_ai_unproduced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"http"}))
    check = Run().check()
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == "The runtime journal does not record the ai source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."


def test_ai_operations_without_the_http_source_say_they_cannot_be_placed_on_a_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"ai"}))
    run = Run()
    run.journal.offer(chat(100, 10, traceId="t1"))
    check = run.check()
    assert check["status"] == "INSUFFICIENT"
    assert "Without the http source" in str(check["reason"])
    assert run.rows() == []


def test_ai_usage_by_route_text_uses_journal_fields_only() -> None:
    run = Run()
    canary = "CANARY-prompt-text-7f3a"
    run.request(
        ASSISTANT, "t1", *(chat(100, 10, prompt=canary, completion=canary, spanId=canary) for _ in range(3))
    )
    rows = run.rows()
    assert len(rows) == 1
    assert canary not in json.dumps(run.report())
    assert canary not in json.dumps(InsightsService(run.journal).insight(str(rows[0]["id"])))


# ported: WorkAfterResponseTests.withoutTheAgentItDoesNotApply
def test_work_after_response_not_applicable_when_agent_executors_unproduced() -> None:
    run = Run()
    run.request("GET /seed/work-after-response", "t1")
    check = run.check("work-after-response")
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == (
        "The runtime journal does not record the agent.executors source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."
    )
    assert all(o["kind"] != "work-after-response" for o in run.report()["observations"])  # type: ignore[attr-defined]
