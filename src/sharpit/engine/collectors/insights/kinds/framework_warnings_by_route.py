"""``framework-warnings-by-route``: BootUI ``E/insights/FrameworkWarningsByRoute.java:83-330``.

``WARN`` and ``ERROR`` events that framework loggers wrote while serving a request, grouped by logger, message template
and route; framework ``ERROR`` events that carried no request id are counted in one row of their own. Everything is read
from the ``log`` event as the log handler wrote it (``logger``, ``level``, masked ``template``): never an argument.

Deviations (proposed, ``w5c-K2b.tsv``): the framework loggers are Python's (``FRAMEWORK_LOGGERS``), matched on a whole
dotted name, and the uvicorn loggers count only uvicorn's own messages (apps log through ``uvicorn.error``); the known
messages are the ERROR ones asyncio, SQLAlchemy and uvicorn write (a WARN carries no request id and is never counted
without one, so a known WARN could not show); there is no ``Resolved [`` rule (Spring MVC's note has no Python
counterpart); the "written just after a failed request on its thread" rule is not ported (a request id rides a context
variable, and one event-loop thread serves many requests, so a thread says nothing about ownership): every id-less
framework ``ERROR`` is counted, which includes the "Exception in ASGI application" line uvicorn writes after the
request id is reset, so an unhandled 500 is also in Exception hotspots; a log event joins a request by its request id
only, as in BootUI (its trace id does not); an object address is dropped from a message's group key; there is no
previous run to compare with.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, ids_withheld, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import carried, counted, quoted, stable_hash, unit

KIND = "framework-warnings-by-route"
TITLE = "Framework warnings by route"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"log"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = True

SOURCE = "log"
NO_REQUEST = "No request"
UNKNOWN_MESSAGE = "It is a WARN message sharpit has no specific check for."
ERROR = "ERROR"
NOT_COMPARED = "Not compared with the previous run: sharpit keeps no previous-run summary."
# The logger names counted as framework loggers, each a whole dotted name or its children. Derived from what a FastAPI
# app logs below the application: the servers (uvicorn, gunicorn, hypercorn: BootUI's Tomcat/Netty/Undertow), the web
# stack (starlette, fastapi: spring-web), the database layer (sqlalchemy, alembic: Hibernate, HikariCP), the async
# runtime (asyncio, anyio: reactor, Vert.x) and the HTTP clients (httpx, httpcore).
FRAMEWORK_LOGGERS = (
    "uvicorn", "gunicorn", "hypercorn", "starlette", "fastapi", "sqlalchemy", "alembic", "asyncio", "anyio", "httpx",
    "httpcore", "urllib3", "aiohttp",
)  # fmt: skip
# Apps log through ``uvicorn.error`` as the server's own idiom, so the uvicorn loggers count only the server's messages.
# BootUI's prefixes are Java packages an app does not log under; this narrowing has no counterpart there.
UVICORN = "uvicorn"
UVICORN_MESSAGES = (
    "Exception in ASGI application",
    "Exception in 'lifespan' protocol",
    "ASGI callable returned without",
)
KNOWN: dict[str, str] = {  # a fragment of the template -> its check
    "non-checked-in connection": (
        "A connection was garbage-collected without being returned to the pool: close the session or connection on "
        "every path, including errors; see Connections per request."
    ),
    "Task exception was never retrieved": (
        "A task failed and nothing awaited it, so its error was dropped: await the task, or give it a done callback "
        "that handles the exception."
    ),
    "Exception in ASGI application": (
        "An exception escaped the application and the server logged it: see Exception hotspots for the request's "
        "exception group."
    ),
}
LIMITATIONS = [
    "Counts WARN and ERROR events written while the request's id was current, by the event's request id only; a "
    "warning logged outside the request's context is not counted.",
    NOT_COMPARED,
]
OPEN_LOG_TAIL = (
    "Open Log Tail and filter on the logger to read these errors with their stack traces: a failure the server logged "
    "after a request ended, or work outside any request."
)

# a UUID with the request counter some frameworks append; a hexadecimal id of 16+ characters holding letters and
# digits; a path segment that is a number
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:-\d+)?\b")
_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]+\b")  # an object's address: each leaked connection has its own
_HEX_ID = re.compile(r"\b(?=[0-9a-fA-F]*[a-fA-F])(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{16,}\b")
_NUMERIC_SEGMENT = re.compile(r"(?<=/)\d+(?=[/?#\s,;:]|$)")


def message_key(template: str | None) -> str | None:
    """A message without the parts that differ between the events of one message: ids and numeric path segments."""
    if template is None:
        return None
    return _NUMERIC_SEGMENT.sub("<n>", _HEX_ID.sub("<id>", _UUID.sub("<id>", _ADDRESS.sub("<addr>", template))))


def is_framework(event: dict[str, object]) -> bool:
    logger = event.get("logger")
    if not isinstance(logger, str) or not any(
        logger == prefix or logger.startswith(f"{prefix}.") for prefix in FRAMEWORK_LOGGERS
    ):
        return False
    if logger != UVICORN and not logger.startswith(f"{UVICORN}."):
        return True
    return any(fragment in (_template(event) or "") for fragment in UVICORN_MESSAGES)


def not_applicable(snapshot: Snapshot) -> str | None:
    return ids_withheld(snapshot, "warnings cannot be placed on a route")


def _template(event: dict[str, object]) -> str | None:
    template = event.get("template")
    return template if isinstance(template, str) else None


def _checks(template: str) -> list[str]:
    found: list[str] = []
    for fragment, check in KNOWN.items():
        if fragment in template and check not in found:
            found.append(check)
    return found


@dataclass
class _Group:
    logger: str
    level: str
    template: str | None
    rows: list[list[str]] = field(default_factory=list[list[str]])
    events: int = 0

    def add(self, request: Request, count: int) -> None:
        self.events += count
        self.rows.append([request.request_id, str(request.status or 0), str(count), self.logger])


def _groups(requests: list[Request]) -> dict[str, _Group]:
    groups: dict[str, _Group] = {}
    for request in requests:
        counts: dict[str, int] = {}
        for event in request.children.get(SOURCE, ()):
            if not event.get("requestId") or not is_framework(event):  # BootUI joins logs by request id only
                continue
            logger = event["logger"]
            level, template = str(event.get("level")), _template(event)
            key = f"{logger}\n{level}\n{message_key(template)}"
            groups.setdefault(key, _Group(str(logger), level, template))
            counts[key] = counts.get(key, 0) + 1
        for key, count in counts.items():
            groups[key].add(request, count)
    return groups


def _finding(route: str, key: str, group: _Group, eligible: int) -> Finding:
    template = group.template or ""
    shown = None if group.template is None else message_key(group.template)
    sentence = (
        f"`{route}` logged `{group.level}` from `{group.logger}` in {len(group.rows)} of "
        f"{counted(eligible, unit(route))} ({counted(group.events, 'event')})"
        + ("." if shown is None else f': "{carried(shown)}".')
    )
    checks = _checks(template)
    finding = Finding(
        key=f"{route}:{stable_hash(key)}", subject=route, sufficient=True, sentence=sentence, eligible=eligible,
        affected=len(group.rows),
        what_to_check=[*checks, "Open one of these requests in Live Activity to read the message with its context."],
        exemplar_request_ids=[row[0] for row in group.rows[:3]],
        columns=["Request", "Status", "Events", "Logger"], rows=group.rows, limitations=LIMITATIONS,
    )  # fmt: skip
    return finding if checks or group.level == ERROR else replace(finding, unlisted=UNKNOWN_MESSAGE)


def _unowned(snapshot: Snapshot) -> Finding | None:
    """One row counting the framework ``ERROR`` events that carried no request id, by logger and template."""
    counts: dict[str, int] = {}
    first: dict[str, dict[str, object]] = {}
    for event in snapshot.records.get(SOURCE, ()):
        if event.get("requestId") or str(event.get("level")) != ERROR or not is_framework(event):
            continue
        key = f"{event['logger']}\n{message_key(_template(event))}"
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, event)
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda item: -item[1])  # stable: ties keep their first-seen order
    rows: list[list[str]] = []
    checks: list[str] = []
    for key, n in ranked:
        template = _template(first[key])
        shown = None if template is None else message_key(template)
        rows.append([str(first[key]["logger"]), "" if shown is None else quoted(shown), str(n)])
        checks += [c for c in _checks(template or "") if c not in checks][: 2 - len(checks)]
    total = sum(counts.values())
    top = first[ranked[0][0]]
    sentence = (
        f"Framework loggers wrote {counted(total, '`ERROR` event')} that carried no request or execution id, from "
        f"{counted(len(ranked), 'message')}; the most frequent from `{top['logger']}`, "
        f"{ranked[0][1]} times."
    )
    return Finding(
        key=NO_REQUEST, subject=NO_REQUEST, sufficient=True, sentence=sentence, eligible=0,
        affected=total,  # no request is eligible, so affected counts the errors, which ranks the row among its kind's
        what_to_check=[*checks, OPEN_LOG_TAIL], exemplar_request_ids=[], columns=["Logger", "Message", "Events"],
        rows=rows,
        limitations=[
            "Counts framework ERROR events written while no request id was current: work outside any request, and "
            "failures the server logged after the request ended (an unhandled 500 is logged this way, so the same "
            "failure is also in Exception hotspots). WARN events without an id are not counted. Its affected count "
            "is those events, not requests.",
            NOT_COMPARED,
        ],
    )  # fmt: skip


def evaluate(snapshot: Snapshot) -> Evaluation:
    by_route: dict[str, list[Request]] = {}
    for request in project_requests(snapshot, SOURCE):
        by_route.setdefault(request.route, []).append(request)
    findings: list[Finding] = []
    for route, requests in by_route.items():
        findings += [_finding(route, key, group, len(requests)) for key, group in _groups(requests).items()]
    if (unowned := _unowned(snapshot)) is not None:
        findings.append(unowned)
    return Evaluation(sum(map(len, by_route.values())), findings)
