"""``route-time-breakdown``: BootUI ``E/insights/RouteTimeBreakdown.java:137-164`` (evaluation ``:173-223``, findings
``:379-492``). Where a route's warm requests spend their time, as named phases; each route's first request in the run is
reported apart as cold.

Deviations (proposed, by field; the phase maths is ``route_phases``):
- ``timing``: only its ``startNanos`` is written, flat as the http event's ``startNanos`` (``perf_counter_ns``, the
  clock of the sql event's ``completedNanos``); the handler and response marks and the authentication time are not. A
  request is placed by ``startNanos`` and ``durationNanos`` and a statement by ``completedNanos - durationNanos``
  against it, as BootUI does; a request without either is unplaced (left out and counted), never placed by wall
  clock. The stack never marks phases (BootUI's WebFlux branch): no handler-unmarked split, no ``Other filters``,
  ``Handler`` or ``Response write`` phase, and the WebFlux limitation names sharpit. The sql text is never read.
- ``connection``, ``rest-client``, ``authorization``, ``orm`` and ``messaging`` have no producer: their phases, the
  authorization-share and decision-count prominence triggers and the Kafka limitation are absent. ``ai`` events carry
  no wall-clock start, so their time stays unattributed and a limitation names the requests that made AI calls.
- ``resources`` (CPU and allocation) and virtual-thread limitations: http carries neither. The code-paths handler
  split (``setCodePaths``) has no sensor: the handler is never split by method.
- ``clears``: the journal has no clear, so only eviction ends cold knowledge.
"""

from __future__ import annotations

from collections import defaultdict

from sharpit.engine.collectors.insights import route_phases as phases
from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.route_phases import Breakdown, Totals
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, median, millis

KIND = "route-time-breakdown"
TITLE = "Route time breakdown"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http"})
OPTIONAL_READS: frozenset[str] = frozenset(
    {"sql", "connection", "rest-client", "authorization", "ai", "orm", "messaging"}
)
IMPLEMENTED = True

MIN_WARM_REQUESTS = 5
PROMINENT_MEDIAN_NANOS = 20_000_000
SLOW_FEW_WARM_REQUESTS = 2
SLOW_FEW_WARM_MEDIAN_NANOS = 100_000_000
NOT_PROMINENT = "Its warm median is under 20 ms, so it is not prominent."  # no producer records authorization
TOO_FEW_WARM = (
    f"It has fewer than {MIN_WARM_REQUESTS} warm requests, so where its time goes is not known yet, and fewer than 2 "
    "of them or a warm median under 100 ms."
)
NOT_SPLIT = (
    "Its time is not split into phases, since its requests reached no handler sharpit marks or named nothing at all, "
    "and its warm median is under 20 ms."
)
SLOWEST = "Open the slowest exemplar request in Live Activity to see its timeline."
FEW_MORE = "Exercise the route a few more times to read where its time goes."
CHECKS = {
    phases.SQL: "Most of the time is SQL: compare its statements in SQL Trace, and see Repeated SELECTs.",
    phases.UNATTRIBUTED: (
        "Most of the time is outside recorded calls, in filters, handler, or response write, which this stack does "
        "not tell apart: open the slowest exemplar request in Live Activity to see its timeline."
    ),
}


def not_applicable(snapshot: Snapshot) -> str | None:
    """http records exist but none names a request id: the exposure withheld them, so none can be told apart."""
    return ids_withheld(snapshot, "requests cannot be told apart to break a route's time down")


def _slowest(breakdowns: list[Breakdown]) -> list[str]:
    return [b.request.request_id for b in sorted(breakdowns, key=lambda b: -b.duration)[:3]]


def _slow_few(warm: list[Breakdown]) -> bool:
    return len(warm) >= SLOW_FEW_WARM_REQUESTS and median([b.duration for b in warm]) >= SLOW_FEW_WARM_MEDIAN_NANOS


def _rejected(warm: list[Breakdown]) -> str:
    if all(b.request.status in (401, 403) for b in warm):
        return " Every one was answered 401 or 403, as security filters do when they reject a request."
    return ""


def _evicted(snapshot: Snapshot, cold_known: bool) -> list[str]:
    if cold_known:
        return []
    found = [
        "The journal evicted older events, so a route's first request may be gone and none is reported apart as cold."
    ]
    if snapshot.recorded("sql"):
        found.append(
            "The journal evicted older events, so a request may have lost its SQL statements while the request "
            "stayed: that time reads as unattributed."
        )
    return found


def _unplaced(unplaced: int) -> list[str]:
    if not unplaced:
        return []
    return [f"{counted(unplaced, 'request')} had no monotonic start and {'is' if unplaced == 1 else 'are'} left out."]


