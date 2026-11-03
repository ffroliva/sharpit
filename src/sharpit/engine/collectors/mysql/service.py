"""The ``mysql`` panel's report: ``GET`` serves the last read, ``POST /read`` reads every MySQL engine.

Port of BootUI ``MySqlInsightService`` (2.2.0). Each engine is read through ``sqla.run_db_read(read_only=True)``,
whose ``bounded_read_only`` sets session read-only and verifies it. The previous read's metrics live in memory
only (``ctx.lazy``), so ``changes`` appear from the second read on and nothing is ever persisted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sharpit.engine import sqla
from sharpit.engine.collectors.mysql.limits import (
    LOCK_TIMEOUT,
    READ_BUDGET,
    STATEMENT_TIMEOUT,
    ReadBudget,
    RowLimits,
)
from sharpit.engine.collectors.mysql.sections import (
    BUDGET_SKIPPED,
    DataSourceData,
    collect_all,
    compare_changes,
)
from sharpit.engine.daemon_executor import DaemonExecutor
from sharpit.engine.singleflight import ActionBusy, Flight, SingleFlight

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

OPERATION = "mysql-read"
DISCLAIMER = (
    "Explicit, bounded READ ONLY observations of MySQL's own metadata and statistics, not application rows. "
    "Collection is not an atomic snapshot. Server counters include other clients; default-schema association is not "
    "exhaustive schema access. Pool acquisition and network timeouts are separate from the cooperative 15-second read "
    "budget. No health score or complete-history claim."
)
NOT_READ_MESSAGE = "No MySQL read has run. Run MySQL read explicitly to contact existing JDBC datasources."
NO_MYSQL = (
    "No MySQL datasource was found. This panel reads MySQL's own statistics views, "
    "so it has nothing to report for other database products."
)
UNREAD = "The read budget ran out before this datasource was read."
BUDGET_RAN_OUT = "The read budget ran out while reading this datasource."
_LABELS = {
    "sqlite": "SQLite",
    "postgresql": "PostgreSQL",
    "mariadb": "MariaDB",
    "mssql": "SQL Server",
    "oracle": "Oracle",
}

_clock = time.monotonic  # test seam: the read budget's clock
WALL_MARGIN = 1.0

Dto = dict[str, Any]

COLLECTOR_SECTIONS = (
    ("sessions", "Active sessions"),
    ("statements", "Top normalized statements"),
    ("indexes", "Index usage and efficiency"),
    ("tables", "Largest tables"),
    ("lock-waits", "Lock waits"),
    ("replication-channels", "Replication channels"),
    ("settings", "Notable configuration"),
)


def _empty_previous() -> dict[str, dict[str, Any]]:
    return {}


@dataclass
class MySqlState:
    report: Dto | None = None
    previous: dict[str, dict[str, Any]] = field(default_factory=_empty_previous)


def mysql_report(ctx: SharpitContext) -> Dto:
    """The last read, or the initial ``NOT_READ`` report: never discovers an engine, never connects."""
    if (reason := sqla.unavailable_reason()) is not None:
        return unavailable_report(reason)
    state = ctx.peek("mysql")
    if isinstance(state, MySqlState) and state.report is not None:
        return state.report
    return _report("NOT_READ", NOT_READ_MESSAGE, None, None, 0, [], [], False)


def has_async_engine(ctx: SharpitContext) -> bool:
    """Whether a registered MySQL engine is async (its pool belongs to the application's event loop)."""
    registry = ctx.capture.engine_registry
    for _name, engine in registry.engines() if registry is not None else []:
        dialect = getattr(engine, "dialect", None)
        if getattr(dialect, "name", None) in ("mysql", "mariadb") and getattr(dialect, "is_async", False):
            return True
    return False


def unavailable_report(reason: str) -> Dto:
    """A ``DISABLED`` report that read nothing, for a read sharpit refused to start."""
    return _report("DISABLED", reason, None, None, 0, [], [], False)


async def refresh_mysql(ctx: SharpitContext) -> Dto:
    """Read every registered MySQL engine (single-flight, held until every worker thread returns)."""
    if (reason := sqla.unavailable_reason()) is not None:
        return unavailable_report(reason)
    single = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight)
    release = single.try_acquire(OPERATION)
    if release is None:
        raise ActionBusy(OPERATION, single.active)
    flight = Flight(release)
    try:
        state = ctx.lazy("mysql", MySqlState)
        state.report = await _read(ctx, state, flight)
        return state.report
    finally:
        flight.done()


