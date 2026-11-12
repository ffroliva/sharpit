"""``safe-method-dml``: BootUI ``E/insights/SafeMethodDml.java:26-43``. A GET or HEAD request that executed an INSERT,
UPDATE, DELETE or MERGE, per route; worded as a question, since an audit write is often intended.

Deviations (proposed, by field):
- ``sql``: the journal holds the masked statement shape, never the statement (quoted names become ``?`` and text is cut
  at ``#``), so statements are not told apart: BootUI's finding per route and statement fingerprint is one finding per
  route, naming the verbs (the first keyword, read only from a closed list), and the statement is never shown. A text
  that is not a readable statement (the mask marker, the unsupported marker, none) is counted apart and the check says
  so, never read as "not a write".
- ``provenance``: only ``EXECUTION`` is counted. sharpit writes no ``PREPARATION`` (BootUI's Quarkus preparation and the
  ``orm`` read are Quarkus only, OQ-I6), so the prepared branch and its two limitations are absent.
- the first keyword is a word (``[A-Za-z]+``), not BootUI's ``startsWith``: ``updated_at = ?`` is no update.
"""

from __future__ import annotations

import re

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import Request, project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, stable_hash
from sharpit.engine.sqltext import MASK, UNSUPPORTED_STATEMENT

KIND = "safe-method-dml"
TITLE = "Writes in GET requests"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "sql"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = True

SAFE_METHODS = frozenset({"GET", "HEAD"})  # ``ProjectedRequest.safeMethod``
DML = ("insert", "update", "delete", "merge")  # ``SafeMethodDml.isDml``
UNREADABLE = frozenset({MASK, UNSUPPORTED_STATEMENT})
FIRST_WORD = re.compile(r"\s*([A-Za-z]+)")
IDS_WITHHELD = (
    "Request ids are withheld at METADATA_ONLY exposure, so writes cannot be placed in a request "
    "(SHARPIT_EXPOSE_VALUES)."
)
LIMITATIONS = (
    "Counts statements the database executed successfully; a write that failed is not listed.",
    "sharpit's journal holds each statement's masked statement shape, not the statement, so a route's writes are "
    "reported together by verb, not one finding per statement.",
)
CHECKS = [
    "If the caller asked for this change, expose it as POST, PUT, PATCH, or DELETE, since caches, crawlers, "
    "prefetchers, and retries may repeat a GET.",
    "If it is an audit or counter write, check that repeating the request is harmless.",
]
COLUMNS = ["Request", "Status", "Executions", "Call site"]


def not_applicable(snapshot: Snapshot) -> str | None:
    """http records exist but none names a request id: the exposure withheld them, so no write can be placed."""
    return IDS_WITHHELD if snapshot.records.get("http") and not snapshot.requests else None


def _readable(text: object) -> bool:
    return isinstance(text, str) and bool(text.strip()) and text not in UNREADABLE


def _verb(text: str) -> str | None:
    """The DML verb a statement starts with, else ``None``."""
    word = FIRST_WORD.match(text)
    return word.group(1).lower() if word and word.group(1).lower() in DML else None


def _writes(request: Request) -> tuple[list[tuple[str, str]], int]:
    """The request's executed writes as (verb, call site), and how many statements could not be read."""
    found: list[tuple[str, str]] = []
    unread = 0
    for event in request.children["sql"]:
        if event.get("provenance") != "EXECUTION" or event.get("failed") is True:
            continue
        text = event.get("sql")
        if not _readable(text):
            unread += 1
        elif verb := _verb(str(text)):
            site = event.get("callSite")
            found.append((verb.upper(), site if isinstance(site, str) else ""))
    return found, unread


def _finding(route: str, hits: list[tuple[Request, list[tuple[str, str]]]], eligible: int) -> Finding:
    verbs = list(dict.fromkeys(verb for _, writes in hits for verb, _ in writes))
    n = len(hits)
    return Finding(
        key=f"{route}:{stable_hash(route)}", subject=route, sufficient=True,
        sentence=f"`{route}` executed {'a write' if len(verbs) == 1 else 'writes'} ({', '.join(verbs)}) in {n} of "
        f"{counted(eligible, 'request')}: an incidental write, such as an audit or a counter, or a change the caller "
        "asked for?",
        eligible=eligible, affected=n, what_to_check=CHECKS,
        exemplar_request_ids=[r.request_id for r, _ in hits[:3]], columns=COLUMNS,
        rows=[[r.request_id, str(r.status), str(len(writes)), writes[0][1]] for r, writes in hits],
        limitations=list(LIMITATIONS),
    )  # fmt: skip


def evaluate(snapshot: Snapshot) -> Evaluation:
    by_route: dict[str, list[Request]] = {}
    for request in project_requests(snapshot, "sql"):
        if (request.method or "").upper() in SAFE_METHODS:
            by_route.setdefault(request.route, []).append(request)
    findings: list[Finding] = []
    unread = 0
    for route, safe in by_route.items():
        hits: list[tuple[Request, list[tuple[str, str]]]] = []
        for request in safe:
            writes, skipped = _writes(request)
            unread += skipped
            if writes:
                hits.append((request, writes))
        if hits:
            findings.append(_finding(route, hits, len(safe)))
    uncounted = None
    if unread:
        uncounted = (
            f"{counted(unread, 'statement')} in a GET or HEAD request could not be read as a statement, so "
            f"{'it is' if unread == 1 else 'they are'} not counted as writes."
        )
    return Evaluation(sum(map(len, by_route.values())), findings, uncounted)
