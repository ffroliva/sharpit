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

from sharpit.engine.collectors.insights.snapshot import Snapshot


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

    def __init__(self, records: tuple[dict[str, object], ...]) -> None:
        # a record without a request id (withheld by the exposure, or never written) is no request: never ``str(None)``
        self.requests = tuple(
            Request(
                request_id, str(r.get("route") or ""), _text(r.get("traceId")), _text(r.get("method")),
                count(r.get("status")), count(r.get("durationNanos")),
                count(r.get("epochMillis", r.get("startedAt"))), count(r.get("startNanos")),
            )
            for r in records
            if (request_id := _text(r.get("requestId")))
        )  # fmt: skip
        self._by_id = {r.request_id: r for r in self.requests}
        self._joined: dict[str, dict[str, list[dict[str, object]]]] = {}
        self._projected: dict[tuple[str, ...], tuple[Request, ...]] = {}
        self._by_trace: dict[str, Request] = {}
        for request in self.requests:
            if request.trace_id:
                self._by_trace.setdefault(request.trace_id, request)

    def owner(self, event: dict[str, object]) -> Request | None:
        request_id = _text(event.get("requestId"))
        if request_id:
            return self._by_id.get(request_id)
        return self._by_trace.get(_text(event.get("traceId")) or "")

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


def project_requests(snapshot: Snapshot, *sources: str) -> tuple[Request, ...]:
    """The retained http requests, each with its children from ``sources`` (recorded ones only), in journal order.
    Shared per snapshot: read, never mutate."""
    return snapshot.request_index.project(snapshot, sources)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def ids_withheld(snapshot: Snapshot, what: str) -> str | None:
    """Why a kind cannot place ``what`` on a route: http events were recorded but none kept its request id (the
    exposure withheld them). That is not "no eligible work"; the kind says so."""
    if snapshot.requests or not snapshot.records.get("http"):
        return None
    return (
        f"Request ids are withheld at METADATA_ONLY exposure, so {what} cannot be placed on a route "
        "(SHARPIT_EXPOSE_VALUES)."
    )