async def _read(ctx: SharpitContext, state: MySqlState, flight: Flight) -> Dto:
    started_at = int(time.time() * 1000)
    registry = ctx.capture.engine_registry
    engines = registry.engines() if registry is not None else []
    diagnostics: list[Dto] = []
    budget = ReadBudget.start(READ_BUDGET, clock=_clock)
    data_sources: list[Dto] = []
    unread: list[str] = []
    for name, engine in engines:
        dialect = str(getattr(getattr(engine, "dialect", None), "name", ""))
        if dialect not in ("mysql", "mariadb"):
            label = _LABELS.get(dialect, dialect or "unknown")
            diagnostics.append(_diagnostic(name, "INFO", f"Skipped: this datasource is {label}, not MySQL."))
            continue
        if budget.exhausted():
            diagnostics.append(_diagnostic(name, "WARNING", UNREAD))
            unread.append(f"{name}: {UNREAD}")
            continue
        data_sources.append(await _read_engine(ctx, state, flight, name, engine, budget, diagnostics))
    now = int(time.time() * 1000)
    if not data_sources:
        if unread:
            return _report(
                "ERROR",
                "The read budget ran out before any datasource was read, so nothing was inspected.",
                started_at,
                now,
                0,
                [],
                diagnostics,
                False,
            )
        return _report("DISABLED", NO_MYSQL, started_at, now, 0, [], diagnostics, False)
    truncated = any(d["truncated"] for d in data_sources)
    status, message = _overall_status(data_sources, unread, truncated)
    return _report(
        status,
        message,
        started_at,
        now,
        len(data_sources),
        data_sources,
        diagnostics,
        truncated,
        unread,
    )


def _overall_status(data_sources: list[Dto], unread: list[str], truncated: bool) -> tuple[str, str | None]:
    statuses = [ds["status"] for ds in data_sources]
    if all(status == "ERROR" for status in statuses):
        return "ERROR", "No MySQL datasource could be read."
    if unread or truncated or any(status in {"ERROR", "PARTIAL"} for status in statuses):
        message = (
            "The read budget ran out before every datasource was read; see the diagnostics."
            if unread
            else "Some results are incomplete; see the section details and diagnostics."
        )
        return "PARTIAL", message
    return "READ", None


async def _read_engine(
    ctx: SharpitContext,
    state: MySqlState,
    flight: Flight,
    name: str,
    engine: Any,
    budget: ReadBudget,
    diagnostics: list[Dto],
) -> Dto:
    limits = RowLimits.from_settings(ctx.settings)
    executor = ctx.lazy("mysql.executor", lambda: DaemonExecutor(2, thread_name_prefix="sharpit-mysql"))

    partial = DataSourceData(name)
    timed_out = False

    def read(conn: Any) -> DataSourceData:
        return collect_all(conn, ctx.masker, limits, budget, partial)

    try:
        data = await sqla.run_db_read(
            engine,
            read,
            STATEMENT_TIMEOUT,
            executor=executor,
            done=flight.worker(),
            wall_timeout=budget.remaining() + STATEMENT_TIMEOUT + WALL_MARGIN,
            lock_timeout=LOCK_TIMEOUT,
            read_only=True,
        )
    except sqla.ReadOnlyUnavailable as exc:
        return _error_datasource(name, exc.reason, diagnostics)
    except TimeoutError:
        if not partial.sections:
            return _error_datasource(name, BUDGET_RAN_OUT, diagnostics)
        data, timed_out = _timed_out_data(partial), True
        diagnostics.append(_diagnostic(name, "WARNING", BUDGET_RAN_OUT))
    except Exception as exc:  # noqa: BLE001
        return _error_datasource(
            name,
            ctx.masker.mask_text(str(exc).strip()) or type(exc).__name__,
            diagnostics,
        )

    data.name = name
    _collect_diagnostics(name, data, diagnostics)
    datasource = _datasource(name, data, _changes(state, name, data))
    if timed_out:
        datasource["message"] = BUDGET_RAN_OUT
    return datasource


def _timed_out_data(partial: DataSourceData) -> DataSourceData:
    done = {s["id"] for s in partial.sections}
    for section_id, title in COLLECTOR_SECTIONS:
        if section_id not in done:
            partial.sections.append(_skipped(section_id, title))
    return partial


