"""The ``mysql`` panel sections and catalog collectors (BootUI 2.2.0 contract §6)."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, cast

from sharpit.engine.collectors.mysql.limits import ReadBudget, RowLimits, read_one_past
from sharpit.engine.collectors.mysql.queries import (
    CAPABILITIES_SQL,
    CURATED_SETTINGS,
    DATABASE_SQL,
    INDEXES_SQL,
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
from sharpit.engine.masking import Masker

SECTION_IDS = (
    "sessions",
    "statements",
    "indexes",
    "tables",
    "lock-waits",
    "replication-channels",
    "settings",
)

Dto = dict[str, Any]


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


def _diagnostic(source: str, level: str, message: str) -> Dto:
    return {"source": source, "level": level, "message": message}


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
    pfs_enabled = data.capabilities.get("performanceSchema", True)
    query_sql = SESSIONS_PFS_SQL if pfs_enabled else SESSIONS_FALLBACK_SQL
    bound_sql = query_sql.strip() + f" LIMIT {limits.max_sessions + 1}"
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(bound_sql).mappings()]
        sessions: list[Dto] = []
        for r in rows:
            stmt = cast("str | None", r.get("current_statement") or r.get("info"))
            masked_stmt = mysql_query_text(masker, stmt)
            sessions.append(
                {
                    "id": r.get("id"),
                    "user": r.get("user"),
                    "host": r.get("host"),
                    "db": r.get("db"),
                    "command": r.get("command"),
                    "time": r.get("time"),
                    "state": r.get("state"),
                    "info": masked_stmt,
                    "currentStatement": masked_stmt,
                }
            )
        retained, truncated = read_one_past(sessions, limits.max_sessions)
        data.sessions = retained
        if truncated:
            data.truncated = True
        return {
            "id": "sessions",
            "title": "Sessions",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": len(retained),
            "truncated": truncated,
        }
    except Exception as exc:
        data.sessions = []
        reason = masker.mask_text(str(exc).strip()) or type(exc).__name__
        return {
            "id": "sessions",
            "title": "Sessions",
            "status": "FAILED",
            "reason": reason,
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }


def collect_statements(conn: Any, masker: Masker, limits: RowLimits, data: DataSourceData) -> Dto:
    if not data.capabilities.get("performanceSchema", True):
        data.statements = []
        return {
            "id": "statements",
            "title": "Statements",
            "status": "SKIPPED",
            "reason": "performance_schema is disabled on this server.",
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }
    bound_sql = STATEMENTS_SQL.strip() + f" LIMIT {limits.max_statements + 1}"
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(bound_sql).mappings()]
        statements: list[Dto] = []
        for r in rows:
            digest_text = mysql_query_text(masker, cast("str | None", r.get("digest_text")))
            statements.append(
                {
                    "schema": r.get("schema_name"),
                    "digest": r.get("digest"),
                    "digestText": digest_text,
                    "countStar": r.get("count_star"),
                    "sumTimerWait": r.get("sum_timer_wait"),
                    "avgTimerWait": r.get("avg_timer_wait"),
                    "maxTimerWait": r.get("max_timer_wait"),
                    "sumRowsAffected": r.get("sum_rows_affected"),
                    "sumRowsSent": r.get("sum_rows_sent"),
                    "sumRowsExamined": r.get("sum_rows_examined"),
                    "sumNoIndexUsed": r.get("sum_no_index_used"),
                }
            )
        retained, truncated = read_one_past(statements, limits.max_statements)
        data.statements = retained
        if truncated:
            data.truncated = True
        return {
            "id": "statements",
            "title": "Statements",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": len(retained),
            "truncated": truncated,
        }
    except Exception as exc:
        data.statements = []
        reason = masker.mask_text(str(exc).strip()) or type(exc).__name__
        return {
            "id": "statements",
            "title": "Statements",
            "status": "FAILED",
            "reason": reason,
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }


def collect_indexes(conn: Any, limits: RowLimits, data: DataSourceData) -> Dto:
    bound_sql = INDEXES_SQL.strip() + f" LIMIT {limits.max_indexes + 1}"
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(bound_sql).mappings()]
        indexes: list[Dto] = [
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
        retained, truncated = read_one_past(indexes, limits.max_indexes)
        data.indexes = retained
        if truncated:
            data.truncated = True
        return {
            "id": "indexes",
            "title": "Indexes",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": len(retained),
            "truncated": truncated,
        }
    except Exception as exc:
        data.indexes = []
        return {
            "id": "indexes",
            "title": "Indexes",
            "status": "FAILED",
            "reason": str(exc).strip(),
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }


def collect_tables(conn: Any, limits: RowLimits, data: DataSourceData) -> Dto:
    bound_sql = TABLES_SQL.strip() + f" LIMIT {limits.max_tables + 1}"
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(bound_sql).mappings()]
        tables: list[Dto] = [
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
        retained, truncated = read_one_past(tables, limits.max_tables)
        data.tables = retained
        if truncated:
            data.truncated = True
        return {
            "id": "tables",
            "title": "Tables",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": len(retained),
            "truncated": truncated,
        }
    except Exception as exc:
        data.tables = []
        return {
            "id": "tables",
            "title": "Tables",
            "status": "FAILED",
            "reason": str(exc).strip(),
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }


def collect_lock_waits(conn: Any, masker: Masker, limits: RowLimits, data: DataSourceData) -> Dto:
    bound_sql = LOCK_WAITS_SQL.strip() + f" LIMIT {limits.max_lock_waits + 1}"
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(bound_sql).mappings()]
        lock_waits: list[Dto] = []
        for r in rows:
            waiting_q = mysql_query_text(masker, cast("str | None", r.get("waiting_query")))
            blocking_q = mysql_query_text(masker, cast("str | None", r.get("blocking_query")))
            lock_waits.append(
                {
                    "waitingTrxId": r.get("waiting_trx_id"),
                    "waitingPid": r.get("waiting_pid"),
                    "waitingQuery": waiting_q,
                    "blockingTrxId": r.get("blocking_trx_id"),
                    "blockingPid": r.get("blocking_pid"),
                    "blockingQuery": blocking_q,
                }
            )
        retained, truncated = read_one_past(lock_waits, limits.max_lock_waits)
        data.lock_waits = retained
        if truncated:
            data.truncated = True
        return {
            "id": "lock-waits",
            "title": "Lock Waits",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": len(retained),
            "truncated": truncated,
        }
    except Exception:
        # sys.innodb_lock_waits or pfs data_lock_waits may not exist on all versions
        data.lock_waits = []
        return {
            "id": "lock-waits",
            "title": "Lock Waits",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }


def collect_replication(conn: Any, limits: RowLimits, data: DataSourceData) -> Dto:
    bound_sql = REPLICATION_PFS_SQL.strip() + f" LIMIT {limits.max_replication_channels + 1}"
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(bound_sql).mappings()]
        channels: list[Dto] = [
            {
                "channelName": r.get("channel_name"),
                "serviceState": r.get("service_state"),
                "sourceUuid": r.get("source_uuid"),
                "lastErrorNumber": r.get("last_error_number"),
                "lastErrorMessage": r.get("last_error_message"),
                "lastErrorTimestamp": r.get("last_error_timestamp"),
            }
            for r in rows
        ]
        retained, truncated = read_one_past(channels, limits.max_replication_channels)
        data.replication_channels = retained
        if truncated:
            data.truncated = True
        return {
            "id": "replication-channels",
            "title": "Replication Channels",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": len(retained),
            "truncated": truncated,
        }
    except Exception:
        data.replication_channels = []
        return {
            "id": "replication-channels",
            "title": "Replication Channels",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }


def collect_settings(conn: Any, limits: RowLimits, data: DataSourceData) -> Dto:
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(SETTINGS_SQL).mappings()]
        found = {
            str(r["Variable_name"]).lower(): str(r["Value"]) for r in rows if "Variable_name" in r and "Value" in r
        }
        settings: list[Dto] = [
            {
                "name": name,
                "value": found[name.lower()],
                "scope": "GLOBAL",
                "source": "SERVER",
            }
            for name in sorted(CURATED_SETTINGS)
            if name.lower() in found
        ]
        retained, truncated = read_one_past(settings, limits.max_settings)
        data.settings = retained
        if truncated:
            data.truncated = True
        return {
            "id": "settings",
            "title": "Settings",
            "status": "AVAILABLE",
            "reason": None,
            "hint": None,
            "rowCount": len(retained),
            "truncated": truncated,
        }
    except Exception as exc:
        data.settings = []
        return {
            "id": "settings",
            "title": "Settings",
            "status": "FAILED",
            "reason": str(exc).strip(),
            "hint": None,
            "rowCount": 0,
            "truncated": False,
        }


def collect_metrics(conn: Any, data: DataSourceData) -> list[Dto]:
    try:
        with conn.begin_nested():
            rows: list[dict[str, Any]] = [dict(r) for r in conn.exec_driver_sql(STATUS_SQL).mappings()]
        status_map = {str(r["Variable_name"]): str(r["Value"]) for r in rows if "Variable_name" in r and "Value" in r}
        metrics: list[Dto] = []

        def add_metric(var_name: str, label: str, unit: str | None = None) -> None:
            if var_name in status_map:
                try:
                    val = float(status_map[var_name])
                    int_val = int(val) if val.is_integer() else val
                    metrics.append(
                        {
                            "id": var_name,
                            "label": label,
                            "value": int_val,
                            "unit": unit,
                            "scope": "GLOBAL",
                            "source": "STATUS",
                        }
                    )
                except (ValueError, TypeError):
                    pass

        add_metric("Threads_connected", "Threads connected")
        add_metric("Uptime", "Uptime", "seconds")
        add_metric("Queries", "Queries")
        add_metric("Slow_queries", "Slow queries")

        # Buffer pool hit ratio
        reads = status_map.get("Innodb_buffer_pool_reads")
        requests = status_map.get("Innodb_buffer_pool_read_requests")
        if reads is not None and requests is not None:
            try:
                r_val = float(reads)
                req_val = float(requests)
                if req_val > 0:
                    ratio = round((1.0 - (r_val / req_val)) * 100, 1)
                    metrics.append(
                        {
                            "id": "innodb_buffer_pool_hit_ratio",
                            "label": "Buffer pool hit ratio",
                            "value": ratio,
                            "unit": "%",
                            "scope": "GLOBAL",
                            "source": "STATUS",
                        }
                    )
            except (ValueError, TypeError):
                pass

        data.metrics = metrics
        return metrics
    except Exception:
        data.metrics = []
        return []


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
    collect_metrics(conn, data)

    collectors = (
        ("sessions", "Active sessions", lambda: collect_sessions(conn, masker, limits, data)),
        ("statements", "Top normalized statements", lambda: collect_statements(conn, masker, limits, data)),
        ("indexes", "Index usage and efficiency", lambda: collect_indexes(conn, limits, data)),
        ("tables", "Largest tables", lambda: collect_tables(conn, limits, data)),
        ("lock-waits", "Lock waits", lambda: collect_lock_waits(conn, masker, limits, data)),
        ("replication-channels", "Replication channels", lambda: collect_replication(conn, limits, data)),
        ("settings", "Notable configuration", lambda: collect_settings(conn, limits, data)),
    )

    for section_id, title, run_collector in collectors:
        if budget.exhausted():
            data.sections.append(
                {
                    "id": section_id,
                    "title": title,
                    "status": "SKIPPED",
                    "reason": BUDGET_SKIPPED,
                    "hint": None,
                    "rowCount": 0,
                    "truncated": False,
                }
            )
        else:
            run_collector()

    data.truncated = any(s.get("truncated", False) for s in data.sections)
    return data
