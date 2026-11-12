"""``exception-hotspots``: BootUI ``E/insights/ExceptionHotspots.java:83-420``.

The exception groups each route recorded, by their cross-run signature, with a specific check for well-known
exceptions. The default list shows a group when a request of it failed (5xx) or ended in a redirect or status 0, or when
nearly every request of its route answered 4xx with it; groups seen only behind 4xx responses are counted in one row.

Deviations (proposed, ``w5c-K2b.tsv``): sharpit keeps no previous run, so no group is marked "not observed in the
previous run" and every finding's limitations say so; scheduled runs and messages are not projected, so there is no
"caught in completed runs" row; the specific checks are SQLAlchemy's, keyed by ``module.Class`` as ``exceptionClass``
and ``types`` carry it; no ``EXACT_ONLY`` list (it names Jackson wrappers); no WebFlux limitation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, simple_name, stable_hash, unit

KIND = "exception-hotspots"
TITLE = "Exception hotspots"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"exception"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = True

SOURCE = "exception"
GENERIC_CHECK = "Open the exception group to read its message and stack trace."
BEHIND_4XX = "Behind 4xx responses"
ONLY_4XX = (
    f"It was recorded only behind 4xx responses, which are usually intended, and is counted in the row {BEHIND_4XX}."
)
ONLY_2XX_OR_4XX = "It was recorded only behind 2xx and 4xx responses: Errors behind 2xx responses reports the 2xx ones."
EVERY_REQUEST_SHARE = 0.95  # a route on which (nearly) every request fails with one exception may never succeed
EVERY_REQUEST_MIN = 3  # so one rejected request is not a route
EVERY_REQUEST_CHECK = (
    "Every request to this route, or nearly, answered 4xx with this exception: check whether the route can succeed "
    "at all, or whether its callers always send what it rejects."
)
DIFFERING_CAUSES = (
    "This exception group recorded differing causes; only the first two specific checks are listed. Open its "
    "occurrences to inspect the other causes."
)
NO_PREVIOUS_RUN = (
    "Not compared with the previous run: sharpit keeps no previous-run summary, so a group new since then is not "
    "marked."
)
FAILED, CLIENT, SUCCESS, OTHER = "failed", "client", "success", "other"

_ROLLBACK = (
    "If a participating operation failed and the caller caught the exception, the session's transaction was already "
    "marked failed: rethrow it, or run that operation in its own session or a nested transaction if it may fail alone."
)
_OPTIMISTIC = (
    "Two requests updated the same version of a row: decide whether the caller retries, merges, or receives a 409 "
    "Conflict."
)
CHECKS: dict[str, str] = {  # by ``module.Class``, as ``exceptionClass`` and ``types`` carry it
    "sqlalchemy.orm.exc.DetachedInstanceError": (
        "If a lazy attribute is read after its session closed, load it in the query, with selectinload or "
        "joinedload, or build the response inside the session."
    ),
    "sqlalchemy.exc.PendingRollbackError": _ROLLBACK,
    "sqlalchemy.orm.exc.StaleDataError": _OPTIMISTIC,
    "sqlalchemy.exc.IntegrityError": (
        "A database constraint rejected the write: validate the input first, or map the violation to a 4xx response."
    ),
    "sqlalchemy.exc.TimeoutError": (
        "A connection could not be obtained: if the pool timed out, compare Connections per request with the pool "
        "size and look for connections held across slow work; also check database connectivity."
    ),
    "sqlalchemy.exc.MultipleResultsFound": (
        "A query expected one row and found several: check the uniqueness the query assumes."
    ),
    "sqlalchemy.exc.NoResultFound": "A query expected one row and found none: check whether absence should answer 404.",
    "RecursionError": (
        "If serialization recursed through a bidirectional relationship, break the cycle with a response model that "
        "leaves the back-reference out."
    ),  # builtins are recorded without the ``builtins.`` prefix
}


def not_applicable(snapshot: Snapshot) -> str | None:
    return ids_withheld(snapshot, "exceptions")


def _status_class(status: int | None) -> str:
    code = status or 0  # status 0, no response recorded, counts as other: listed, since nothing says it was intended
    if code >= 500:
        return FAILED
    if 400 <= code < 500:
        return CLIENT
    return SUCCESS if 200 <= code < 300 else OTHER


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


@dataclass
class _Group:
    name: str
    rows: list[list[str]] = field(default_factory=list[list[str]])
    checks: list[str] = field(default_factory=list[str])
    classes: set[str] = field(default_factory=set[str])
    occurrences: int = 0

    def observe(self, event: dict[str, object]) -> None:
        """The first of the event's types with a check (deepest cause first), else its own class's."""
        types = event.get("types")
        names = [t for t in cast("list[object]", types) if isinstance(t, str)] if isinstance(types, list) else []
        specific = next((CHECKS[n] for n in names if n in CHECKS), None)
        specific = specific or CHECKS.get(_text(event.get("exceptionClass")) or "")
        if specific and specific not in self.checks:
            self.checks.append(specific)

    def add(self, request: Request, count: int, group_id: str) -> None:
        self.occurrences += count
        self.classes.add(_status_class(request.status))
        self.rows.append([request.request_id, str(request.status or 0), str(count), group_id])

    def on_every_request(self, eligible: int) -> bool:
        return (
            self.classes == {CLIENT}
            and len(self.rows) >= EVERY_REQUEST_MIN
            and len(self.rows) >= eligible * EVERY_REQUEST_SHARE
        )

    def unlisted(self) -> str | None:
        """Why the default list leaves this group out, or ``None`` when it is listed."""
        if self.classes & {FAILED, OTHER}:
            return None
        if SUCCESS in self.classes:
            return ONLY_2XX_OR_4XX
        return ONLY_4XX if CLIENT in self.classes else None


def _groups(requests: list[Request]) -> dict[str, _Group]:
    groups: dict[str, _Group] = {}
    for request in requests:
        counts: dict[str, int] = {}
        ids: dict[str, str] = {}
        for event in request.children.get(SOURCE, ()):
            key = _text(event.get("signature")) or _text(event.get("groupId"))
            if key is None:
                continue
            group = groups.setdefault(key, _Group(simple_name(event.get("exceptionClass"))))
            group.observe(event)
            counts[key] = counts.get(key, 0) + 1
            ids[key] = _text(event.get("groupId")) or ""
        for key, count in counts.items():
            groups[key].add(request, count, ids[key])
    return groups


def _finding(route: str, key: str, group: _Group, eligible: int) -> Finding:
    every = group.on_every_request(eligible)
    sentence = (
        f"`{route}` recorded `{group.name}` in {len(group.rows)} of {counted(eligible, unit(route))} "
        f"({counted(group.occurrences, 'occurrence')})."
    )
    checks = [*([EVERY_REQUEST_CHECK] if every else []), *group.checks[: 1 if every else 2], GENERIC_CHECK]
    finding = Finding(
        key=f"{route}:{stable_hash(key)}", subject=route, sufficient=True, sentence=sentence, eligible=eligible,
        affected=len(group.rows), what_to_check=checks, exemplar_request_ids=[row[0] for row in group.rows[:3]],
        columns=["Request", "Status", "Occurrences", "Exception group"], rows=group.rows,
        limitations=[*([DIFFERING_CAUSES] if len(group.checks) > 2 else []), NO_PREVIOUS_RUN],
    )  # fmt: skip
    return finding if every else replace(finding, unlisted=group.unlisted())


def _behind_4xx(named: list[tuple[Finding, str]]) -> Finding | None:
    """One row counting the groups the default list leaves out because they were seen only behind 4xx responses. It
    names no request as eligible or affected, so it sorts after the groups it does not collapse."""
    collapsed = [(f, name) for f, name in named if f.unlisted == ONLY_4XX]
    if not collapsed:
        return None
    requests = {row[0] for f, _ in collapsed for row in f.rows}
    occurrences = [sum(int(row[2]) for row in f.rows) for f, _ in collapsed]
    rows = [
        [f.subject, name, str(f.affected), str(n), ", ".join(sorted({row[1] for row in f.rows}))]
        for (f, name), n in zip(collapsed, occurrences, strict=True)
    ]
    rows.sort(key=lambda row: -int(row[3]))
    routes = counted(len({f.subject for f, _ in collapsed}), "route")
    groups = counted(len(collapsed), "exception group")
    return Finding(
        key=BEHIND_4XX, subject=BEHIND_4XX, sufficient=True,
        sentence=f"{groups} on {routes} {'was' if len(collapsed) == 1 else 'were'} recorded only behind 4xx "
        f"responses: {counted(sum(occurrences), 'occurrence')} in {counted(len(requests), 'request')}.",
        eligible=0, affected=0,
        what_to_check=[
            "Check that each of these 4xx responses is the one the caller should get, such as 400 for invalid input; "
            "Show all routes lists each group with its requests.",
            GENERIC_CHECK,
        ],
        exemplar_request_ids=[f.exemplar_request_ids[0] for f, _ in collapsed if f.exemplar_request_ids][:3],
        columns=["Route", "Exception", "Requests", "Occurrences", "Statuses"], rows=rows,
        limitations=["A group also seen behind a 5xx response, a redirect, or a 2xx response is not counted here."],
    )  # fmt: skip


def evaluate(snapshot: Snapshot) -> Evaluation:
    by_route: dict[str, list[Request]] = {}
    for request in project_requests(snapshot, SOURCE):
        by_route.setdefault(request.route, []).append(request)
    named: list[tuple[Finding, str]] = []
    for route, requests in by_route.items():
        named += [(_finding(route, key, group, len(requests)), group.name) for key, group in _groups(requests).items()]
    findings = [f for f, _ in named]
    if (row := _behind_4xx(named)) is not None:
        findings.append(row)
    return Evaluation(sum(map(len, by_route.values())), findings)
