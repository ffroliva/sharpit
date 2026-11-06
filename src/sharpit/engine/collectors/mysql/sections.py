"""The ``mysql`` panel sections and catalog collectors (BootUI 2.2.0 contract §6)."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from sharpit.engine.capture.sqltrace import mask_error
from sharpit.engine.collectors.mysql.limits import ReadBudget, RowLimits, read_one_past
from sharpit.engine.collectors.mysql.queries import (
    CAPABILITIES_SQL,
    CURATED_SETTINGS,
    DATABASE_SQL,
    INDEXES_SQL,
    LOCK_WAITS_MARIADB_SQL,
    LOCK_WAITS_SQL,
    REPLICATION_PFS_SQL,
    SESSIONS_FALLBACK_SQL,
    SESSIONS_PFS_SQL,
    SETTINGS_SQL,
    STATEMENTS_SQL,
    STATUS_SQL,
    TABLES_SQL,
)
from sharpit.engine.collectors.mysql.querytext import mysql_query_text
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

Dto = dict[str, Any]
Row = dict[str, Any]

# One title per section, for read and skipped sections alike.
SECTIONS = (
    ("sessions", "Active sessions"),
    ("statements", "Top normalized statements"),
    ("indexes", "Index usage and efficiency"),
    ("tables", "Largest tables"),
    ("lock-waits", "Lock waits"),
    ("replication-channels", "Replication channels"),
    ("settings", "Notable configuration"),
)
_TITLES = dict(SECTIONS)
# A collector called without the context's masker still masks (fails closed).
_STRICT = Masker(Exposure.MASKED, True)


@dataclass
class DataSourceData:
    name: str
    database_name: str | None = None
    capabilities: Dto = field(default_factory=lambda: {})
    sections: list[Dto] = field(default_factory=lambda: [])
    sessions: list[Dto] = field(default_factory=lambda: [])
    statements: list[Dto] = field(default_factory=lambda: [])
    indexes: list[Dto] = field(default_factory=lambda: [])
    tables: list[Dto] = field(default_factory=lambda: [])
    lock_waits: list[Dto] = field(default_factory=lambda: [])
    replication_channels: list[Dto] = field(default_factory=lambda: [])
    metrics: list[Dto] = field(default_factory=lambda: [])
    settings: list[Dto] = field(default_factory=lambda: [])
    diagnostics: list[Dto] = field(default_factory=lambda: [])
    truncated: bool = False


def _diagnostic(source: str, level: str, message: str | None) -> Dto:
    return {"source": source, "level": level, "message": message}


def section_dto(section_id: str, status: str, reason: str | None = None, rows: int = 0, truncated: bool = False) -> Dto:
    return {"id": section_id, "title": _TITLES[section_id], "status": status, "reason": reason, "hint": None,
            "rowCount": rows, "truncated": truncated}  # fmt: skip


def _reason(masker: Masker, exc: Exception) -> str:
    return mask_error(masker, str(exc).strip(), dialect=Dialect.MYSQL_FAMILY, known=True) or type(exc).__name__


def _rows(conn: Any, sql: str) -> list[Row]:
    with conn.begin_nested():
        return [dict(r) for r in conn.exec_driver_sql(sql).mappings()]


def _read_section(
    conn: Any,
    masker: Masker,
    data: DataSourceData,
    section_id: str,
    sql: str,
    limit: int,
    build: Callable[[list[Row]], list[Dto]],
) -> Dto:
    """Run one section's query; a failure is ``FAILED`` with the masked driver error, never an empty success."""
    try:
        retained, truncated = read_one_past(build(_rows(conn, sql)), limit)
    except Exception as exc:  # noqa: BLE001 - every driver error becomes the section's reason
        return section_dto(section_id, "FAILED", _reason(masker, exc))
    setattr(data, section_id.replace("-", "_"), retained)
    data.truncated = data.truncated or truncated
    return section_dto(section_id, "AVAILABLE", rows=len(retained), truncated=truncated)


