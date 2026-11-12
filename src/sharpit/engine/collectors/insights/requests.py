"""Requests projected from the journal's ``http`` records, with the events of other sources joined to them.

The record shape is ``requestId``, ``traceId`` and ``route`` (``"GET /api/x"``); W5a's http producer meets it. An event
joins the request it names by ``requestId``, else the one its ``traceId`` names. Without the http source there are no
requests and nothing joins: the caller says so rather than guess a route.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sharpit.engine.collectors.insights.snapshot import Snapshot


@dataclass(frozen=True)
class Request:
    request_id: str
    route: str
    trace_id: str | None
    children: dict[str, list[dict[str, object]]] = field(default_factory=dict[str, list[dict[str, object]]])


def project_requests(snapshot: Snapshot, *sources: str) -> list[Request]:
    """The retained http requests, each with its children from ``sources`` (recorded ones only), in journal order."""
    if not snapshot.recorded("http"):
        return []
    requests = [
        Request(str(r.get("requestId")), str(r.get("route") or ""), _text(r.get("traceId")), {s: [] for s in sources})
        for r in snapshot.records.get("http", ())
    ]
    by_id = {r.request_id: r for r in requests}
    by_trace: dict[str, Request] = {}
    for request in requests:
        if request.trace_id:
            by_trace.setdefault(request.trace_id, request)
    for source in sources:
        for event in snapshot.records.get(source, ()):
            owner = by_id.get(_text(event.get("requestId")) or "") or by_trace.get(_text(event.get("traceId")) or "")
            if owner is not None:
                owner.children[source].append(event)
    return requests


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
