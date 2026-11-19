"""BootUI v2.4.0 ``UnbatchedWriteLoop.java`` methods: evaluate (58-88), uncounted (90-105), tally (108-149),
finding (203-273).
"""

from __future__ import annotations

from collections.abc import Sequence

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.sql_readability import (
    WRITE,
    event_call_site,
    event_duration,
    is_unreadable_or_compound,
)
from sharpit.engine.collectors.insights.text import counted, millis, primary_call_site, stable_hash
from sharpit.engine.sqltext import MASK

KIND = "unbatched-write-loop"
TITLE = "Unbatched write loops"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

MIN_STATEMENTS = 10
MIN_REQUESTS = 2

WHAT_TO_CHECK = [
    "If writes go through SQLAlchemy, check whether `executemany()` or a bulk insert/update is used instead "
    "of issuing one statement per row.",
    "With PostgreSQL or MySQL, check whether the driver rewrites a batch into fewer statements, such as "
    "`reWriteBatchedInserts` or `rewriteBatchedStatements`.",
    "If writes go through DB-API, send them with `executemany()`.",
]
COLUMNS = ["Request", "Statement", "Executions", "Call site"]


def not_applicable(snapshot: Snapshot) -> str | None:
    return ids_withheld(snapshot, "unbatched writes cannot be placed in a request")


def _is_candidate_write(event: dict[str, object], statement: str) -> bool:
    if event.get("provenance") != "EXECUTION" or event.get("failed") is True:
        return False
    if statement.lower().startswith("select"):
        return False
    return WRITE.match(statement) is not None


def _batch_size(event: dict[str, object]) -> int | None:
    batch = event.get("batchSize")
    if isinstance(batch, int) and not isinstance(batch, bool) and batch >= 1:
        return batch
    return None


def _request_writes(request: Request) -> tuple[dict[str, list[tuple[str, int, str]]], int, int]:
    per_request: dict[str, list[tuple[str, int, str]]] = {}
    unreadable = unknown_batch = 0
    for event in request.children["sql"]:
        statement = event.get("sql")
        if not isinstance(statement, str) or not _is_candidate_write(event, statement):
            continue
        if is_unreadable_or_compound(statement):
            unreadable += 1
            continue
        batch = _batch_size(event)
        if batch is None:
            unknown_batch += 1
            continue
        if batch == 1:
            per_request.setdefault(statement, []).append(
                (request.request_id, event_duration(event), event_call_site(event))
            )
    return per_request, unreadable, unknown_batch


def _group_writes(
    requests: Sequence[Request],
) -> tuple[dict[str, dict[str, list[list[tuple[str, int, str]]]]], dict[str, int], int, int]:
    routes: dict[str, dict[str, list[list[tuple[str, int, str]]]]] = {}
    route_eligible: dict[str, int] = {}
    unreadable = unknown_batch = 0
    for request in requests:
        writes, unreadable_count, unknown_count = _request_writes(request)
        unreadable += unreadable_count
        unknown_batch += unknown_count
        route_eligible[request.route] = route_eligible.get(request.route, 0) + 1
        for statement, rows in writes.items():
            if len(rows) >= MIN_STATEMENTS:
                routes.setdefault(request.route, {}).setdefault(statement, []).append(rows)
    return routes, route_eligible, unreadable, unknown_batch


def _sentence(
    route: str,
    statement: str,
    runs: list[list[tuple[str, int, str]]],
    eligible: int,
    sufficient: bool,
) -> str:
    shown_statement = f"`{statement}`" if MASK not in statement else "one write statement shape"
    if sufficient:
        return (
            f"`{route}` ran {shown_statement} {MIN_STATEMENTS} or more times, each without a JDBC batch, "
            f"in {len(runs)} of {counted(eligible, 'request')}, up to {len(runs[0])} times in one."
        )
    return (
        f"`{route}`: {len(runs)} of {MIN_REQUESTS} requests needed to report {shown_statement} run "
        f"{MIN_STATEMENTS} or more times without a JDBC batch."
    )


def _total_time_text(total: int, unknown_time: bool) -> str:
    if unknown_time:
        return "Total time is unknown."
    if total > 0:
        return f"Total time is {millis(total)} ms, summed across affected requests."
    return "Total time is unmeasured: every execution was recorded as 0."


def _limitations(total: int, unknown_time: bool) -> list[str]:
    return [
        "Counts executions the database ran with a batch size of one: a statement sent in a JDBC batch is "
        "not counted, and neither is one whose batch size is unknown.",
        _total_time_text(total, unknown_time),
        "Transactions are not recorded, so executions are counted per request, not per transaction.",
    ]


def _finding_row(statement: str, run: list[tuple[str, int, str]]) -> list[str]:
    unknown_time = any(row[1] < 0 for row in run)
    duration_text = "unknown" if unknown_time else millis(sum(max(0, row[1]) for row in run))
    return [
        run[0][0],
        statement,
        str(len(run)),
        duration_text,
        primary_call_site([row[2] for row in run]),
    ]


def _finding(
    route: str,
    statement: str,
    runs: list[list[tuple[str, int, str]]],
    eligible: int,
) -> Finding:
    runs.sort(key=len, reverse=True)
    sufficient = len(runs) >= MIN_REQUESTS
    rows = [row for run in runs for row in run]
    unknown_time = any(row[1] < 0 for row in rows)
    total = sum(max(0, row[1]) for row in rows)
    return Finding(
        key=f"{route}:{stable_hash(statement)}",
        subject=route,
        sufficient=sufficient,
        sentence=_sentence(route, statement, runs, eligible, sufficient),
        eligible=eligible,
        affected=len(runs),
        what_to_check=WHAT_TO_CHECK,
        exemplar_request_ids=list(dict.fromkeys(row[0] for row in rows))[:3],
        columns=COLUMNS,
        rows=[_finding_row(statement, run) for run in runs],
        limitations=_limitations(total, unknown_time),
    )


def _uncounted_reason(unreadable: int, unknown_batch: int) -> str | None:
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
    return " ".join(reasons) or None


def evaluate(snapshot: Snapshot) -> Evaluation:
    requests = project_requests(snapshot, "sql")
    routes, route_eligible, unreadable, unknown_batch = _group_writes(requests)
    findings = [
        _finding(route, statement, runs, route_eligible[route])
        for route, statements in routes.items()
        for statement, runs in statements.items()
    ]
    return Evaluation(len(requests), findings, _uncounted_reason(unreadable, unknown_batch))
