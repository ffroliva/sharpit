"""Live Activity and the request profile (F4, spec §7.4): a read-time merge of F1-F3, no buffer of its own.

Port of BootUI ``LiveActivityAssembler`` (entries, severities, KPIs), ``LiveActivityService`` (filters, limit) and
``RequestProfileAssembler`` with ``SqlTraceGrouping``. Rows are correlated by sharpit's request id (spec §9), not by
BootUI's trace id. Each source is read under its own lock and the DTOs are built outside it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from sharpit.engine import sqla
from sharpit.engine.capture.exchanges import DTO_KEYS as EXCHANGE_KEYS
from sharpit.engine.capture.sqltrace import entry_dto, normalize_sql

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

ENTRY_KEYS = (
    "id", "type", "timestamp", "severity", "summary", "detail", "durationMs", "correlationId", "method", "path",
    "status", "thread", "profileable", "parentId", "securedPrincipal", "sqlNPlusOneSuspected",
)  # fmt: skip
KPI_KEYS = (
    "requestsPerMinute", "errorRatePercent", "p50LatencyMs", "p95LatencyMs", "slowestEndpoint", "slowestEndpointMs",
    "activeExceptionCount", "sqlPerMinute", "slowestQueryMs", "healthStatus", "heapUsedBytes", "heapMaxBytes",
    "cacheHitRatioPercent", "scheduledTaskFailureCount", "restCallErrorRatePercent", "restCallP95LatencyMs",
)  # fmt: skip
REPORT_KEYS = ("available", "entries", "typeCounts", "kpis", "sources", "warnings", "pageInfo", "persistenceOption")
PROFILE_KEYS = (
    "available", "unavailableReason", "request", "sql", "sqlGroups", "sqlCorrelationApproximate", "exceptions",
    "security", "trace", "timing", "notes",
)  # fmt: skip
EVICTED = "Request is no longer in the buffer"
NO_SOURCE = "Live Activity has no source: request capture is not installed and no other source is available"
APPROXIMATE = (
    "Some statements finished after the response was sent (for example in BackgroundTasks); they are listed here "
    "because they ran under this request's id."
)
MAX_SQL_SUMMARY = 160
MAX_CALL_SITES = 5


def _sources(ctx: SharpitContext) -> tuple[dict[str, Any], list[str]]:
    """Source name -> its buffer, for the sources that are on and available; plus the warnings for the rest."""
    capture = ctx.capture
    found: dict[str, Any] = {}
    warnings: list[str] = []
    exchanges = capture.exchanges
    if exchanges is not None:
        if exchanges.unavailable_reason is None:
            found["requests"] = exchanges
        else:
            warnings.append(f"Requests: {exchanges.unavailable_reason}")
    store = capture.exceptions
    if store is not None and store.unavailable_reason is None:
        found["exceptions"] = store
    recorder = capture.sql_trace  # exists only while the sql-trace panel and SQL tracing are on
    if recorder is not None:
        reason = sqla.unavailable_reason()
        if reason is None:
            found["sql"] = recorder
        else:
            warnings.append(f"SQL: {reason}")
    return found, warnings


def unavailable_reason(ctx: SharpitContext) -> str | None:
    """None while at least one source is on and available (spec §13.1)."""
    found, warnings = _sources(ctx)
    if found:
        return None
    exchanges = ctx.capture.exchanges
    if exchanges is not None and exchanges.unavailable_reason is not None:
        return exchanges.unavailable_reason
    return warnings[0] if warnings else NO_SOURCE


def _percentile(sorted_values: list[int], p: int) -> int | None:
    if not sorted_values:
        return None
    index = math.ceil(p / 100 * len(sorted_values)) - 1
    return sorted_values[max(0, min(index, len(sorted_values) - 1))]


def _per_minute(stamps_ms: list[int]) -> float:
    """``LiveActivityService.perMinute``: count over the span, a span shorter than a second counts as one second."""
    if len(stamps_ms) < 2:
        return float(len(stamps_ms))
    span = max(stamps_ms) - min(stamps_ms)
    if span <= 0:
        return float(len(stamps_ms))
    return len(stamps_ms) / max(span / 60_000, 1 / 60)


def _summarize_sql(category: str, sql: str) -> str:
    """``LiveActivityAssembler.summarizeSql`` + ``truncate``: the category prefix only when it adds information."""
    text = " ".join(sql.split())
    if category and not text.lower().startswith(category.lower()):
        text = f"{category} {text}" if text else category
    return text if len(text) <= MAX_SQL_SUMMARY else text[:MAX_SQL_SUMMARY] + "…"


def _groups(rows: Iterable[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    """``SqlTraceGrouping.group`` over normalised SQL: executions first, N+1 = a SELECT run ``threshold`` times."""
    by_sql: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = normalize_sql(row["sql"])
        group = by_sql.get(key)
        if group is None:
            group = by_sql[key] = {
                "sql": key,
                "category": row["category"] or "OTHER",
                "executions": 0,
                "totalDurationMillis": 0,
                "maxDurationMillis": 0,
                "potentialNPlusOne": False,
                "callSites": [],
            }
        group["executions"] += 1
        group["totalDurationMillis"] += row["durationMillis"]
        group["maxDurationMillis"] = max(group["maxDurationMillis"], row["durationMillis"])
        site = row["callSite"]
        if site is not None and site not in group["callSites"] and len(group["callSites"]) < MAX_CALL_SITES:
            group["callSites"].append(site)
    groups = sorted(by_sql.values(), key=lambda g: -g["executions"])
    for group in groups:
        group["potentialNPlusOne"] = group["category"] == "SELECT" and group["executions"] >= threshold
    return groups


def _entry(**fields: Any) -> dict[str, Any]:
    entry: dict[str, Any] = dict.fromkeys(ENTRY_KEYS)
    return {**entry, "profileable": False, "sqlNPlusOneSuspected": False, **fields}


def activity_report(
    ctx: SharpitContext, type: str | None, severity: str | None, since: int | None, limit: int | None, q: str | None
) -> dict[str, Any]:
    """``LiveActivityReport``, newest first; ``typeCounts`` and KPIs count every entry, before the filters."""
    settings = ctx.settings
    found, warnings = _sources(ctx)
    exchanges: list[dict[str, Any]] = found["requests"].rows() if "requests" in found else []
    groups: list[dict[str, Any]] = found["exceptions"].report()["groups"] if "exceptions" in found else []
    statements: list[dict[str, Any]] = found["sql"].rows() if "sql" in found else []
    request_ids = {r["id"] for r in exchanges}
    sql_by_request: dict[str, list[dict[str, Any]]] = {}
    for row in statements:
        if row["traceId"] is not None:
            sql_by_request.setdefault(row["traceId"], []).append(row)

    entries: list[dict[str, Any]] = []
    slow_ms = settings.activity_request_slow_threshold_ms
    for r in exchanges:
        status, duration = r["status"], r["durationMs"]
        level = "ERROR" if status >= 500 else "WARN" if status >= 400 else "SLOW" if duration >= slow_ms else "OK"
        n_plus_one = any(
            g["potentialNPlusOne"]
            for g in _groups(sql_by_request.get(r["id"], ()), settings.activity_n_plus_one_threshold)
        )
        entries.append(
            _entry(
                id=r["id"],
                type="REQUEST",
                timestamp=r["startNs"] // 1_000_000,
                severity=level,
                summary=f"{r['method']} {r['path']}",
                detail=f"{status} · {duration}ms",
                durationMs=duration,
                correlationId=r["id"],
                method=r["method"],
                path=r["path"],
                status=status,
                profileable=True,
                securedPrincipal=r["principal"],
                sqlNPlusOneSuspected=n_plus_one,
            )
        )
    for s in statements:
        rid = s["traceId"]
        entries.append(
            _entry(
                id=f"sql-{s['id']}",
                type="SQL",
                timestamp=s["timestamp"] // 1_000_000,
                severity="ERROR" if not s["success"] else "SLOW" if s["slow"] else "OK",
                summary=_summarize_sql(s["category"], s["sql"]),
                detail=None if s["success"] else s["errorMessage"],
                durationMs=s["durationMillis"],
                correlationId=rid,
                thread=s["thread"],
                parentId=rid if rid in request_ids else None,
            )
        )
    for g in groups:
        rid = g["lastTraceId"]
        detail = g["location"]
        if g["count"] > 1:
            detail = f"{detail or ''} ×{g['count']}".strip()
        entries.append(
            _entry(
                id=f"exc-{g['id']}",
                type="EXCEPTION",
                timestamp=g["lastSeen"],
                severity="ERROR",
                summary=g["exceptionClassName"] + (f": {g['message']}" if g["message"] is not None else ""),
                detail=detail,
                correlationId=rid,
                method=g["lastRequestMethod"],
                path=g["lastRequestPath"],
                thread=g["lastThread"],
                parentId=rid if rid in request_ids else None,
            )
        )
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    type_counts: dict[str, int] = {}
    for entry in entries:
        type_counts[entry["type"]] = type_counts.get(entry["type"], 0) + 1

    cap = settings.activity_max_entries if not limit or limit <= 0 else min(limit, settings.activity_max_entries)
    wanted_type = (type or "").strip().upper()
    wanted_severity = (severity or "").strip().upper()
    needle = (q or "").strip().lower()
    visible: list[dict[str, Any]] = []
    for entry in entries:
        if len(visible) >= cap:
            break
        if (
            entry["timestamp"] <= (since or 0)
            or (wanted_type and entry["type"] != wanted_type)
            or (wanted_severity and entry["severity"] != wanted_severity)
        ):
            continue
        if needle and not any(
            needle in str(entry[k]).lower() for k in ("summary", "detail", "path", "correlationId") if entry[k]
        ):
            continue
        visible.append(entry)

    durations = sorted(r["durationMs"] for r in exchanges)
    slowest = max(exchanges, key=lambda r: r["durationMs"], default=None)
    errors = sum(r["status"] >= 400 for r in exchanges)
    kpis = {
        "requestsPerMinute": round(_per_minute([r["startNs"] // 1_000_000 for r in exchanges]), 2),
        "errorRatePercent": round(100 * errors / len(exchanges), 2) if exchanges else 0.0,
        "p50LatencyMs": _percentile(durations, 50),
        "p95LatencyMs": _percentile(durations, 95),
        "slowestEndpoint": slowest["path"] if slowest else None,
        "slowestEndpointMs": slowest["durationMs"] if slowest else None,
        "activeExceptionCount": sum(g["status"] == "OPEN" for g in groups),
        "sqlPerMinute": round(_per_minute([s["timestamp"] // 1_000_000 for s in statements]), 2),
        "slowestQueryMs": max((s["durationMillis"] for s in statements), default=None),
        "healthStatus": None,  # TODO(Task 7): the last cached Health status
        "heapUsedBytes": None,
        "heapMaxBytes": None,
        "cacheHitRatioPercent": None,
        "scheduledTaskFailureCount": 0,
        "restCallErrorRatePercent": None,
        "restCallP95LatencyMs": None,
    }
    return {
        "available": bool(found),
        "entries": visible,
        "typeCounts": type_counts,
        "kpis": kpis,
        "sources": list(found),
        "warnings": warnings,
        "pageInfo": None,
        "persistenceOption": None,
    }


def _unavailable_profile(reason: str) -> dict[str, Any]:
    """``RequestProfileDto.unavailable``."""
    profile: dict[str, Any] = dict.fromkeys(PROFILE_KEYS)
    profile.update(
        available=False, unavailableReason=reason, sql=[], sqlGroups=[], sqlCorrelationApproximate=False,
        exceptions=[], security=[], notes=[],
    )  # fmt: skip
    return profile


def request_profile(ctx: SharpitContext, request_id: str) -> dict[str, Any]:
    """``RequestProfileDto``: what one request did, from the rows that carry its request id."""
    found, _ = _sources(ctx)
    row = found["requests"].get(request_id) if "requests" in found else None
    if row is None:
        return _unavailable_profile(EVICTED)
    request = {k: row[k] for k in EXCHANGE_KEYS}
    if not ctx.settings.panels["http-exchanges"].enabled:  # the headers belong to that panel (spec §7.4)
        request.update(requestHeaders=[], responseHeaders=[])
    statements = [s for s in found["sql"].rows() if s["traceId"] == request_id] if "sql" in found else []
    approximate = any(s["timestamp"] > row["endNs"] for s in statements)
    sql_ms = sum(s["durationMillis"] for s in statements)
    total = row["durationMs"]
    return {
        "available": True,
        "unavailableReason": None,
        "request": request,
        "sql": [entry_dto(s) for s in statements],
        "sqlGroups": _groups(statements, ctx.settings.activity_n_plus_one_threshold),
        "sqlCorrelationApproximate": approximate,
        "exceptions": found["exceptions"].request_occurrences(request_id) if "exceptions" in found else [],
        "security": [],
        "trace": None,
        "timing": {
            "totalMs": total,
            "sqlMs": sql_ms,
            "sqlCount": len(statements),
            "sqlPercent": round(10000 * sql_ms / total) / 100 if total > 0 else None,
        },
        "notes": [APPROXIMATE] if approximate else [],
    }
