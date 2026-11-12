"""``ai-usage-by-route``: BootUI ``E/insights/AiUsageByRoute.java:63-264``.

Deviations (proposed): an operation joins its request by request id or trace id only (sharpit's AI event carries no
start time for BootUI's time-window join); a call without ``durationNanos`` is left out of the median, which is then
not stated; the not-applicable reason names no Java framework.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, median, millis, unit

KIND = "ai-usage-by-route"
TITLE = "AI usage by route"
MINIMUM_TIER = "TRACE_ID"
READS: frozenset[str] = frozenset({"ai"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = True

MIN_OPERATIONS = 3
MIN_GROWTH = 1.5  # a tool round-trip resends the question with a short result: not growth
NOT_APPLICABLE = "Without tracing, or an AI framework reporting its calls, AI usage is unknown."
NO_ROUTE = (
    "Without the http source, which the runtime journal does not record, AI operations cannot be placed on a route."
)
COLUMNS = ["Request", "Operations", "Model calls", "Models", "Input tokens", "Output tokens"]
_Event = dict[str, object]


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def not_applicable(snapshot: Snapshot) -> str | None:
    requests = project_requests(snapshot)
    if not requests or any(r.trace_id for r in requests):
        return None
    stamped = any(e.get("requestId") or e.get("executionId") for e in snapshot.records.get("ai", ()))
    return None if stamped else NOT_APPLICABLE


@dataclass
class _Usage:
    threshold: int
    requests: list[Request] = field(default_factory=list[Request])
    rows: list[list[str]] = field(default_factory=list[list[str]])
    chats: list[int] = field(default_factory=list[int])
    calls: dict[str, int] = field(default_factory=dict[str, int])
    operations: int = 0
    model_calls: int = 0
    with_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    length_limited: int = 0
    over_threshold: int = 0
    failed: int = 0
    trace_linked: int = 0
    growing: int = 0
    largest_growth: float = 0.0
    most_calls: int = 0

    def add(self, request: Request, events: list[_Event]) -> None:
        self.requests.append(request)
        calls, totals = 0, [0, 0]
        models: list[str] = []
        inputs: list[int] = []
        for event in events:
            self.operations += 1
            self.trace_linked += not event.get("requestId") and not event.get("executionId")
            self.failed += event.get("failed") is True
            if event.get("operation") == "chat":
                calls += 1
                self._chat(event, models, inputs, totals)
        self.input_tokens, self.output_tokens = self.input_tokens + totals[0], self.output_tokens + totals[1]
        self.most_calls = max(self.most_calls, calls)
        self.calls[request.request_id] = calls
        if calls >= 2 and inputs and inputs[0] > 0 and inputs[-1] >= inputs[0] * MIN_GROWTH:
            self.growing += 1
            self.largest_growth = max(self.largest_growth, inputs[-1] / inputs[0])
        self.rows.append(
            [request.request_id, str(len(events)), str(calls), ", ".join(models), str(totals[0]), str(totals[1])]
        )

    def _chat(self, event: _Event, models: list[str], inputs: list[int], totals: list[int]) -> None:
        self.model_calls += 1
        duration = _count(event.get("durationNanos"))
        if duration is not None:
            self.chats.append(max(0, duration))
        model = event.get("model")
        if isinstance(model, str) and model not in models:
            models.append(model)
        tokens_in, tokens_out = _count(event.get("inputTokens")), _count(event.get("outputTokens"))
        self.with_tokens += tokens_in is not None or tokens_out is not None
        totals[0] += tokens_in or 0
        totals[1] += tokens_out or 0
        self.over_threshold += (tokens_in or 0) + (tokens_out or 0) > self.threshold
        reason = event.get("finishReason")
        self.length_limited += isinstance(reason, str) and reason.lower() in {"length", "max_tokens"}
        if tokens_in is not None:
            inputs.append(tokens_in)

    @property
    def tier(self) -> str:
        return "TRACE_ID" if self.trace_linked else "REQUEST_ID"

    @property
    def exemplars(self) -> list[str]:
        return [r for r, _ in sorted(self.calls.items(), key=lambda kv: -kv[1])[:3]]


def _sentence(route: str, usage: _Usage, eligible: int, sufficient: bool) -> str:
    text = (
        f"`{route}` made {counted(usage.operations, 'AI operation')} in {len(usage.requests)} of "
        f"{counted(eligible, unit(route))}"
    )
    if usage.model_calls:
        text += f": {counted(usage.model_calls, 'model call')}, up to {usage.most_calls} in one request"
        if usage.chats:
            text += f", a median {millis(median(usage.chats))} ms each"
        if usage.with_tokens:
            text += (
                f", {usage.input_tokens} input and {usage.output_tokens} output tokens "
                f"(reported by {usage.with_tokens} of {usage.model_calls} calls)"
            )
    text += "."
    if usage.growing:
        text += (
            f" Input tokens grew by half or more across successive model calls in {counted(usage.growing, 'request')}, "
            f"up to {usage.largest_growth:.1f} times the first call's."
        )
    if usage.length_limited:
        text += f" {counted(usage.length_limited, 'call')} stopped at the length limit."
    if usage.failed:
        text += f" {counted(usage.failed, 'operation')} failed."
    if not sufficient:
        text += (
            f" Reported from {MIN_OPERATIONS} operations, one call above {usage.threshold} tokens, or one "
            "length-limited stop."
        )
    return text


def _checks(usage: _Usage) -> list[str]:
    checks: list[str] = []
    if usage.most_calls > 2:
        checks.append(
            "Several model calls in one request suggest an agent or tool loop: check that it ends and caps its "
            "iterations."
        )
    if usage.growing:
        checks.append(
            "Input that grows with each call resends the conversation: trim or summarize what is sent."
            if usage.most_calls > 2
            else "The second call's input grew with what the first call returned, such as a tool's result: check "
            "what that tool returns if it is large."
        )
    if usage.length_limited:
        checks.append("A length-limited answer is cut off: raise the output limit or ask for a shorter answer.")
    if not checks:
        checks.append(
            "Two model calls in one request is the shape of one tool call and its answer: open an exemplar "
            "request's trace to see each operation in order."
            if usage.most_calls == 2
            else "Open an exemplar request's trace to see each operation in order."
        )
    return checks[:3]


def _limitations(usage: _Usage) -> list[str]:
    limitations: list[str] = []
    if usage.trace_linked:
        linked = usage.trace_linked
        limitations.append(
            f"{counted(linked, 'operation')} of {usage.operations} came from GenAI spans, linked to "
            f"{'its' if linked == 1 else 'their'} request by trace id and time; such an operation outside a traced "
            "request is not counted."
        )
    if usage.with_tokens < usage.model_calls:
        limitations.append("Some model calls reported no tokens, so token totals are a floor.")
    return limitations


def _finding(route: str, usage: _Usage, eligible: int) -> Finding:
    sufficient = usage.operations >= MIN_OPERATIONS or usage.length_limited > 0 or usage.over_threshold > 0
    return Finding(
        key=route, subject=route, sufficient=sufficient, sentence=_sentence(route, usage, eligible, sufficient),
        eligible=eligible, affected=len(usage.requests), what_to_check=_checks(usage),
        exemplar_request_ids=usage.exemplars, columns=COLUMNS, rows=usage.rows, limitations=_limitations(usage),
        tier=usage.tier,
    )  # fmt: skip


def evaluate(snapshot: Snapshot) -> Evaluation:
    requests = project_requests(snapshot, "ai")
    by_route: dict[str, list[Request]] = defaultdict(list)
    for request in requests:
        by_route[request.route].append(request)
    findings: list[Finding] = []
    for route, routed in by_route.items():
        usage = _Usage(snapshot.ai_token_threshold)
        for request in routed:
            if operations := request.children["ai"]:
                usage.add(request, operations)
        if usage.operations:
            findings.append(_finding(route, usage, len(routed)))
    unplaced = not snapshot.recorded("http") and bool(snapshot.records.get("ai"))
    return Evaluation(len(requests), findings, NO_ROUTE if unplaced else None)
