"""Requests projected from the journal's ``http`` records, with the events of other sources joined to them.

The http record shape is the W5a http producer's (``exchanges.http_event``):
``requestId`` (str), ``traceId`` (str, lower-case 32 hex as ``capture/exchanges.trace_id`` writes it), ``method`` (str),
``route`` (the label, ``"GET /api/x"``), ``status`` (int), ``durationNanos`` (int),
``epochMillis`` (epoch ms, BootUI's name; ``startedAt`` is a fallback), ``startNanos`` (BootUI's
``timing.startNanos``, flat: ``perf_counter_ns``, the clock of the sql event's ``completedNanos``).
Only ``requestId`` is required; a missing field reads as ``None``.

An event that carries a ``requestId`` joins that request or nothing (BootUI ``InsightsSnapshot.java:205-209``); an event
without one joins the request its ``traceId`` names. Without the http source there are no requests and nothing joins:
the caller says so rather than guess a route. The projection and each source's join are built once per snapshot
(``Snapshot.request_index``), however many kinds read them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sharpit.engine.collectors.insights.snapshot import LOSS_HORIZON_SLACK_MILLIS, Snapshot


@dataclass(frozen=True)
class Request:
    request_id: str
    route: str
    trace_id: str | None
    method: str | None = None
    status: int | None = None
    duration_nanos: int | None = None
    started_at: int | None = None
    start_nanos: int | None = None
    children: dict[str, list[dict[str, object]]] = field(default_factory=dict[str, list[dict[str, object]]])


class RequestIndex:
    """The retained http requests and the join of an event to one of them."""

    def __init__(self, records: tuple[dict[str, object], ...], loss_horizon: int | None = None) -> None:
        # a record without a request id (withheld by the exposure, or never written) is no request: never ``str(None)``
        projected = tuple(
            Request(
                request_id, str(r.get("route") or ""), text_or_none(r.get("traceId")), text_or_none(r.get("method")),
                count(r.get("status")), count(r.get("durationNanos")),
                count(r.get("epochMillis", r.get("startedAt"))), count(r.get("startNanos")),
            )
            for r in records
            if (request_id := text_or_none(r.get("requestId")))
        )  # fmt: skip
        # ``RuntimeInsightsService.visibleEntries``: a request that started at or before the journal's loss horizon may
        # have lost events of its own, so judging it would read a missing statement as one that never happened.
        self.requests = tuple(r for r in projected if not before_loss(r, loss_horizon))
        self.left_out = len(projected) - len(self.requests)
        self._by_id = {r.request_id: r for r in self.requests}
        self._left_out_ids = frozenset(r.request_id for r in projected if r.request_id not in self._by_id)
        self._joined: dict[str, dict[str, list[dict[str, object]]]] = {}
        self._projected: dict[tuple[str, ...], tuple[Request, ...]] = {}
        self._by_trace: dict[str, Request] = {}
        for request in projected:  # a trace's owner is found among ALL requests, as BootUI's ``AiCallOwners`` does
            if request.trace_id:
                self._by_trace.setdefault(request.trace_id, request)

    def owner(self, event: dict[str, object]) -> Request | None:
        """The judged request an event belongs to. A left-out request's evidence joins none (``visibleEntries``)."""
        request_id = text_or_none(event.get("requestId"))
        if request_id:
            return self._by_id.get(request_id)
        owner = self._by_trace.get(text_or_none(event.get("traceId")) or "")
        return owner if owner is not None and owner.request_id in self._by_id else None

    def left_out_event(self, event: dict[str, object]) -> bool:
        """Whether the event is a left-out request's own or a trace-only event of it: BootUI ``visibleEntries`` drops
        it, so the coverage and the window do not count it."""
        if request_id := text_or_none(event.get("requestId")):
            return request_id in self._left_out_ids
        owner = self._by_trace.get(text_or_none(event.get("traceId")) or "")
        return owner is not None and owner.request_id in self._left_out_ids

    def _join(self, source: str, events: tuple[dict[str, object], ...]) -> dict[str, list[dict[str, object]]]:
        """``source``'s events by owning request id, computed once."""
        if (joined := self._joined.get(source)) is None:
            joined = self._joined[source] = {}
            for event in events:
                if (owner := self.owner(event)) is not None:
                    joined.setdefault(owner.request_id, []).append(event)
        return joined

    def project(self, snapshot: Snapshot, sources: tuple[str, ...]) -> tuple[Request, ...]:
        if (projected := self._projected.get(sources)) is None:
            joins = {s: self._join(s, snapshot.records.get(s, ())) for s in sources}
            projected = self._projected[sources] = tuple(
                replace(r, children={s: joins[s].get(r.request_id, []) for s in sources}) for r in self.requests
            )
        return projected


def before_loss(request: Request, loss_horizon: int | None) -> bool:
    """``beforeLoss``: it started at or before the horizon plus the slack; a request with no start time cannot be
    placed, so it is left out whenever anything was lost (fail closed)."""
    if loss_horizon is None:
        return False
    return request.started_at is None or request.started_at <= loss_horizon + LOSS_HORIZON_SLACK_MILLIS


def project_requests(snapshot: Snapshot, *sources: str) -> tuple[Request, ...]:
    """The retained http requests, each with its children from ``sources`` (recorded ones only), in journal order.
    Shared per snapshot: read, never mutate."""
    return snapshot.request_index.project(snapshot, sources)


def text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def ids_withheld(snapshot: Snapshot, consequence: str) -> str | None:
    """Why a kind cannot work: http events were recorded but none kept its request id (the exposure withheld them),
    so ``consequence`` (what the kind cannot do). That is not "no eligible work"; the kind says so. A request left out
    before a loss kept its id, so it is not this: ``Snapshot.ids_withheld`` is the one gate every kind reads."""
    if not snapshot.ids_withheld:
        return None
    return f"Request ids are withheld at METADATA_ONLY exposure, so {consequence} (SHARPIT_EXPOSE_VALUES)."
