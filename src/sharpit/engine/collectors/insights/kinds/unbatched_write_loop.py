"""BootUI v2.4.0 ``UnbatchedWriteLoop.java`` methods: evaluate (58-88), uncounted (90-105), tally (108-149),
finding (203-273).
"""

from __future__ import annotations

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.sql_readability import SET_OPERATION, WRITE, readable
from sharpit.engine.collectors.insights.text import counted, millis, stable_hash
from sharpit.engine.sqltext import MASK

KIND = "unbatched-write-loop"
TITLE = "Unbatched write loops"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

MIN_STATEMENTS = 10
MIN_REQUESTS = 2


def not_applicable(snapshot: Snapshot) -> str | None:
    return ids_withheld(snapshot, "unbatched writes cannot be placed in a request")


def _request_writes(request: Request) -> tuple[dict[str, list[tuple[str, int, str]]], int, int]:
    per_request: dict[str, list[tuple[str, int, str]]] = {}
    unreadable = unknown_batch = 0
    for event in request.children["sql"]:
        statement = event.get("sql")
        if event.get("provenance") != "EXECUTION":
            continue
        if not isinstance(statement, str):
            continue
        write = WRITE.match(statement)
        if write is None:
            continue
        if event.get("failed") is True:
            continue
        if not readable(statement) or statement.endswith("…") or SET_OPERATION.search(statement):
            unreadable += 1
            continue
        batch_size = event.get("batchSize")
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            unknown_batch += 1
            continue
        if batch_size == 1:
            site = event.get("callSite")
            duration = event.get("durationNanos")
            per_request.setdefault(statement, []).append(
                (
                    request.request_id,
                    duration if isinstance(duration, int) and duration >= 0 else -1,
                    site if isinstance(site, str) else "",
                )
            )
    return per_request, unreadable, unknown_batch


def _finding(route: str, statement: str, runs: list[list[tuple[str, int, str]]], eligible: int) -> Finding:
    runs.sort(key=len, reverse=True)
    sufficient = len(runs) >= MIN_REQUESTS
    shown_statement = f"`{statement}`" if MASK not in statement else "one write statement shape"
    sentence = (
        f"`{route}` ran {shown_statement} {MIN_STATEMENTS} or more times, each without a JDBC batch, "
        f"in {len(runs)} of {counted(eligible, 'request')}, up to {len(runs[0])} times in one."
        if sufficient
        else (
            f"`{route}`: {len(runs)} of {MIN_REQUESTS} requests needed to report {shown_statement} run "
            f"{MIN_STATEMENTS} or more times without a JDBC batch."
        )
    )
    rows = [row for run in runs for row in run]
    unknown_time = any(row[1] < 0 for row in rows)
    total = sum(max(0, row[1]) for row in rows)
    return Finding(
        key=f"{route}:{stable_hash(statement)}",
        subject=route,
        sufficient=sufficient,
        sentence=sentence,
        eligible=eligible,
        affected=len(runs),
        what_to_check=[
            "If writes go through SQLAlchemy, check whether `executemany()` or a bulk insert/update is used instead "
            "of issuing one statement per row.",
            "With PostgreSQL or MySQL, check whether the driver rewrites a batch into fewer statements, such as "
            "`reWriteBatchedInserts` or `rewriteBatchedStatements`.",
            "If writes go through DB-API, send them with `executemany()`.",
        ],
        exemplar_request_ids=list(dict.fromkeys(row[0] for row in rows))[:3],
        columns=["Request", "Statement", "Executions", "Time (ms)", "Call site"],
        rows=[
            [
                run[0][0],
                statement,
                str(len(run)),
                "unknown" if any(row[1] < 0 for row in run) else millis(sum(max(0, row[1]) for row in run)),
                max((row[2] for row in run), key=lambda site: sum(item[2] == site for item in run)),
            ]
            for run in runs
        ],
        limitations=[
            "Counts executions the database ran with a batch size of one: a statement sent in a JDBC batch is "
            "not counted, and neither is one whose batch size is unknown.",
            "Total time is unknown."
            if unknown_time
            else (
                f"Total time is {millis(total)} ms, summed across affected requests."
                if total
                else "Total time is unmeasured: every execution was recorded as 0."
            ),
            "Transactions are not recorded, so executions are counted per request, not per transaction.",
        ],
    )


def evaluate(snapshot: Snapshot) -> Evaluation:
    routes: dict[str, dict[str, list[list[tuple[str, int, str]]]]] = {}
    route_eligible: dict[str, int] = {}
    unreadable = unknown_batch = eligible = 0
    for request in project_requests(snapshot, "sql"):
        writes, unreadable_count, unknown_count = _request_writes(request)
        unreadable += unreadable_count
        unknown_batch += unknown_count
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
    if unreadable:
        reasons.append(
            f"{counted(unreadable, 'statement')} that might be a write could not be read, so "
            f"{'it is' if unreadable == 1 else 'they are'} not counted as unbatched."
        )
    if unknown_batch:
        reasons.append(
            f"{counted(unknown_batch, 'executed write')} had no recorded batch size, so "
            f"{'it is' if unknown_batch == 1 else 'they are'} not counted as unbatched."
        )
    return Evaluation(eligible, findings, " ".join(reasons) or None)
