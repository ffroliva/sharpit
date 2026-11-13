"""Runtime Insights K9: ``ai-usage-by-route`` and ``work-after-response`` over the journal.

The http source has no producer on this base, so the tests record it by widening ``PRODUCED_SOURCES``; the http record
shape is the contract in ``insights/requests.py``, for the W5a producer to meet. The ai events are what
``ai_journal_event`` writes for a span, never hand-built rows.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.ai.recognizer import ai_journal_event
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.service import InsightsService, insights_service
from sharpit.engine.collectors.insights.snapshot import project
from sharpit.engine.collectors.insights.text import unit
from sharpit.engine.masking import Exposure, Masker

MS = 1_000_000
KIND = "ai-usage-by-route"
ASSISTANT = "GET /api/assistant"
Row = dict[str, object]
Op = Callable[[int], Row]  # a GenAI span ended under the given trace id, as sharpit's AI producer journals it


def trace_id(trace: int | None) -> str | None:
    """The id the http producer writes: lower-case 32 hex (``capture/exchanges.trace_id``)."""
    return None if trace is None else format(trace, "032x")


@pytest.fixture(autouse=True)
def http_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"ai", "http"}))


def span(trace: int, attributes: dict[str, object], name: str = "chat") -> object:
    return SimpleNamespace(
        context=SimpleNamespace(trace_id=trace, span_id=7), kind=SimpleNamespace(name="INTERNAL"), name=name,
        start_time=0, end_time=40 * MS, status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET")),
        attributes=attributes,
    )  # fmt: skip


def chat(input_tokens: int | None, output_tokens: int | None, finish: str = "stop", **extra: object) -> Op:
    attributes: dict[str, object] = {
        "gen_ai.operation.name": "chat", "gen_ai.provider.name": "openai", "gen_ai.request.model": "gpt-4o",
        "gen_ai.response.finish_reasons": [finish],
    }  # fmt: skip
    if input_tokens is not None:
        attributes["gen_ai.usage.input_tokens"] = input_tokens
    if output_tokens is not None:
        attributes["gen_ai.usage.output_tokens"] = output_tokens
    return lambda trace: {**ai_journal_event(span(trace, attributes)), **extra}


def tool() -> Op:
    return lambda trace: ai_journal_event(span(trace, {"gen_ai.operation.name": "execute_tool"}, "execute_tool t"))


def in_request(request_id: str) -> RequestInfo:
    return RequestInfo(request_id, "ctx", "GET", "/x", None, 0, None)


class Run:
    def __init__(self, **kwargs: int) -> None:
        self.journal = RuntimeJournal(**kwargs)  # type: ignore[arg-type]
        self.requests = 0

    def request(self, route: str, trace: int | None, *operations: Op, stamp: bool = False) -> str:
        request_id = f"r{self.requests + 1}"
        self.requests += 1
        self.journal.offer({"source": "http", "requestId": request_id, "traceId": trace_id(trace), "route": route})
        for operation in operations:
            token = REQUEST.set(in_request(request_id)) if stamp else None  # the span ends inside the request
            try:
                self.journal.offer(operation(0xABC if trace is None else trace))
            finally:
                if token is not None:
                    REQUEST.reset(token)
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
        run.request("GET /api/messages", i + 1, chat(800, 30, "tool_calls"), chat(830, 40))
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
    run.request(ASSISTANT, 1, chat(1000, 100), tool(), chat(2500, 150), chat(4000, 4096, "length"))
    run.request(ASSISTANT, 2, chat(900, 80))
    run.request("GET /api/orders", 3)
    run.journal.offer(chat(10, 10)(999))  # a trace no retained request carries stays unlinked
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
    coverage = {c["source"]: c for c in run.report()["coverage"]}  # type: ignore[attr-defined]
    assert coverage["ai"]["byTraceId"] == 5  # BootUI AiUsageByRouteTests.java:96-106
    assert coverage["ai"]["unlinked"] == 1
    assert coverage["ai"]["byRequestId"] == 0
    assert "http" in coverage


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
    run.request(ASSISTANT, 1, chat(100, 10), chat(100, 10), chat(100, 10))  # seeded: three operations
    run.request("GET /api/quiet", 2, chat(100, 10))  # counterexample: one cheap call, below every floor
    run.request("GET /api/none", 3)  # counterexample: no AI work, no finding
    rows = {str(r["subject"]): r for r in run.rows()}
    assert set(rows) == {ASSISTANT, "GET /api/quiet"}
    assert rows[ASSISTANT]["status"] == "OBSERVED"
    assert rows["GET /api/quiet"]["status"] == "INSUFFICIENT"
    assert "Reported from 3 operations" in str(rows["GET /api/quiet"]["sentence"])


def test_a_single_call_above_the_token_threshold_is_enough_and_the_setting_is_read() -> None:
    run = Run()
    run.request(ASSISTANT, 1, chat(9000, 10))
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
    run.journal.offer(chat(100, 10)(1))
    check = run.check()
    assert check["status"] == "INSUFFICIENT"
    assert "Without the http source" in str(check["reason"])
    assert run.rows() == []


def test_ai_usage_by_route_text_uses_journal_fields_only() -> None:
    run = Run()
    canary = "CANARY-prompt-text-7f3a"
    run.request(ASSISTANT, 1, *(chat(100, 10, prompt=canary, completion=canary, spanId=canary) for _ in range(3)))
    rows = run.rows()
    assert len(rows) == 1
    assert canary not in json.dumps(run.report())
    assert canary not in json.dumps(InsightsService(run.journal).insight(str(rows[0]["id"])))


# ported: WorkAfterResponseTests.withoutTheAgentItDoesNotApply
def test_work_after_response_not_applicable_when_agent_executors_unproduced() -> None:
    run = Run()
    run.request("GET /seed/work-after-response", 1)
    check = run.check("work-after-response")
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == (
        "The runtime journal does not record the agent.executors source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."
    )
    assert all(o["kind"] != "work-after-response" for o in run.report()["observations"])  # type: ignore[attr-defined]


def test_ai_events_that_join_no_retained_request_are_counted_not_dropped() -> None:
    run = Run()
    for i in range(3):
        run.request(ASSISTANT, i + 1)  # retained requests, no AI of their own
    for _ in range(9):
        run.journal.offer(chat(9000, 10, "length")(777))  # nine calls of a trace no retained request carries
    check = run.check()
    assert "9 AI operations joined no retained request" in str(check["reason"])
    assert run.rows() == []


# ported: RuntimeInsightsService.visibleEntries (v2.3.0, l.815-823): an AI call whose owner is a left-out request is
# skipped without a count; only a call linked by trace whose own start is before the loss is counted (aiCallsLeftOut)
def test_an_ai_call_of_a_left_out_request_is_not_counted_as_joining_no_retained_request() -> None:
    run = Run(max_events=3)
    token = REQUEST.set(in_request("r1"))
    try:
        run.journal.offer(chat(1000, 10)(1))  # r1's own AI call: the ring evicts it, so r1 lost evidence
    finally:
        REQUEST.reset(token)
    run.request(ASSISTANT, 1, chat(1000, 10))  # r1's http event stays, with a trace-linked AI call
    run.request(ASSISTANT, 2)
    reason = str(run.check()["reason"])
    assert "joined no retained request" not in reason
    assert "started before events the journal evicted" in reason


def test_the_bootui_shaped_case_with_matching_trace_ids_is_observed() -> None:
    run = Run()
    run.request(ASSISTANT, 1, *(chat(9000, 10, "length") for _ in range(9)))
    rows = run.rows()
    assert [r["status"] for r in rows] == ["OBSERVED"]
    assert "joined no retained request" not in str(run.check()["reason"])


def test_a_request_id_that_names_no_retained_request_does_not_fall_back_to_the_trace() -> None:
    run = Run()
    run.request(ASSISTANT, 1)
    token = REQUEST.set(in_request("evicted"))  # BootUI InsightsSnapshot.java:205-209: the request id decides
    try:
        run.journal.offer(chat(9000, 10)(1))  # its trace names the retained request, its request id another
    finally:
        REQUEST.reset(token)
    assert run.rows() == []
    assert "1 AI operation joined no retained request" in str(run.check()["reason"])


def test_a_trace_linked_event_stamped_with_a_request_id_is_not_tier_trace() -> None:
    run = Run()
    run.request(ASSISTANT, 1, chat(9000, 10), stamp=True)
    assert [r["minimumTier"] for r in run.rows()] == ["REQUEST_ID"]


def test_requests_are_projected_once_per_snapshot_with_the_full_http_fields() -> None:
    run = Run()
    run.journal.offer({
        "source": "http", "requestId": "r1", "traceId": trace_id(1), "route": "GET /x", "method": "GET", "status": 200,
        "durationNanos": 5, "startedAt": 1000,
    })  # fmt: skip
    snapshot = project(run.journal)
    first = getattr(snapshot, "requests", None)
    assert first is not None
    assert snapshot.requests is first
    request = first[0]
    assert (request.method, request.status, request.duration_nanos, request.started_at) == ("GET", 200, 5, 1000)


@pytest.mark.parametrize("route", ["@Scheduled com.x.Job.run", "consume orders"])
def test_unit_has_no_java_route_prefixes_no_sharpit_producer_writes(route: str) -> None:
    assert unit(route) == "request"


def test_http_ids_withheld_by_metadata_only_exposure_are_not_a_clean_nothing_found() -> None:
    run = Run(masker=Masker(Exposure.METADATA_ONLY, True))
    run.request(ASSISTANT, 1, chat(100, 10), chat(100, 10), chat(100, 10))
    run.request(ASSISTANT, 2, chat(100, 10))
    check = run.check()
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == (
        "Request and trace ids are withheld at METADATA_ONLY exposure, so AI operations cannot be placed on a route "
        "(SHARPIT_EXPOSE_VALUES)."
    )
