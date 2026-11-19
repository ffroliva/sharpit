"""``repeated-selects``: BootUI v2.4.0 ``RepeatedSelects.java`` evaluate (126-187), finding (189-330).

The finding names a statement shape because SQL names and values can trigger the free-text masker.
"""

from __future__ import annotations

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.sql_readability import SET_OPERATION, readable
from sharpit.engine.collectors.insights.text import (
    HIGH_REPEAT_KEEP,
    MIN_REQUESTS,
    UNDER_DEFAULT_FLOOR,
    counted,
    millis,
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
    for event in sorted(request.children["sql"], key=_start):
        sql = event.get("sql")
        if event.get("provenance") != "EXECUTION":
            continue
        fingerprint = stable_hash(" ".join(sql.split())) if isinstance(sql, str) else ""
        if first is None:
            first = fingerprint
        if event.get("failed") is True:
            continue
        if not isinstance(sql, str) or not readable(sql) or sql.endswith("…") or SET_OPERATION.search(sql):
            unread += 1
            continue
        if not sql.lower().startswith("select") or fingerprint == first:
            continue
        duration = event.get("durationNanos")
        site = event.get("callSite")
        counts.setdefault(fingerprint, []).append(
            (
                request.request_id,
                duration if isinstance(duration, int) and duration >= 0 else -1,
                site if isinstance(site, str) else "",
                " ".join(sql.split()),
            )
        )
    return counts, unread


def evaluate(snapshot: Snapshot) -> Evaluation:
    groups: dict[tuple[str, str], list[tuple[str, int, str, str]]] = {}
    requests = project_requests(snapshot, "sql")
    route_counts: dict[str, int] = {}
    unread = 0
    for request in requests:
        route_counts[request.route] = route_counts.get(request.route, 0) + 1
        counts, skipped = _request_repeats(request)
        unread += skipped
        for fingerprint, rows in counts.items():
            if len(rows) >= MIN_REPEATS:
                groups.setdefault((request.route, fingerprint), []).extend(rows)
    findings: list[Finding] = []
    for (route, fingerprint), rows in groups.items():
        by_request: dict[str, list[tuple[str, int, str, str]]] = {}
        for row in rows:
            by_request.setdefault(row[0], []).append(row)
        runs = sorted(by_request.values(), key=len, reverse=True)
        sufficient = len(runs) >= MIN_REQUESTS
        shape = rows[0][3]
        first_event_shape = f"`{shape}`" if MASK not in shape else "a repeated SELECT statement shape"
        sentence = (
            f"`{route}` ran {first_event_shape} {MIN_REPEATS} or more times after another statement in "
            f"{len(runs)} of {counted(route_counts[route], 'request')}, up to {len(runs[0])} times in one."
            if sufficient
            else f"`{route}`: {len(runs)} of {MIN_REQUESTS} requests needed to report {first_event_shape} "
            f"repeated {MIN_REPEATS} or more times."
        )
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
            "Total repeat time is "
            + (
                f"{millis(total)} ms, summed across affected requests."
                if total and known
                else "unmeasured: every execution was recorded as 0."
                if known
                else "unknown."
            ),
        ]
        if under_floor:
            limitations.append(UNDER_DEFAULT_FLOOR)
        findings.append(
            Finding(
                key=f"{route}:{fingerprint}",
                subject=route,
                sufficient=sufficient,
                sentence=sentence,
                eligible=route_counts[route],
                affected=len(runs),
                what_to_check=[
                    "Open an exemplar request in Live Activity and check whether each repeat loads the children "
                    "of one row the first statement returned.",
                    "If it does, load them with one statement, such as a join or an IN list, in SQL Trace's call site.",
                ],
                exemplar_request_ids=[run[0][0] for run in runs[:3]],
                columns=["Request", "Executions", "Time (ms)", "Call site", "Phase", "In transaction"],
                rows=[
                    [
                        run[0][0],
                        str(len(run)),
                        "unknown" if any(r[1] < 0 for r in run) else millis(sum(max(0, r[1]) for r in run)),
                        max((row[2] for row in run), key=lambda site: sum(item[2] == site for item in run)),
                        "unknown",
                        "unknown",
                    ]
                    for run in runs
                ],
                limitations=limitations,
            )
        )
    uncounted = (
        f"{counted(unread, 'statement')} contained a mask marker or unsupported-database placeholder, used a set "
        "operation, or was truncated, so it is not counted."
        if unread
        else None
    )
    return Evaluation(len(requests), findings, uncounted)