def _bounded(sql: str, limit: int) -> str:
    return f"{sql.strip()} LIMIT {limit + 1}"


def collect_capabilities(conn: Any, data: DataSourceData) -> Dto:
    """Capability probe: @@version, @@version_comment, @@performance_schema."""
    version = ""
    version_comment = ""
    pfs_raw: Any = 1
    try:
        cap_rows = list(conn.exec_driver_sql(CAPABILITIES_SQL).mappings())
        row: dict[str, Any] = dict(cap_rows[0]) if cap_rows else {}
        version = str(row.get("version") or "")
        version_comment = str(row.get("version_comment") or "")
        pfs_raw = row.get("performance_schema", 1)
    except Exception:
        # Fallback to individual selects if composite select fails
        with contextlib.suppress(Exception):
            version = str(conn.exec_driver_sql("SELECT @@version").scalar() or "")
        with contextlib.suppress(Exception):
            version_comment = str(conn.exec_driver_sql("SELECT @@version_comment").scalar() or "")
        with contextlib.suppress(Exception):
            pfs_raw = conn.exec_driver_sql("SELECT @@performance_schema").scalar()

    dialect = getattr(conn, "dialect", None)
    is_mariadb = (
        getattr(dialect, "is_mariadb", False)
        or "mariadb" in str(getattr(dialect, "name", "")).lower()
        or "-mariadb" in version.lower()
        or "mariadb" in version_comment.lower()
    )

    pfs_enabled = str(pfs_raw).strip().lower() in ("1", "on", "true") or pfs_raw == 1

    caps: Dto = {
        "serverVersion": version,
        "serverComment": version_comment,
        "isMariaDb": is_mariadb,
        "performanceSchema": pfs_enabled,
    }
    data.capabilities = caps

    if not pfs_enabled:
        msg = (
            "performance_schema is disabled on this server. Statements and performance statistics "
            "require performance_schema."
        )
        data.diagnostics.append(_diagnostic(f"{data.name}/capabilities", "WARNING", msg))

    try:
        db_rows = list(conn.exec_driver_sql(DATABASE_SQL).mappings())
        db_row: dict[str, Any] = dict(db_rows[0]) if db_rows else {}
        data.database_name = cast("str | None", db_row.get("current_database"))
    except Exception:
        data.database_name = None

    return caps


def collect_sessions(conn: Any, masker: Masker, limits: RowLimits, data: DataSourceData) -> Dto:
    sql = SESSIONS_PFS_SQL if data.capabilities.get("performanceSchema", True) else SESSIONS_FALLBACK_SQL

    def build(rows: list[Row]) -> list[Dto]:
        return [
            {
                "id": r.get("id"),
                "user": r.get("user"),
                "host": r.get("host"),
                "db": r.get("db"),
                "command": r.get("command"),
                "time": r.get("time"),
                "state": r.get("state"),
                "info": mysql_query_text(masker, r.get("info")),
                "currentStatement": mysql_query_text(masker, r.get("current_statement")),
            }
            for r in rows
        ]

    return _read_section(conn, masker, data, "sessions", _bounded(sql, limits.max_sessions), limits.max_sessions,
                         build)  # fmt: skip


def collect_statements(conn: Any, masker: Masker, limits: RowLimits, data: DataSourceData) -> Dto:
    if not data.capabilities.get("performanceSchema", True):
        return section_dto("statements", "SKIPPED", "performance_schema is disabled on this server.")

    def build(rows: list[Row]) -> list[Dto]:
        return [
            {
                "schema": r.get("schema_name"),
                "digest": r.get("digest"),
                "digestText": mysql_query_text(masker, r.get("digest_text")),
                "countStar": r.get("count_star"),
                "sumTimerWait": r.get("sum_timer_wait"),
                "avgTimerWait": r.get("avg_timer_wait"),
                "maxTimerWait": r.get("max_timer_wait"),
                "sumRowsAffected": r.get("sum_rows_affected"),
                "sumRowsSent": r.get("sum_rows_sent"),
                "sumRowsExamined": r.get("sum_rows_examined"),
                "sumNoIndexUsed": r.get("sum_no_index_used"),
            }
            for r in rows
        ]

    limit = limits.max_statements
    return _read_section(conn, masker, data, "statements", _bounded(STATEMENTS_SQL, limit), limit, build)


