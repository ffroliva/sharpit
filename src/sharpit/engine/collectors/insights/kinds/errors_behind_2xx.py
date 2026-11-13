"""``errors-behind-2xx``: BootUI ``E/insights/ErrorsBehind2xx.java:63-424``.

2xx requests whose own request rolled back its root transaction, recorded an exception, wrote an ``ERROR`` log or
received a 5xx or failed downstream call, strongest evidence first. The evidence events join their request by
``requestId`` and carry BootUI's payload field names (``rolledBack``, ``nested``, ``method``; ``exceptionClass``;
``level``, ``logger``; ``status``, ``failed``, ``authority``, ``method``); no sharpit producer writes those sources
yet, so today the check answers not applicable.

Deviations (proposed): no recovered group, no task-failure evidence and no downstream path, because the
``fault-tolerance``, ``agent.executors`` sources and a path-masking exposure on the rest-client path have no producer;
the finding says so in its limitations. A recorded http source whose ids the exposure withheld is not applicable, as in
``ai-usage-by-route``, not "no eligible work".
"""

from __future__ import annotations

from collections.abc import Callable

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted

KIND = "errors-behind-2xx"
TITLE = "Errors behind 2xx responses"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http"})
TRANSACTION, EXCEPTION_SOURCE, LOG, REST_CLIENT = "transaction", "exception", "log", "rest-client"
IMPLEMENTED = True

EVIDENCE_SOURCES = (TRANSACTION, EXCEPTION_SOURCE, LOG, REST_CLIENT)
OPTIONAL_READS: frozenset[str] = frozenset(EVIDENCE_SOURCES)
MAX_ITEMS = 3  # BootUI ``ErrorsBehind2xx.java:420``: ``.distinct().limit(3)``
NOT_APPLICABLE = (
    "The runtime journal records none of the transaction, exception, log, and rest-client sources, or"
    " their panels are disabled."
)
IDS_WITHHELD = (
    "Request ids are withheld at METADATA_ONLY exposure, so errors cannot be placed behind a request "
    "(SHARPIT_EXPOSE_VALUES)."
)
COLUMNS = ["Request", "Status", "Evidence"]
LIMITATIONS = [
    "Only work that carries the request's id is counted: work handed to another thread without sharpit's correlation "
    "is not.",
    "Recovery by a retry or fallback is not evaluated, so an exception one recovered is still reported as an error; "
    "a task's own failure is not counted apart from the request's.",
]
# (clause after "3 requests", noun in the evidence row), strongest first
ROLLED_BACK, EXCEPTION, ERROR_LOG, DOWNSTREAM = "rolled", EXCEPTION_SOURCE, "error-log", "downstream"
EVIDENCE = {
    ROLLED_BACK: ("whose transaction rolled back", "rolled-back transaction"),
    EXCEPTION: ("that recorded an exception", EXCEPTION_SOURCE),
    ERROR_LOG: ("that wrote an ERROR log", "ERROR log"),
    DOWNSTREAM: ("that received a 5xx or failed downstream call", "downstream 5xx or failure"),
}
_Event = dict[str, object]


def not_applicable(snapshot: Snapshot) -> str | None:
    """No evidence source available (journaled with its panel enabled): BootUI's reason.
    Ids the exposure withheld: no request to place evidence behind."""
    if not any(snapshot.available(source) for source in EVIDENCE_SOURCES):
        return NOT_APPLICABLE
    return IDS_WITHHELD if snapshot.ids_withheld else None


def _simple_name(value: object) -> str:
    return str(value).rsplit(".", 1)[-1] if isinstance(value, str) and value else "?"


def _text(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _downstream(event: _Event) -> str | None:
    status = event.get("status")
    if isinstance(status, int) and not isinstance(status, bool):
        failed = status >= 500
    else:
        status, failed = None, event.get("failed") is True
    if not failed:
        return None
    parts = [
        str(status) if status is not None else "failed",
        *(_text(event.get(k), "") for k in ("method", "authority")),
    ]
    return " ".join(p for p in parts if p)


def _rolled_back(event: _Event) -> str | None:
    rolled = event.get("rolledBack") is True and event.get("nested") is not True
    return _text(event.get("method"), TRANSACTION) if rolled else None


def _error_log(event: _Event) -> str | None:
    return _text(event.get("logger"), "?") if str(event.get("level")).upper() == "ERROR" else None


_BY_SOURCE: dict[str, tuple[str, Callable[[_Event], str | None]]] = {
    TRANSACTION: (ROLLED_BACK, _rolled_back),
    EXCEPTION_SOURCE: (EXCEPTION, lambda event: _simple_name(event.get("exceptionClass"))),
    LOG: (ERROR_LOG, _error_log),
    REST_CLIENT: (DOWNSTREAM, _downstream),
}


def _behind(request: Request) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for source in EVIDENCE_SOURCES:
        for event in request.children.get(source, ()):
            kind, what = _BY_SOURCE[source]
            if (item := what(event)) is not None:
                found.setdefault(kind, []).append(item)
    return {kind: found[kind] for kind in EVIDENCE if kind in found}  # strongest first


def _describe(found: dict[str, list[str]]) -> str:
    return "; ".join(
        f"{EVIDENCE[kind][1]}: {', '.join(list(dict.fromkeys(what))[:MAX_ITEMS])}" for kind, what in found.items()
    )


def _finding(route: str, behind: list[tuple[Request, dict[str, list[str]]]], eligible: int) -> Finding:
    counts = {kind: sum(kind in found for _, found in behind) for kind in EVIDENCE}
    parts = [f"{counted(n, 'request')} {EVIDENCE[kind][0]}" for kind, n in counts.items() if n]
    ordered = sorted(behind, key=lambda pair: list(EVIDENCE).index(next(iter(pair[1]))))
    checks = ["Verify the response contract: should the caller learn that part of this request failed?"]
    if counts[ROLLED_BACK]:
        checks.append("If the transaction rolled back, the response may describe data that was never saved.")
    return Finding(
        key=f"{route}:unrecovered", subject=route, sufficient=True,
        sentence=f"`{route}` answered 2xx in {len(behind)} of {counted(eligible, 'successful request')}: "
        f"{', '.join(parts)}.",
        eligible=eligible, affected=len(behind), what_to_check=checks,
        exemplar_request_ids=[r.request_id for r, _ in ordered[:3]], columns=COLUMNS,
        rows=[[r.request_id, str(r.status), _describe(found)] for r, found in ordered], limitations=LIMITATIONS,
    )  # fmt: skip


def evaluate(snapshot: Snapshot) -> Evaluation:
    by_route: dict[str, list[Request]] = {}
    for request in project_requests(snapshot, *EVIDENCE_SOURCES):
        if request.status is not None and 200 <= request.status < 300:
            by_route.setdefault(request.route, []).append(request)
    findings: list[Finding] = []
    for route, successes in by_route.items():
        behind = [(r, found) for r in successes if (found := _behind(r))]
        if behind:
            findings.append(_finding(route, behind, len(successes)))
    return Evaluation(sum(map(len, by_route.values())), findings)
