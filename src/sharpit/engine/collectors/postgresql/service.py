"""The ``postgresql`` panel's report: ``GET`` serves the last read, ``POST /read`` reads every PostgreSQL engine.

Port of BootUI ``PostgresInsightService`` (2.2.0). Each engine is read through ``sqla.run_db_read(read_only=True)``,
whose ``bounded_read_only`` pins ``SET TRANSACTION READ ONLY`` and refuses the read (no catalog SQL) when the server
does not confirm it: that refusal is BootUI's "manual-commit mode" skip. The previous read's metrics live in memory
only (``ctx.lazy``), so ``changes`` appear from the second read on and nothing is ever persisted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine import sqla
from sharpit.engine.collectors.postgresql.limits import READ_BUDGET, STATEMENT_TIMEOUT, RowLimits
from sharpit.engine.collectors.postgresql.sections import (
    BUDGET_SKIPPED,
    COLLECTORS,
    DatabaseData,
    ReadBudget,
    collect,
)
from sharpit.engine.daemon_executor import DaemonExecutor
from sharpit.engine.singleflight import ActionBusy, Flight, SingleFlight

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

OPERATION = "postgresql-read"
DISCLAIMER = (
    "Read-only reads of PostgreSQL's own pg_stat_* and pg_catalog views, bounded by row count and a "
    "wall-clock budget. The session list is a live snapshot; every other number is cumulative "
    "since the last statistics reset and covers every client of the database, not only this "
    "application."
)
NOT_READ_MESSAGE = (
    "The database has not been read yet. Run PostgreSQL read in the panel, or call postgresql_read"
    " (sharpit db postgres read), to query its own statistics views."
)
NO_POSTGRES = (
    "No PostgreSQL datasource was found. This panel reads PostgreSQL's own statistics views, "
    "so it has nothing to report for other database products."
)
UNREAD = "The read budget ran out before this datasource was read."
_LABELS = {"sqlite": "SQLite", "mysql": "MySQL", "mariadb": "MariaDB", "mssql": "SQL Server", "oracle": "Oracle"}

_clock = time.monotonic  # test seam: the read budget's clock
# the wall timeout outlasts the cooperative budget by one statement plus this margin, so the budget's own SKIPPED path
# is what normally stops a slow read; the wall timeout is only the backstop
WALL_MARGIN = 1.0
BUDGET_RAN_OUT = "The read budget ran out while reading this datasource."

Dto = dict[str, Any]


@dataclass(frozen=True)
class Metric:
    """PostgresMetric: the raw value decides the direction, only the rendered form reaches the browser."""

    value: float
    rendered: str


@dataclass
class PostgresState:
    report: Dto | None = None
    previous: dict[str, dict[str, Metric]] = field(default_factory=lambda: {})


def postgresql_report(ctx: SharpitContext) -> Dto:
    """The last read, or the initial ``NOT_READ`` report: never discovers an engine, never connects."""
    state = ctx.peek("postgresql")
    if isinstance(state, PostgresState) and state.report is not None:
        return state.report
    return _report("NOT_READ", NOT_READ_MESSAGE, None, [], [], False)


async def refresh_postgresql(ctx: SharpitContext) -> Dto:
    """Read every registered PostgreSQL engine (single-flight, held until every worker thread returns)."""
    single = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight)
    release = single.try_acquire(OPERATION)
    if release is None:
        raise ActionBusy(OPERATION, single.active)
    flight = Flight(release)
    try:
        state = ctx.lazy("postgresql", PostgresState)
        state.report = await _read(ctx, state, flight)
        return state.report
    finally:
        flight.done()


async def _read(ctx: SharpitContext, state: PostgresState, flight: Flight) -> Dto:
    registry = ctx.capture.engine_registry
    engines = registry.engines() if registry is not None else []
    diagnostics: list[Dto] = []
    budget = ReadBudget.start(READ_BUDGET, clock=_clock)
    databases: list[Dto] = []
    unread: list[str] = []
    for name, engine in engines:
        dialect = str(getattr(getattr(engine, "dialect", None), "name", ""))
        if dialect != "postgresql":
            label = _LABELS.get(dialect, dialect or "unknown")
            diagnostics.append(_diagnostic(name, "INFO", f"Skipped: this datasource is {label}, not PostgreSQL."))
            continue
        if budget.exhausted():
            diagnostics.append(_diagnostic(name, "WARNING", UNREAD))
            unread.append(f"{name}: {UNREAD}")
            continue
        databases.append(await _read_engine(ctx, state, flight, name, engine, budget, diagnostics))
    now = int(time.time() * 1000)
    if not databases:
        if unread:
            return _report("ERROR", "The read budget ran out before any datasource was read, so nothing was "
                           "inspected.", now, [], diagnostics, False)  # fmt: skip
        return _report("DISABLED", NO_POSTGRES, now, [], diagnostics, False)
    statuses = [d["status"] for d in databases]
    truncated = any(d["truncated"] for d in databases)
    if all(s == "ERROR" for s in statuses):
        status, message = "ERROR", "No PostgreSQL datasource could be read."
    elif unread or truncated or any(s in {"ERROR", "PARTIAL"} for s in statuses):
        status = "PARTIAL"
        message = (
            "The read budget ran out before every datasource was read; see the diagnostics."
            if unread
            else "Some results are incomplete; see the section details and diagnostics."
        )
    else:
        status, message = "READ", None
    return _report(status, message, now, databases, diagnostics, truncated, unread)


async def _read_engine(
    ctx: SharpitContext,
    state: PostgresState,
    flight: Flight,
    name: str,
    engine: Any,
    budget: ReadBudget,
    diagnostics: list[Dto],
) -> Dto:
    limits = RowLimits.from_settings(ctx.settings)
    executor = ctx.lazy("postgresql.executor", lambda: DaemonExecutor(2, thread_name_prefix="sharpit-postgresql"))

    partial = DatabaseData(name)
    timed_out = False

    def read(conn: Any) -> tuple[DatabaseData, Any]:
        return collect(conn, ctx.masker, limits, budget, partial), getattr(conn.dialect, "server_version_info", None)

    try:
        data, version = await sqla.run_db_read(
            engine,
            read,
            STATEMENT_TIMEOUT,
            executor=executor,
            done=flight.worker(),
            wall_timeout=budget.remaining() + STATEMENT_TIMEOUT + WALL_MARGIN,
            statement_timeout=STATEMENT_TIMEOUT,
            read_only=True,
        )
    except sqla.ReadOnlyUnavailable as exc:
        return _error_database(name, exc.reason, diagnostics)
    except TimeoutError:
        if not partial.sections:
            return _error_database(name, BUDGET_RAN_OUT, diagnostics)
        # the worker may still be adding sections: report a copy, every section it had not reached as SKIPPED
        sections = list(partial.sections)
        done = {s["id"] for s in sections}
        sections += [_skipped(c.id, c.title) for c in COLLECTORS if c.id not in done]
        data, version, timed_out = replace(partial, sections=sections), None, True
        diagnostics.append(_diagnostic(name, "WARNING", BUDGET_RAN_OUT))
    except Exception as exc:  # noqa: BLE001 - a failed engine is reported for that engine, never raised
        return _error_database(name, ctx.masker.mask_text(str(exc).strip()) or type(exc).__name__, diagnostics)
    data.name = name
    for section in data.sections:
        source = f"{name}/{section['id']}"
        if section["status"] != "AVAILABLE":
            level = "ERROR" if section["status"] == "FAILED" else "WARNING"
            diagnostics.append(_diagnostic(source, level, section["reason"]))
        elif section["reason"] is not None:
            diagnostics.append(_diagnostic(source, "INFO", section["reason"]))
    database = _database(name, data, version, _changes(state, name, data))
    if timed_out:
        database["message"] = BUDGET_RAN_OUT
    return database


def _skipped(section_id: str, title: str) -> Dto:
    return {"id": section_id, "title": title, "status": "SKIPPED", "reason": BUDGET_SKIPPED, "hint": None,
            "rowCount": 0, "truncated": False}  # fmt: skip


def _diagnostic(source: str, level: str, message: str | None) -> Dto:
    return {"source": source, "level": level, "message": message}


def _status(data: DatabaseData) -> str:
    """PostgresInsightService.statusOf."""
    if not any(s["status"] == "AVAILABLE" for s in data.sections):
        return "ERROR"
    complete = all(s["status"] == "AVAILABLE" and s["reason"] is None for s in data.sections)
    return "READ" if complete and not data.truncated else "PARTIAL"


def _database(name: str, data: DatabaseData, version: Any, changes: list[Dto]) -> Dto:
    parts = [str(p) for p in cast("tuple[object, ...]", version)] if isinstance(version, tuple) else []
    vitals = data.vital_signs
    return {
        "name": name,
        "databaseName": None if vitals is None else vitals["databaseName"],
        "serverVersion": ".".join(parts) or None,
        "serverMajorVersion": int(parts[0]) if parts and parts[0].isdigit() else -1,
        "role": data.role,
        "monitoringRole": not data.statistics_restricted,
        "status": _status(data),
        "message": None,
        "vitalSigns": vitals,
        "sections": data.sections,
        "sessions": data.sessions,
        "statements": data.statements,
        "indexes": data.indexes,
        "tables": data.tables,
        "vacuum": data.vacuum,
        "replication": data.replication,
        "settings": data.settings,
        "changes": changes,
        "truncated": data.truncated,
    }


def _error_database(name: str, reason: str, diagnostics: list[Dto]) -> Dto:
    diagnostics.append(_diagnostic(name, "ERROR", reason))
    data = DatabaseData(name)
    return {**_database(name, data, None, []), "status": "ERROR", "message": reason, "monitoringRole": False}


# ---- comparison with the previous read (PostgresInsightService.changesFor / metricsOf) ----------------------------


def _percent(ratio: float) -> str:
    return f"{ratio * 100:.1f}%"


def _bytes(value: int) -> str:
    size, unit = float(value), 0
    units = ("B", "kB", "MB", "GB", "TB")
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{value} B" if unit == 0 else f"{size:.1f} {units[unit]}"


def _metrics(data: DatabaseData) -> dict[str, Metric]:
    metrics: dict[str, Metric] = {}
    vitals = data.vital_signs or {}
    for label, key, render in (
        ("Cache hit ratio", "cacheHitRatio", _percent),
        ("Rollback ratio", "rollbackRatio", _percent),
        ("Connections", "connections", str),
        ("Deadlocks", "deadlocks", str),
        ("Database size", "databaseSizeBytes", _bytes),
        ("Transaction id age", "transactionIdAge", str),
    ):
        value = vitals.get(key)
        if value is not None:
            metrics[label] = Metric(float(value), render(value))
    # a subset total over the largest relations: only comparable when that list was read whole
    tables = data.section("tables")
    dead = [t["deadTuples"] for t in data.tables if t["deadTuples"] is not None]
    if tables and tables["status"] == "AVAILABLE" and tables["reason"] is None and not tables["truncated"] and dead:
        metrics["Dead tuples in the largest relations"] = Metric(float(sum(dead)), str(sum(dead)))
    return metrics


def _changes(state: PostgresState, name: str, data: DatabaseData) -> list[Dto]:
    current = _metrics(data)
    if not current:
        return []  # a read with nothing comparable never replaces the baseline
    before = state.previous.get(name)
    state.previous[name] = {**(before or {}), **current}  # a partial read merges into the baseline
    if before is None:
        return []
    changes: list[Dto] = []
    for metric, now in current.items():
        earlier = before.get(metric)
        if earlier is None or now.value == earlier.value:
            continue
        direction = "UP" if now.value > earlier.value else "DOWN"
        changes.append(
            {"metric": metric, "previous": earlier.rendered, "current": now.rendered, "direction": direction}
        )
    return changes


# ---- the report ----------------------------------------------------------------------------------------------------


def _report(
    status: str,
    message: str | None,
    read_at: int | None,
    databases: list[Dto],
    diagnostics: list[Dto],
    truncated: bool,
    read_limitations: list[str] | None = None,
) -> Dto:
    return {
        "localOnly": True,
        "disclaimer": DISCLAIMER,
        "status": status,
        "message": message,
        "readAt": read_at,
        "databasesRead": len(databases),
        "truncated": truncated,
        "databases": databases,
        "diagnostics": diagnostics,
        "limitations": _limitations(databases, truncated, read_limitations or []),
    }


def _limitations(databases: list[Dto], truncated: bool, read_limitations: list[str]) -> list[str]:
    limitations = list(read_limitations)
    for database in databases:
        name = database["name"]
        for section in database["sections"]:
            if section["status"] != "AVAILABLE" or section["reason"] is not None:
                limitations.append(f"{name}/{section['id']}: {section['reason']}")
            if section["truncated"]:
                count = section["rowCount"]
                if section["id"] == "statements":
                    noun = "statement" if count == 1 else "statements"
                    text = (
                        f"Showing the top {count} {noun} by total execution time. Additional statements are not shown."
                    )
                else:
                    noun = "row." if count == 1 else "rows."
                    text = (
                        f"Showing {count} {noun} Additional rows are not shown because this section reached sharpit's "
                        "row limit."
                    )
                limitations.append(f"{name} / {section['title']}: {text}")
        if database["status"] in {"PARTIAL", "ERROR"} and database["message"] is not None:
            limitations.append(f"{name}: {database['message']}")
    if truncated and not limitations:
        limitations.append("Some results reached sharpit's row limits. Additional rows are not shown.")
    return limitations


def summary(report: Dto) -> Dto:
    """McpScanSummaries.postgresql: the read's status and each database's and section's coverage, without rows."""
    databases = [
        {
            "name": d["name"],
            "status": d["status"],
            "message": d["message"],
            "truncated": d["truncated"],
            "sections": [{k: s[k] for k in ("id", "status", "reason", "rowCount", "truncated")} for s in d["sections"]],
        }
        for d in report["databases"]
    ]
    return {
        "reportTool": "get_postgresql_report",
        "status": report["status"],
        "message": report["message"],
        "readAt": report["readAt"],
        "databasesRead": report["databasesRead"],
        "truncated": report["truncated"],
        "databases": databases,
        "diagnostics": len(report["diagnostics"]),
        "limitations": report["limitations"],
    }
