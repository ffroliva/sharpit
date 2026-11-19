"""``unbatched-write-loop``: BootUI ``E/insights/UnbatchedWriteLoop.java:33-55``."""

from __future__ import annotations

import re

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import UNBATCHED_MIN_REQUESTS as MIN_REQUESTS
from sharpit.engine.collectors.insights.text import counted, millis, stable_hash
from sharpit.engine.sqltext import MASK, UNSUPPORTED_STATEMENT

KIND = "unbatched-write-loop"
TITLE = "Unbatched write loops"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

MIN_STATEMENTS = 10
_WRITE = re.compile(r"\s*(insert|update|delete|merge)\b", re.IGNORECASE)
_UNREADABLE = {MASK, UNSUPPORTED_STATEMENT}
_SET_OPERATION = re.compile(r"\b(union|intersect|except)\b", re.IGNORECASE)


def not_applicable(snapshot: Snapshot) -> str | None:
    return ids_withheld(snapshot, "unbatched writes cannot be placed in a request")


def _request_writes(request: Request) -> tuple[dict[str, list[tuple[str, int, int, str]]], bool, int]:
    per_request: dict[str, list[tuple[str, int, int, str]]] = {}
    known_write = False
    unknown = 0
    for event in request.children["sql"]:
        statement = event.get("sql")
        if event.get("failed") is True or event.get("provenance") != "EXECUTION":
            continue
        if (
            not isinstance(statement, str)
            or statement in _UNREADABLE
            or statement.endswith("…")
            or _SET_OPERATION.search(statement)
        ):
            unknown += 1
            continue
        if not _WRITE.match(statement):
            continue
        batch_size = event.get("batchSize")
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            unknown += 1
            continue
        known_write = True
        if batch_size == 1:
            site = event.get("callSite")
            duration = event.get("durationNanos")
            per_request.setdefault(statement, []).append(
                (
                    request.request_id,
                    max(0, duration) if isinstance(duration, int) else 0,
                    duration if isinstance(duration, int) and duration >= 0 else -1,
                    site if isinstance(site, str) else "",
                )
            )
    return per_request, known_write, unknown


def _finding(route: str, statement: str, runs: list[list[tuple[str, int, int, str]]], eligible: int) -> Finding:
    runs.sort(key=len, reverse=True)
    sufficient = len(runs) >= MIN_REQUESTS
    sentence = (
        f"`{route}` ran one write statement shape {MIN_STATEMENTS} or more times, each without a JDBC batch, "
        f"in {len(runs)} of {counted(eligible, 'request')}, up to {len(runs[0])} times in one."
        if sufficient
        else (
            f"`{route}`: {len(runs)} of {counted(eligible, 'request')} requests needed to report one write "
            f"statement shape run {MIN_STATEMENTS} or more times without a JDBC batch."
        )
    )
    rows = [row for run in runs for row in run]
    unknown_time = any(row[2] < 0 for row in rows)
    total = sum(row[1] for row in rows)
    return Finding(
        key=f"{route}:{stable_hash(statement)}",
        subject=route,
        sufficient=sufficient,
        sentence=sentence,
        eligible=eligible,
        affected=len(runs),
        what_to_check=[
            "If the writes go through Hibernate, check `hibernate.jdbc.batch_size`, ordered inserts and updates, "
            "and the id generator.",
            "With PostgreSQL or MySQL, check whether the driver rewrites a batch into fewer statements.",
            "If the writes go through JDBC, send them as one batch, such as `batch_update`.",
        ],
        exemplar_request_ids=list(dict.fromkeys(row[0] for row in rows))[:3],
        columns=["Request", "Statement", "Executions", "Time (ms)", "Call site"],
        rows=[
            [
                run[0][0],
                statement,
                str(len(run)),
                "unknown" if any(row[2] < 0 for row in run) else millis(sum(row[1] for row in run)),
                run[0][3],
            ]
            for run in runs
        ],
        limitations=[
            "Counts executions with a batch size of one; batched writes and writes with unknown batch size "
            "are not counted.",
            "Total time is unknown."
            if unknown_time
            else (
                f"Total time is {millis(total)} ms, summed across affected requests."
                if total
                else "Total time is unmeasured."
            ),
        ],
    )


def evaluate(snapshot: Snapshot) -> Evaluation:
    routes: dict[str, dict[str, list[list[tuple[str, int, int, str]]]]] = {}
    route_eligible: dict[str, int] = {}
    unknown = eligible = 0
    for request in project_requests(snapshot, "sql"):
        writes, known, unknown_count = _request_writes(request)
        unknown += unknown_count
        if known:
            eligible += 1
            route_eligible[request.route] = route_eligible.get(request.route, 0) + 1
        for statement, rows in writes.items():
            if len(rows) >= MIN_STATEMENTS:
                routes.setdefault(request.route, {}).setdefault(statement, []).append(rows)
    findings = [
        _finding(route, statement, runs, route_eligible[route])
        for route, statements in routes.items()
        for statement, runs in statements.items()
    ]
    reasons: list[str] = []
    if unknown:
        reasons.append(
            f"{counted(unknown, 'statement')} contained a mask marker or unsupported-database placeholder, used a set "
            "operation, was truncated, or had no recorded batch size, so it is not counted as an unbatched write."
        )
    return Evaluation(eligible, findings, " ".join(reasons) or None)
