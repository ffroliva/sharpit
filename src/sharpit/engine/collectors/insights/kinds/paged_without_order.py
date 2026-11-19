"""``paged-without-order``: BootUI ``E/insights/PagedWithoutOrder.java``."""

from __future__ import annotations

import re

from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.requests import project_requests
from sharpit.engine.collectors.insights.snapshot import Snapshot
from sharpit.engine.collectors.insights.text import counted, stable_hash

KIND = "paged-without-order"
TITLE = "Paged without ORDER BY"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = True

_LIMIT = re.compile(r"\b(limit|fetch\s+first|fetch\s+next|top)\s+(?:\?|\d+)", re.IGNORECASE)
_UNSUPPORTED = re.compile(r"\b(union|intersect|except)\b", re.IGNORECASE)
_EQUALITY_ONLY = re.compile(r"\bwhere\b(?:(?!\border\s+by\b).)*(?=\blimit\b|\bfetch\b|\btop\b)", re.IGNORECASE)


def _candidate(sql: object) -> bool:
    if (
        not isinstance(sql, str)
        or not sql.strip()
        or sql.endswith("…")
        or not sql.lstrip().lower().startswith("select")
    ):
        return False
    if not _LIMIT.search(sql) or re.search(r"\border\s+by\b", sql, re.IGNORECASE) or _UNSUPPORTED.search(sql):
        return False
    if re.search(r"\b(count|exists)\s*\(|^\s*select\s+(?:\d+|true|false)\b", sql, re.IGNORECASE):
        return False
    if re.search(r"\boffset\s+(?:\?|\d+)", sql, re.IGNORECASE):
        return True
    where = _EQUALITY_ONLY.search(sql)
    return where is None or bool(
        re.search(r"(?:<>|!=|>=|<=|>|<|\bor\b|\blike\b|\bin\s*\()", where.group(), re.IGNORECASE)
    )


def evaluate(snapshot: Snapshot) -> Evaluation:
    groups: dict[tuple[str, str], dict[str, tuple[int, str]]] = {}
    requests = project_requests(snapshot, "sql")
    for request in requests:
        per_request: dict[str, tuple[int, str]] = {}
        for event in request.children["sql"]:
            sql = event.get("sql")
            if event.get("failed") is True or event.get("provenance") != "EXECUTION" or not _candidate(sql):
                continue
            fingerprint = stable_hash(str(sql))
            count, prior_site = per_request.get(fingerprint, (0, ""))
            site = event.get("callSite")
            per_request[fingerprint] = (
                count + 1,
                prior_site or (site if isinstance(site, str) else ""),
            )
        for fingerprint, value in per_request.items():
            groups.setdefault((request.route, fingerprint), {})[request.request_id] = value
    findings: list[Finding] = []
    for (route, fingerprint), runs in groups.items():
        enough = len(runs) >= 2
        executions = sum(count for count, _ in runs.values())
        sentence = (
            f"`{route}` ran a statement that limits rows without an `ORDER BY`, {counted(executions, 'time')} "
            f"in {counted(len(runs), 'request')}."
            if enough
            else (
                f"`{route}`: {len(runs)} of 2 requests needed to report a statement that limits rows "
                "without an `ORDER BY`."
            )
        )
        findings.append(
            Finding(
                key=f"{route}:{fingerprint}",
                subject=route,
                sufficient=enough,
                sentence=sentence,
                eligible=len([r for r in requests if r.route == route]),
                affected=len(runs),
                what_to_check=[
                    "Add a deterministic `ORDER BY`, with a unique key last, to paged queries.",
                    "If the rows are meant to be arbitrary, such as a sample, this is expected.",
                ],
                exemplar_request_ids=list(runs)[:3],
                columns=["Request", "Executions", "Call site", "Statement"],
                rows=[
                    [request_id, str(count), site, "a paged SELECT statement shape"]
                    for request_id, (count, site) in runs.items()
                ],
                limitations=[
                    "Equality-only key lookups are left out.",
                    "Truncated statements and set operations are left out.",
                    (
                        "SQL text in findings is named as a statement shape because secret-looking names can mask "
                        "the rest of a sentence."
                    ),
                ],
            )
        )
    return Evaluation(len(requests), findings)