def _ai(snapshot: Snapshot, warm: list[Breakdown]) -> list[str]:
    ai = sum(1 for b in warm if b.request.children["ai"]) if snapshot.recorded("ai") else 0
    if not ai:
        return []
    return [
        f"{counted(ai, 'request')} made AI calls, which carry no start on the request's clock, so their time "
        "stays unattributed."
    ]


def _limitations(snapshot: Snapshot, cold_known: bool, unplaced: int, warm: list[Breakdown]) -> list[str]:
    return [
        *_evicted(snapshot, cold_known),
        *_unplaced(unplaced),
        "sharpit marks no handler or response phase, so filters, handler, and response write are one unattributed "
        "span around the recorded SQL statements.",
        *_ai(snapshot, warm),
    ]


def _cold_text(cold: Request | None) -> str:
    return (
        ""
        if cold is None or cold.duration_nanos is None
        else f" First request {millis(cold.duration_nanos)} ms (cold)."
    )


def _too_few(route: str, warm: list[Breakdown], cold: Request | None, limitations: list[str]) -> Finding:
    cold_text = _cold_text(cold)
    if _slow_few(warm):  # slow enough that a developer exercising it a few times must not miss it
        sentence = (
            f"`{route}`: warm median {millis(median([b.duration for b in warm]))} ms over "
            f"{counted(len(warm), 'request')}; phases need {MIN_WARM_REQUESTS} warm requests.{cold_text}"
        )
        checks, exemplars, unlisted = [SLOWEST, FEW_MORE], _slowest(warm), None
    else:
        sentence = f"`{route}`: {len(warm)} of {MIN_WARM_REQUESTS} warm requests needed.{cold_text}"
        checks, exemplars, unlisted = [FEW_MORE], [cold.request_id] if cold else [], TOO_FEW_WARM
    return Finding(
        route, route, False, sentence, len(warm), len(warm), checks, exemplars, [], [], limitations, unlisted=unlisted
    )


def _split(route: str, warm: list[Breakdown], cold: Request | None, limitations: list[str]) -> Finding:
    totals = Totals.of(warm)
    median_nanos = median(totals.durations)
    warm_text = f"`{route}`: warm median {millis(median_nanos)} ms over {counted(len(warm), 'request')}"
    cold_text = _cold_text(cold)
    prominent = median_nanos >= PROMINENT_MEDIAN_NANOS
    if totals.only_unattributed():  # no recorded call took time: the breakdown would be one unattributed span
        sentence = (
            f"{warm_text}, none of it in a recorded call; sharpit marks no phases, so where that time went is not "
            f"known.{_rejected(warm)}{cold_text}"
        )
        return Finding(
            route, route, False, sentence, len(warm), len(warm), [SLOWEST], _slowest(warm), phases.COLUMNS,
            totals.rows(), limitations, unlisted=None if prominent else NOT_SPLIT,
        )  # fmt: skip
    ranked = totals.ranked()
    top = [f"{phase} {phases.percent(time, totals.whole)}" for phase, time in ranked[:3] if time]
    # BootUI adds SLOWEST when prominent or the top phase holds half the time; with two phases the top always does
    checks = [CHECKS[ranked[0][0]], SLOWEST]
    return Finding(
        route, route, True, f"{warm_text}; {', '.join(top)}.{cold_text}", len(warm), len(warm), checks, _slowest(warm),
        phases.COLUMNS, totals.rows(), limitations, unlisted=None if prominent else NOT_PROMINENT,
    )  # fmt: skip


def _route(snapshot: Snapshot, route: str, requests: list[Request], cold_known: bool) -> tuple[Finding, int]:
    cold = requests[0] if cold_known else None
    warm = [b for r in requests if r is not cold and (b := phases.breakdown_of(r)) is not None]
    unplaced = len(requests) - len(warm) - (cold is not None)
    limitations = _limitations(snapshot, cold_known, unplaced, warm)
    if len(warm) < MIN_WARM_REQUESTS:
        return _too_few(route, warm, cold, limitations), len(warm)
    return _split(route, warm, cold, limitations), len(warm)


def evaluate(snapshot: Snapshot) -> Evaluation:
    cold_known = int(snapshot.status["evictedEvents"]) == 0  # ``firstRequestIsCold``
    by_route: dict[str, list[Request]] = defaultdict(list)
    for request in project_requests(snapshot, "sql", "ai"):
        by_route[request.route].append(request)
    findings: list[Finding] = []
    eligible = 0
    for route, requests in by_route.items():
        finding, count = _route(snapshot, route, requests, cold_known)
        findings.append(finding)
        eligible += count
    return Evaluation(eligible, findings)