def _collect_diagnostics(name: str, data: DataSourceData, diagnostics: list[Dto]) -> None:
    diagnostics.extend(data.diagnostics)
    for section in data.sections:
        source = f"{name}/{section['id']}"
        if section["status"] != "AVAILABLE":
            level = "ERROR" if section["status"] == "FAILED" else "WARNING"
            diagnostics.append(_diagnostic(source, level, section["reason"]))
        elif section.get("reason") is not None:
            diagnostics.append(_diagnostic(source, "INFO", section["reason"]))


def _skipped(section_id: str, title: str) -> Dto:
    return {
        "id": section_id,
        "title": title,
        "status": "SKIPPED",
        "reason": BUDGET_SKIPPED,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def _diagnostic(source: str, level: str, message: str | None) -> Dto:
    return {"source": source, "level": level, "message": message}


def _status(data: DataSourceData) -> str:
    """MySqlInsightService.statusOf."""
    if not any(s["status"] == "AVAILABLE" for s in data.sections):
        return "ERROR"
    complete = all(s["status"] == "AVAILABLE" and s.get("reason") is None for s in data.sections)
    return "READ" if complete and not data.truncated else "PARTIAL"


def _datasource(name: str, data: DataSourceData, changes: list[Dto]) -> Dto:
    return {
        "name": name,
        "databaseName": data.database_name,
        "status": _status(data),
        "message": None,
        "capabilities": data.capabilities
        or {
            "serverVersion": None,
            "serverComment": None,
            "isMariaDb": False,
            "performanceSchema": False,
        },
        "sections": data.sections,
        "sessions": data.sessions,
        "statements": data.statements,
        "indexes": data.indexes,
        "tables": data.tables,
        "lockWaits": data.lock_waits,
        "replicationChannels": data.replication_channels,
        "metrics": data.metrics,
        "settings": data.settings,
        "changes": changes,
        "truncated": data.truncated,
    }


def _error_datasource(name: str, reason: str, diagnostics: list[Dto]) -> Dto:
    diagnostics.append(_diagnostic(name, "ERROR", reason))
    data = DataSourceData(name)
    return {**_datasource(name, data, []), "status": "ERROR", "message": reason}


def _changes(state: MySqlState, name: str, data: DataSourceData) -> list[Dto]:
    current = {
        m["label"]: {"value": m["value"], "rendered": f"{m['value']} {m.get('unit', '')}".strip()}
        for m in data.metrics
        if m.get("value") is not None
    }
    if not current:
        return []
    before = state.previous.get(name)
    state.previous[name] = {**(before or {}), **current}
    return compare_changes(before, current)


def _report(
    status: str,
    message: str | None,
    read_started_at: int | None,
    read_at: int | None,
    data_sources_read: int,
    data_sources: list[Dto],
    diagnostics: list[Dto],
    truncated: bool,
    read_limitations: list[str] | None = None,
) -> Dto:
    return {
        "localOnly": True,
        "disclaimer": DISCLAIMER,
        "status": status,
        "message": message,
        "readStartedAt": read_started_at,
        "readAt": read_at,
        "dataSourcesRead": data_sources_read,
        "dataSources": data_sources,
        "diagnostics": diagnostics,
        "limitations": _limitations(data_sources, truncated, read_limitations or []),
        "truncated": truncated,
    }


def _limitations(data_sources: list[Dto], _truncated: bool, read_limitations: list[str]) -> list[str]:
    limitations: list[str] = list(read_limitations)
    for ds in data_sources:
        name = ds["name"]
        for section in ds.get("sections", []):
            if section["status"] != "AVAILABLE" or section.get("reason") is not None:
                limitations.append(f"{name}/{section['id']}: {section['reason']}")
            if section.get("truncated"):
                count = section.get("rowCount", 0)
                limitations.append(f"{name}/{section['id']}: row limit reached ({count} rows retained)")
    return limitations


def summary(report: Dto) -> Dto:
    """McpScanSummaries.mysql: the read's status and each datasource's and section's coverage, without rows."""
    data_sources = [
        {
            "name": d["name"],
            "status": d["status"],
            "message": d["message"],
            "truncated": d["truncated"],
            "sections": [
                {k: s[k] for k in ("id", "status", "reason", "rowCount", "truncated")} for s in d.get("sections", [])
            ],
        }
        for d in report.get("dataSources", [])
    ]
    return {
        "reportTool": "get_mysql_report",
        "status": report["status"],
        "message": report["message"],
        "readAt": report["readAt"],
        "dataSourcesRead": report["dataSourcesRead"],
        "truncated": report["truncated"],
        "dataSources": data_sources,
        "diagnostics": len(report["diagnostics"]),
        "limitations": report["limitations"],
    }
