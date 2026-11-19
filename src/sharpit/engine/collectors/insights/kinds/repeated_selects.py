"""``repeated-selects``: BootUI ``E/insights/RepeatedSelects.java:77,152-186``.

The finding names a statement shape because SQL names and values can trigger the free-text masker.
"""

from __future__ import annotations

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, stable_hash

KIND = "repeated-selects"
TITLE = "Repeated SELECTs"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = True

MIN_REPEATS = 5
MIN_REQUESTS = 3


def _start(event: dict[str, object]) -> tuple[int, int]:
    completed, duration = event.get("completedNanos"), event.get("durationNanos")
    epoch = event.get("epochMillis")
    return (
        completed - duration
        if isinstance(completed, int) and isinstance(duration, int) and completed >= 0 and duration >= 0
        else 2**63 - 1,
        epoch if isinstance(epoch, int) else 0,
    )


def evaluate(snapshot: Snapshot) -> Evaluation:
    groups: dict[tuple[str, str], list[tuple[str, int, int, str]]] = {}
    eligible: dict[str, int] = {}
    requests = project_requests(snapshot, "sql")
    for request in requests:
        events = sorted(
            request.children["sql"],
            key=_start,
        )
        first: str | None = None
        counts: dict[str, list[tuple[str, int, int, str]]] = {}
        for event in events:
            sql = event.get("sql")
            if not isinstance(sql, str) or event.get("failed") is True or event.get("provenance") != "EXECUTION":
                continue
            shape = " ".join(sql.split())
            fingerprint = stable_hash(shape)
            first = first or fingerprint
            if not shape.lower().startswith("select") or fingerprint == first:
                continue
            duration = event.get("durationNanos")
            site = event.get("callSite")
            counts.setdefault(fingerprint, []).append(
                (
                    request.request_id,
                    max(0, duration) if isinstance(duration, int) else 0,
                    duration if isinstance(duration, int) and duration > 0 else -1,
                    site if isinstance(site, str) else "",
                )
            )
        if any(count >= MIN_REPEATS for count in map(len, counts.values())):
            eligible[request.route] = eligible.get(request.route, 0) + 1
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
            f"{len(runs)} of {counted(eligible.get(route, 0), 'request')}, up to {len(runs[0])} times in one."
            if sufficient
            else f"`{route}`: {len(runs)} of {MIN_REQUESTS} requests needed to report {first_event_shape} "
            f"repeated {MIN_REPEATS} or more times."
        )
        measured = all(row[2] >= 0 for row in rows)
        total = sum(row[1] for row in rows)
        limitations = [
            "Counts statements the request ran; a statement Hibernate batches counts once.",
            "JDBC row counts, when known, do not establish how many entities or response items a query produced.",
            (
                "SQL text in findings is named as a statement shape because secret-looking names can mask "
                "the rest of a sentence."
            ),
            "Sharpit records no transaction events for this check; repeats are counted per request.",
            "Total repeat time is "
            + (f"{total / 1_000_000:.1f} ms, summed across affected requests." if measured else "unknown."),
        ]
        findings.append(
            Finding(
                key=f"{route}:{fingerprint}",
                subject=route,
                sufficient=sufficient,
                sentence=sentence,
                eligible=eligible.get(route, 0),
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
                        "unknown" if any(r[2] < 0 for r in run) else str(sum(r[1] for r in run) / 1_000_000),
                        run[0][3],
                    ]
                    for run in runs
                ],
                limitations=limitations,
            )
        )
    return Evaluation(len(requests), findings)
