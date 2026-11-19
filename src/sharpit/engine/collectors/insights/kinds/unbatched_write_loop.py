"""``unbatched-write-loop``: BootUI ``E/insights/UnbatchedWriteLoop.java:33-55``."""

from __future__ import annotations

import re

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, millis, stable_hash

KIND = "unbatched-write-loop"
TITLE = "Unbatched write loops"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

MIN_STATEMENTS = 10
MIN_REQUESTS = 2
_WRITE = re.compile(r"\s*(insert|update|delete|merge)\b", re.IGNORECASE)


def _request_writes(request: Request) -> tuple[dict[str, list[tuple[str, int, str]]], bool, int, int]:
    per_request: dict[str, list[tuple[str, int, str]]] = {}
    known_write = False
    prepared = unknown = 0
    for event in request.children["sql"]:
        statement = event.get("sql")
        if not isinstance(statement, str) or not _WRITE.match(statement) or event.get("failed") is True:
            continue
        provenance = event.get("provenance")
        if provenance == "PREPARATION":
            prepared += 1
            continue
        if provenance != "EXECUTION":
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
                    site if isinstance(site, str) else "",
                )
            )
    return per_request, known_write, prepared, unknown


def _finding(route: str, statement: str, runs: list[list[tuple[str, int, str]]], eligible: int) -> Finding:
    runs.sort(key=len, reverse=True)
    sufficient = len(runs) >= MIN_REQUESTS
    sentence = (
        f"`{route}` ran one write statement shape {MIN_STATEMENTS} or more times, each without a JDBC batch, "
        f"in {len(runs)} of {counted(len(runs), 'request')}, up to {len(runs[0])} times in one."
        if sufficient
        else f"`{route}`: {len(runs)} of {MIN_REQUESTS} requests needed to report one write statement shape "
        f"run {MIN_STATEMENTS} or more times without a JDBC batch."
    )
    rows = [row for run in runs for row in run]
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
        rows=[[run[0][0], statement, str(len(run)), millis(sum(row[1] for row in run)), run[0][2]] for run in runs],
        limitations=[
            "Counts executions with a batch size of one; batched writes and writes with unknown batch size "
            "are not counted.",
            "Transactions are not recorded, so executions are counted per request, not per transaction.",
            "Total time is measured from SQL event durations; a zero duration is unmeasured.",
        ],
    )


def evaluate(snapshot: Snapshot) -> Evaluation:
    routes: dict[str, dict[str, list[list[tuple[str, int, str]]]]] = {}
    route_eligible: dict[str, int] = {}
    prepared = unknown = eligible = 0
    for request in project_requests(snapshot, "sql"):
        writes, known, prepared_count, unknown_count = _request_writes(request)
        prepared += prepared_count
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
    if prepared:
        reasons.append(
            f"{counted(prepared, 'write statement')} were only prepared, so whether they were batched is unknown "
            "and they are not counted."
        )
    if unknown:
        reasons.append(
            f"{counted(unknown, 'executed write')} had no recorded batch size, so they are not counted as unbatched."
        )
    return Evaluation(eligible, findings, " ".join(reasons) or None)
