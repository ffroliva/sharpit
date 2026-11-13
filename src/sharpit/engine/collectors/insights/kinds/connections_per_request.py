"""``connections-per-request``: BootUI ``E/insights/ConnectionsPerRequest.java:24-41`` (evaluation ``:44-99``,
``maxHeldTogether`` ``:101-132``). One request holding two or more connections of one data source at the same time,
such as a ``REQUIRES_NEW`` transaction inside another. Intervals come from each connection's monotonic checkout time
(``checkoutNanos``, ``perf_counter_ns`` at checkout) and hold duration, so sequential connections never count as held
together.

Deviations (proposed, by field):
- ``uncounted``: BootUI skips a connection with no data source name or no checkout time without a word. sharpit's
  producer writes ``dataSource`` null for an engine the registry does not hold, so the check counts those connections
  and says so: "nothing found" over connections it could not place is never a clean result.
- ``not_applicable``: http records exist but none names a request id (the exposure withheld them), so no connection can
  be placed in a request.
- ``shared pool``: SQLAlchemy's ``StaticPool`` and ``SingletonThreadPool`` (in-memory sqlite) hand one connection to
  every checkout, so a nested checkout is one event and cannot overlap anything; the check says so in its reason.
- the pool size is a queue pool's size plus its overflow (``DataSourcePoolSizes`` reads Hikari's maximum); another pool
  or an unbounded overflow has none, and the estimate then uses P.
"""

from __future__ import annotations

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, stable_hash

KIND = "connections-per-request"
TITLE = "Connections held together"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"connection"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = True

COLUMNS = ["Request", "Connections held together"]
NO_POOL_SIZE = "The pool's maximum size is unavailable; the estimate uses P."
POOL_SIZE = "The estimate uses the pool's current maximum size."


def not_applicable(snapshot: Snapshot) -> str | None:
    """http records exist but none names a request id: the exposure withheld them, so no connection can be placed."""
    return ids_withheld(snapshot, "connections cannot be placed in a request")


def _span(event: dict[str, object]) -> tuple[str, int, int] | None:
    """``(data source, checkout, release)`` of a connection event, or ``None`` if it has no name or checkout time."""
    data_source, checkout, held = event.get("dataSource"), event.get("checkoutNanos"), event.get("durationNanos")
    if not isinstance(data_source, str) or not data_source:
        return None
    if not isinstance(checkout, int) or isinstance(checkout, bool) or checkout < 0:
        return None
    hold = held if isinstance(held, int) and not isinstance(held, bool) else 0
    return data_source, checkout, checkout + max(0, hold)


def _most_at_once(spans: list[tuple[int, int]]) -> int:
    """The most spans open at once; at equal instants a release comes before a checkout (``maxHeldTogether``)."""
    edges = sorted([(start, 1) for start, _ in spans] + [(end, -1) for _, end in spans])
    open_now = most = 0
    for _, step in edges:
        open_now += step
        most = max(most, open_now)
    return most


def max_held_together(request: Request) -> tuple[dict[str, int], int]:
    """The most connections of each data source the request held at once, and how many it could not place."""
    spans: dict[str, list[tuple[int, int]]] = {}
    unplaced = 0
    for event in request.children.get("connection", []):
        span = _span(event)
        if span is None:
            unplaced += 1
        else:
            spans.setdefault(span[0], []).append((span[1], span[2]))
    return {data_source: _most_at_once(held) for data_source, held in spans.items()}, unplaced


def _estimate(pool: int | None, held: int) -> str:
    if pool is None:
        return (
            f"With a pool of P connections, floor((P - 1) / {held - 1}) + 1 concurrent requests can exhaust the pool "
            "while waiting for another connection."
        )
    noun = "request can" if pool <= held - 1 else "requests can"
    return (
        f"With a pool of {pool} connections and the observed maximum of {held} held per request, "
        f"{(pool - 1) // (held - 1) + 1} concurrent {noun} exhaust the pool while waiting for another connection."
    )


def _finding(
    route: str, data_source: str, rows: list[tuple[str, int]], eligible: int, held: int, pool: int | None
) -> Finding:
    rows = sorted(rows, key=lambda row: -row[1])  # stable: requests of equal count keep their order
    return Finding(
        key=f"{route}:{stable_hash(data_source)}", subject=route, sufficient=True,
        sentence=f"`{route}` held {held} connections of `{data_source}` at the same time in {len(rows)} of "
        f"{counted(eligible, 'request')}.",
        eligible=eligible, affected=len(rows),
        what_to_check=[
            "Check for a REQUIRES_NEW transaction, or a second call to the data source, inside an open transaction "
            "(Transactions).",
            f"{_estimate(pool, held)} This is a hold-and-wait estimate, not proof of a deadlock "
            "(Database Connection Pools).",
        ],
        exemplar_request_ids=[request_id for request_id, _ in rows[:3]], columns=COLUMNS,
        rows=[[request_id, str(count)] for request_id, count in rows],
        limitations=[
            "Counts logical connections the application obtained. The estimate assumes nested checkouts, not "
            "parallel independent work; other pool users can exhaust it at lower concurrency.",
            NO_POOL_SIZE if pool is None else POOL_SIZE,
        ],
    )  # fmt: skip


def _route_findings(snapshot: Snapshot, route: str, requests: list[Request]) -> tuple[list[Finding], int]:
    by_data_source: dict[str, list[tuple[str, int]]] = {}
    unplaced = 0
    for request in requests:
        most, skipped = max_held_together(request)
        unplaced += skipped
        for data_source, held in most.items():
            if held >= 2:
                by_data_source.setdefault(data_source, []).append((request.request_id, held))
    findings = [
        _finding(
            route, data_source, rows, len(requests), max(held for _, held in rows), snapshot.pool_size(data_source)
        )
        for data_source, rows in by_data_source.items()
    ]
    return findings, unplaced


def evaluate(snapshot: Snapshot) -> Evaluation:
    by_route: dict[str, list[Request]] = {}
    for request in project_requests(snapshot, "connection"):
        by_route.setdefault(request.route, []).append(request)
    findings: list[Finding] = []
    unplaced = 0
    for route, requests in by_route.items():
        route_findings, skipped = _route_findings(snapshot, route, requests)
        findings += route_findings
        unplaced += skipped
    notes = [*_unplaced_note(unplaced), *_shared_pool_notes(snapshot)]
    return Evaluation(len(snapshot.requests), findings, " ".join(notes) or None)


def _unplaced_note(unplaced: int) -> list[str]:
    if not unplaced:
        return []
    return [
        f"{counted(unplaced, 'connection')} had no data source name or checkout time, so "
        f"{'it is' if unplaced == 1 else 'they are'} not counted as held together."
    ]


def _shared_pool_notes(snapshot: Snapshot) -> list[str]:
    """A pool that hands one connection to every checkout journals a nested checkout as one event, so nothing it
    holds can be told apart as held together: say so rather than read it as "none held together"."""
    names = dict.fromkeys(
        name for event in snapshot.records.get("connection", ()) if isinstance(name := event.get("dataSource"), str)
    )
    return [
        f"The pool of `{name}` ({pool}) hands one connection to every checkout, so a connection held inside another "
        "is journaled once and cannot be counted as held together."
        for name in names
        if (pool := snapshot.shared_pool(name))
    ]