def collect_indexes(conn: Any, limits: RowLimits, data: DataSourceData, masker: Masker = _STRICT) -> Dto:
    def build(rows: list[Row]) -> list[Dto]:
        return [
            {
                "tableSchema": r.get("table_schema"),
                "tableName": r.get("table_name"),
                "indexName": r.get("index_name"),
                "nonUnique": bool(r.get("non_unique")),
                "seqInIndex": r.get("seq_in_index"),
                "columnName": r.get("column_name"),
                "cardinality": r.get("cardinality"),
                "indexType": r.get("index_type"),
            }
            for r in rows
        ]

    limit = limits.max_indexes
    return _read_section(conn, masker, data, "indexes", _bounded(INDEXES_SQL, limit), limit, build)


def collect_tables(conn: Any, limits: RowLimits, data: DataSourceData, masker: Masker = _STRICT) -> Dto:
    def build(rows: list[Row]) -> list[Dto]:
        return [
            {
                "tableSchema": r.get("table_schema"),
                "tableName": r.get("table_name"),
                "tableType": r.get("table_type"),
                "engine": r.get("engine"),
                "tableRows": r.get("table_rows"),
                "avgRowLength": r.get("avg_row_length"),
                "dataLength": r.get("data_length"),
                "indexLength": r.get("index_length"),
                "dataFree": r.get("data_free"),
            }
            for r in rows
        ]

    limit = limits.max_tables
    return _read_section(conn, masker, data, "tables", _bounded(TABLES_SQL, limit), limit, build)


def collect_lock_waits(conn: Any, masker: Masker, limits: RowLimits, data: DataSourceData) -> Dto:
    sql = LOCK_WAITS_MARIADB_SQL if data.capabilities.get("isMariaDb") else LOCK_WAITS_SQL

    def build(rows: list[Row]) -> list[Dto]:
        return [
            {
                "waitingTrxId": r.get("waiting_trx_id"),
                "waitingPid": r.get("waiting_pid"),
                "waitingQuery": mysql_query_text(masker, r.get("waiting_query")),
                "blockingTrxId": r.get("blocking_trx_id"),
                "blockingPid": r.get("blocking_pid"),
                "blockingQuery": mysql_query_text(masker, r.get("blocking_query")),
            }
            for r in rows
        ]

    limit = limits.max_lock_waits
    return _read_section(conn, masker, data, "lock-waits", _bounded(sql, limit), limit, build)


def collect_replication(conn: Any, limits: RowLimits, data: DataSourceData, masker: Masker = _STRICT) -> Dto:
    if data.capabilities.get("isMariaDb"):
        return section_dto(
            "replication-channels", "SKIPPED", "MariaDB has no performance_schema.replication_connection_status."
        )

    def build(rows: list[Row]) -> list[Dto]:
        return [
            {
                "channelName": r.get("channel_name"),
                "serviceState": r.get("service_state"),
                "sourceUuid": r.get("source_uuid"),
                "lastErrorNumber": r.get("last_error_number"),
                "lastErrorMessage": mask_error(
                    masker, r.get("last_error_message"), dialect=Dialect.MYSQL_FAMILY, known=True
                ),
                "lastErrorTimestamp": r.get("last_error_timestamp"),
            }
            for r in rows
        ]

    limit = limits.max_replication_channels
    return _read_section(conn, masker, data, "replication-channels", _bounded(REPLICATION_PFS_SQL, limit), limit,
                         build)  # fmt: skip


