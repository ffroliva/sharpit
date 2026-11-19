"""``repeated-selects``: BootUI ``E/insights/RepeatedSelects.java:77,152-186``.

The finding names a statement shape because SQL names and values can trigger the free-text masker.
"""

from __future__ import annotations

import re

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import (
    HIGH_REPEAT_KEEP,
    MIN_REQUESTS,
    UNDER_DEFAULT_FLOOR,
    counted,
    millis,
    stable_hash,
)
from sharpit.engine.sqltext.constants import MASK, UNSUPPORTED_STATEMENT

KIND = "repeated-selects"
TITLE = "Repeated SELECTs"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

MIN_REPEATS = 5
_UNREADABLE = {MASK, UNSUPPORTED_STATEMENT}
_SET_OPERATION = re.compile(r"\b(union|intersect|except)\b", re.IGNORECASE)


def not_applicable(snapshot: Snapshot) -> str | None:
    return ids_withheld(snapshot, "repeated SELECTs cannot be placed in a request")


def _start(event: dict[str, object]) -> int:
    completed, duration = event.get("completedNanos"), event.get("durationNanos")
    return (
        completed - duration
        if isinstance(completed, int) and isinstance(duration, int) and completed >= 0 and duration >= 0
        else 2**63 - 1
    )


def _request_repeats(request: Request) -> tuple[dict[str, list[tuple[str, int, int, str]]], int]:
    first: str | None = None
    counts: dict[str, list[tuple[str, int, int, str]]] = {}
    unread = 0
    for event in sorted(request.children["sql"], key=_start):
        sql = event.get("sql")
        if event.get("failed") is True or event.get("provenance") != "EXECUTION":
            continue
        if not isinstance(sql, str) or sql in _UNREADABLE or sql.endswith("…") or _SET_OPERATION.search(sql):
            unread += 1
            continue
        fingerprint = stable_hash(" ".join(sql.split()))
        first = first or fingerprint
        if not sql.lower().startswith("select") or fingerprint == first:
            continue
        duration = event.get("durationNanos")
        site = event.get("callSite")
        counts.setdefault(fingerprint, []).append(
            (
                request.request_id,
                max(0, duration) if isinstance(duration, int) else 0,
                duration if isinstance(duration, int) and duration >= 0 else -1,
                site if isinstance(site, str) else "",
            )
        )
    return counts, unread


def evaluate(snapshot: Snapshot) -> Evaluation:
    groups: dict[tuple[str, str], list[tuple[str, int, int, str]]] = {}
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
        by_request: dict[str, list[tuple[str, int, int, str]]] = {}
        for row in rows:
            by_request.setdefault(row[0], []).append(row)
        runs = sorted(by_request.values(), key=len, reverse=True)
        sufficient = len(runs) >= MIN_REQUESTS
        first_event_shape = "a repeated SELECT statement shape"
        sentence = (
            f"`{route}` ran {first_event_shape} {MIN_REPEATS} or more times after another statement in "
            f"{len(runs)} of {counted(route_counts[route], 'request')}, up to {len(runs[0])} times in one."
            if sufficient
            else f"`{route}`: {len(runs)} of {route_counts[route]} requests needed to report {first_event_shape} "
            f"repeated {MIN_REPEATS} or more times."
        )
        known = all(row[2] >= 0 for row in rows)
        total = sum(row[1] for row in rows)
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
                else "unmeasured."
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
                    "Check whether the repeated SELECT loads children of rows returned by the first statement.",
                    "If it does, load them with one statement, such as a join or an IN list.",
                ],
                exemplar_request_ids=[run[0][0] for run in runs[:3]],
                columns=["Request", "Executions", "Time (ms)", "Call site"],
                rows=[
                    [
                        run[0][0],
                        str(len(run)),
                        "unknown" if any(r[2] < 0 for r in run) else millis(sum(r[1] for r in run)),
                        run[0][3],
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
