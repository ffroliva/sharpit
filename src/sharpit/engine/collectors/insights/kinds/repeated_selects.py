"""``repeated-selects``: BootUI v2.4.0 ``RepeatedSelects.java`` evaluate (126-187), finding (189-330).

The finding names a statement shape because SQL names and values can trigger the free-text masker.
"""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.sql_readability import (
    event_call_site,
    event_duration,
    is_unreadable_or_compound,
)
from sharpit.engine.collectors.insights.text import (
    HIGH_REPEAT_KEEP,
    MIN_REQUESTS,
    UNDER_DEFAULT_FLOOR,
    counted,
    millis,
    primary_call_site,
    stable_hash,
)
from sharpit.engine.sqltext import MASK

KIND = "repeated-selects"
TITLE = "Repeated SELECTs"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

MIN_REPEATS = 5

WHAT_TO_CHECK = [
    "Open an exemplar request in Live Activity and check whether each repeat loads the children "
    "of one row the first statement returned.",
    "If it does, load them with one statement, such as a join or an IN list, in SQL Trace's call site.",
]
COLUMNS = ["Request", "Executions", "Time (ms)", "Call site", "Phase", "In transaction"]


def not_applicable(snapshot: Snapshot) -> str | None:
    return ids_withheld(snapshot, "repeated SELECTs cannot be placed in a request")


def _start(event: dict[str, object]) -> int:
    completed, duration = event.get("completedNanos"), event.get("durationNanos")
    return (
        completed - duration
        if isinstance(completed, int) and isinstance(duration, int) and completed >= 0 and duration >= 0
        else 2**63 - 1
    )


def _request_repeats(request: Request) -> tuple[dict[str, list[tuple[str, int, str, str]]], int]:
    first: str | None = None
    counts: dict[str, list[tuple[str, int, str, str]]] = {}
    unread = 0
    events = request.children["sql"]
    if len(events) > 1:
        events = sorted(events, key=_start)
    for event in events:
        if event.get("provenance") != "EXECUTION":
            continue
        sql = event.get("sql")
        if first is None:
            first = stable_hash(" ".join(sql.split())) if isinstance(sql, str) else ""
        if event.get("failed") is True:
            continue
        if not isinstance(sql, str) or is_unreadable_or_compound(sql):
            unread += 1
            continue
        if not sql.lower().startswith("select"):
            continue
        normalized = " ".join(sql.split())
        fingerprint = stable_hash(normalized)
        if fingerprint == first:
            continue
        counts.setdefault(fingerprint, []).append(
            (
                request.request_id,
                event_duration(event),
                event_call_site(event),
                normalized,
            )
        )
    return counts, unread


def _group_repeats(
    requests: Sequence[Request],
) -> tuple[dict[tuple[str, str], list[tuple[str, int, str, str]]], dict[str, int], int]:
    groups: dict[tuple[str, str], list[tuple[str, int, str, str]]] = {}
    route_counts: dict[str, int] = {}
    unread = 0
    for request in requests:
        route_counts[request.route] = route_counts.get(request.route, 0) + 1
        counts, skipped = _request_repeats(request)
        unread += skipped
        for fingerprint, rows in counts.items():
            if len(rows) >= MIN_REPEATS:
                groups.setdefault((request.route, fingerprint), []).extend(rows)
    return groups, route_counts, unread


def _sentence(
    route: str,
    shape: str,
    runs: list[list[tuple[str, int, str, str]]],
    eligible: int,
    sufficient: bool,
) -> str:
    first_event_shape = f"`{shape}`" if MASK not in shape else "a repeated SELECT statement shape"
    if sufficient:
        return (
            f"`{route}` ran {first_event_shape} {MIN_REPEATS} or more times after another statement in "
            f"{len(runs)} of {counted(eligible, 'request')}, up to {len(runs[0])} times in one."
        )
    return (
        f"`{route}`: {len(runs)} of {MIN_REQUESTS} requests needed to report {first_event_shape} "
        f"repeated {MIN_REPEATS} or more times."
    )


def _total_time_text(total: int, known: bool) -> str:
    if not known:
        return "Total repeat time is unknown."
    if total > 0:
        return f"Total repeat time is {millis(total)} ms, summed across affected requests."
    return "Total repeat time is unmeasured: every execution was recorded as 0."


def _limitations(
    rows: list[tuple[str, int, str, str]],
    runs: list[list[tuple[str, int, str, str]]],
    sufficient: bool,
) -> list[str]:
    known = all(row[1] >= 0 for row in rows)
    total = sum(max(0, row[1]) for row in rows)
    under_floor = not sufficient and 0 < total < 50_000_000 and max(map(len, runs)) < HIGH_REPEAT_KEEP and known
    limitations = [
        "Counts statements the request ran; a statement Hibernate batches counts once.",
        "JDBC row counts, when known, do not establish how many entities or response items a query produced.",
        (
            "SQL text in findings is named as a statement shape because secret-looking names can mask "
            "the rest of a sentence."
        ),
        _total_time_text(total, known),
    ]
    if under_floor:
        limitations.append(UNDER_DEFAULT_FLOOR)
    return limitations


def _finding_row(run: list[tuple[str, int, str, str]]) -> list[str]:
    unknown_time = any(r[1] < 0 for r in run)
    duration_text = "unknown" if unknown_time else millis(sum(max(0, r[1]) for r in run))
    return [
        run[0][0],
        str(len(run)),
        duration_text,
        primary_call_site([row[2] for row in run]),
        "unknown",
        "unknown",
    ]


def _finding(
    route: str,
    fingerprint: str,
    rows: list[tuple[str, int, str, str]],
    eligible: int,
) -> Finding:
    by_request: dict[str, list[tuple[str, int, str, str]]] = {}
    for row in rows:
        by_request.setdefault(row[0], []).append(row)
    runs = sorted(by_request.values(), key=len, reverse=True)
    sufficient = len(runs) >= MIN_REQUESTS
    shape = rows[0][3]
    return Finding(
        key=f"{route}:{fingerprint}",
        subject=route,
        sufficient=sufficient,
        sentence=_sentence(route, shape, runs, eligible, sufficient),
        eligible=eligible,
        affected=len(runs),
        what_to_check=WHAT_TO_CHECK,
        exemplar_request_ids=[run[0][0] for run in runs[:3]],
        columns=COLUMNS,
        rows=[_finding_row(run) for run in runs],
        limitations=_limitations(rows, runs, sufficient),
    )


def evaluate(snapshot: Snapshot) -> Evaluation:
    requests = project_requests(snapshot, "sql")
    groups, route_counts, unread = _group_repeats(requests)
    findings = [
        _finding(route, fingerprint, rows, route_counts[route]) for (route, fingerprint), rows in groups.items()
    ]
    uncounted = (
        f"{counted(unread, 'statement')} contained a mask marker or unsupported-database placeholder, used a set "
        "operation, or was truncated, so it is not counted."
        if unread
        else None
    )
    return Evaluation(len(requests), findings, uncounted)
