"""Requests projected from the journal's ``http`` records, with the events of other sources joined to them.

The http record shape is a contract the W5a http producer meets (self-declared here; no producer is merged yet):
``requestId`` (str), ``traceId`` (str, lower-case 32 hex as ``capture/exchanges.trace_id`` writes it), ``method`` (str),
``route`` (the label, ``"GET /api/x"``), ``status`` (int), ``durationNanos`` (int), ``startedAt`` (epoch ms). Only
``requestId`` is required; a missing field reads as ``None``.

An event that carries a ``requestId`` joins that request or nothing (BootUI ``InsightsSnapshot.java:205-209``); an event
without one joins the request its ``traceId`` names. Without the http source there are no requests and nothing joins:
the caller says so rather than guess a route. The projection is built once per snapshot (``Snapshot.request_index``).
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
    children: dict[str, list[dict[str, object]]] = field(default_factory=dict[str, list[dict[str, object]]])


class RequestIndex:
    """The retained http requests and the join of an event to one of them."""

    def __init__(self, records: tuple[dict[str, object], ...]) -> None:
        # a record without a request id (withheld by the exposure, or never written) is no request: never ``str(None)``
        self.requests = tuple(
            Request(
                request_id, str(r.get("route") or ""), _text(r.get("traceId")), _text(r.get("method")),
                _count(r.get("status")), _count(r.get("durationNanos")), _count(r.get("startedAt")),
            )
            for r in records
            if (request_id := _text(r.get("requestId")))
        )  # fmt: skip
        self._by_id = {r.request_id: r for r in self.requests}
        self._by_trace: dict[str, Request] = {}
        for request in self.requests:
            if request.trace_id:
                self._by_trace.setdefault(request.trace_id, request)

    def owner(self, event: dict[str, object]) -> Request | None:
        request_id = _text(event.get("requestId"))
        if request_id:
            return self._by_id.get(request_id)
        return self._by_trace.get(_text(event.get("traceId")) or "")


def project_requests(snapshot: Snapshot, *sources: str) -> list[Request]:
    """The retained http requests, each with its children from ``sources`` (recorded ones only), in journal order."""
    index = snapshot.request_index
    requests = [replace(r, children={s: [] for s in sources}) for r in index.requests]
    by_id = {r.request_id: r for r in requests}
    for source in sources:
        for event in snapshot.records.get(source, ()):
            if (owner := index.owner(event)) is not None:
                by_id[owner.request_id].children[source].append(event)
    return requests


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