def collect_settings(conn: Any, limits: RowLimits, data: DataSourceData, masker: Masker = _STRICT) -> Dto:
    def build(rows: list[Row]) -> list[Dto]:
        found = {
            str(r["Variable_name"]).lower(): str(r["Value"]) for r in rows if "Variable_name" in r and "Value" in r
        }
        return [
            {"name": name, "value": found[name.lower()], "scope": "GLOBAL", "source": "SERVER"}
            for name in sorted(CURATED_SETTINGS)
            if name.lower() in found
        ]

    return _read_section(conn, masker, data, "settings", SETTINGS_SQL, limits.max_settings, build)


_METRICS = (
    ("Threads_connected", "Threads connected", None),
    ("Uptime", "Uptime", "seconds"),
    ("Queries", "Queries", None),
    ("Slow_queries", "Slow queries", None),
)


def _number(raw: str | None) -> float | None:
    try:
        return None if raw is None else float(raw)
    except ValueError:
        return None


def _metric(metric_id: str, label: str, value: float, unit: str | None) -> Dto:
    shown = int(value) if value.is_integer() else value
    return {"id": metric_id, "label": label, "value": shown, "unit": unit, "scope": "GLOBAL", "source": "STATUS"}


def collect_metrics(conn: Any, data: DataSourceData, masker: Masker = _STRICT) -> list[Dto]:
    """SHOW GLOBAL STATUS counters; a failure is an ERROR diagnostic, never a silent empty list."""
    try:
        rows = _rows(conn, STATUS_SQL)
    except Exception as exc:  # noqa: BLE001 - the driver error becomes the diagnostic
        data.diagnostics.append(_diagnostic(f"{data.name}/metrics", "ERROR", _reason(masker, exc)))
        return []
    status = {str(r["Variable_name"]): str(r["Value"]) for r in rows if "Variable_name" in r and "Value" in r}
    metrics = [
        _metric(var, label, value, unit)
        for var, label, unit in _METRICS
        if (value := _number(status.get(var))) is not None
    ]
    reads = _number(status.get("Innodb_buffer_pool_reads"))
    requests = _number(status.get("Innodb_buffer_pool_read_requests"))
    if reads is not None and requests is not None and requests > 0:
        ratio = round((1.0 - reads / requests) * 100, 1)
        metrics.append(_metric("innodb_buffer_pool_hit_ratio", "Buffer pool hit ratio", ratio, "%"))
    data.metrics = metrics
    return metrics


def compare_changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[Dto]:
    if previous is None:
        return []
    changes: list[Dto] = []
    for metric, now in current.items():
        earlier = previous.get(metric)
        if earlier is None:
            continue
        earlier_val = earlier.get("value")
        now_val = now.get("value")
        if earlier_val is None or now_val is None or earlier_val == now_val:
            continue
        direction = "UP" if now_val > earlier_val else "DOWN"
        changes.append(
            {
                "metric": metric,
                "previous": str(earlier.get("rendered", earlier_val)),
                "current": str(now.get("rendered", now_val)),
                "direction": direction,
            }
        )
    return changes


BUDGET_SKIPPED = "The read budget ran out before this section was read."


def collect_all(
    conn: Any,
    masker: Masker,
    limits: RowLimits,
    budget: ReadBudget,
    data: DataSourceData,
) -> DataSourceData:
    collect_capabilities(conn, data)
    collect_metrics(conn, data, masker)

    collectors: dict[str, Callable[[], Dto]] = {
        "sessions": lambda: collect_sessions(conn, masker, limits, data),
        "statements": lambda: collect_statements(conn, masker, limits, data),
        "indexes": lambda: collect_indexes(conn, limits, data, masker),
        "tables": lambda: collect_tables(conn, limits, data, masker),
        "lock-waits": lambda: collect_lock_waits(conn, masker, limits, data),
        "replication-channels": lambda: collect_replication(conn, limits, data, masker),
        "settings": lambda: collect_settings(conn, limits, data, masker),
    }
    for section_id, _title in SECTIONS:
        exhausted = budget.exhausted()
        data.sections.append(
            section_dto(section_id, "SKIPPED", BUDGET_SKIPPED) if exhausted else collectors[section_id]()
        )
    return data
