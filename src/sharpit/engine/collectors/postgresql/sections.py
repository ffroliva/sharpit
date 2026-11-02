"""The eight ``postgresql`` panel sections, read through one pinned read-only connection.

Port of BootUI ``engine/postgres`` (``PostgresQuery``, ``PostgresRows``, ``PostgresReadBudget``,
``PostgresDatabaseData`` and the eight ``*Collector`` classes). ``conn`` is the SQLAlchemy ``Connection`` that
``sqla.bounded_read_only`` hands over; only ``exec_driver_sql`` and ``begin_nested`` are used, so no SQLAlchemy import
is needed here. Every query runs in its own savepoint: PostgreSQL aborts the whole transaction on any error, and one
refused view must not turn every later section into "current transaction is aborted".
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NamedTuple

from sharpit.engine.collectors.postgresql import queries
from sharpit.engine.collectors.postgresql.limits import RowLimits
from sharpit.engine.collectors.postgresql.queries import checkpoint_sql, statement_sql
from sharpit.engine.collectors.postgresql.querytext import is_metadata_only, query_text, truncate
from sharpit.engine.masking import MASK, Masker

# PostgresSectionIds
SECTION_IDS = ("vital-signs", "sessions", "statements", "indexes", "tables", "vacuum", "replication", "settings")

BUDGET_SKIPPED = "The read budget ran out before this section was read."
RESTRICTED_SESSIONS_LIMITATION = (
    "pg_stat_activity hides the state of backends this role does not own, so the session breakdown "
    "(active, idle in transaction, blocked, oldest transaction) is unknown. Grant the sharpit "
    "role membership of pg_monitor to read it."
)
RESTRICTED_SESSION_LIST_LIMITATION = (
    "pg_stat_activity hides the backends this role does not own, so this list covers only sharpit's "
    "own sessions and is not the server's real activity. Grant the sharpit role membership of "
    "pg_monitor to see every session."
)
INSTALL_HINT = (
    "Install the extension (shared_preload_libraries = 'pg_stat_statements', then "
    "CREATE EXTENSION pg_stat_statements;) to rank statements by execution time."
)
INSUFFICIENT_PRIVILEGE = "<insufficient privilege>"
RESTRICTED_STATEMENTS_LIMITATION = (
    'pg_stat_statements shows the text of statements run by other roles as "<insufficient '
    'privilege>"; their timings are real but the statements cannot be identified. Grant the '
    "sharpit role membership of pg_monitor to read them."
)
ESTIMATE_LIMITATION = (
    'Autovacuum "due" is computed against the live-tuple estimate in pg_stat_user_tables, whereas '
    "autovacuum itself uses pg_class.reltuples, and only the dead-tuple trigger is modelled: "
    "an insert-only table can also be vacuumed by autovacuum_vacuum_insert_threshold."
)
RESTRICTED_REPLICA_LIMITATION = (
    "pg_stat_replication hides the WAL-sender details of replicas this role does not own, so each "
    "replica's state, sync state and lag are unknown even though the replicas themselves are "
    "listed. Grant the sharpit role membership of pg_monitor to read them."
)
STANDBY_LIMITATION = (
    "This server is a standby, so the replica list and lag were not read; "
    "downstream cascading replicas may still be connected."
)

Row = Mapping[str, Any]
Dto = dict[str, Any]


class ReadBudget:
    """PostgresReadBudget: one wall-clock deadline, checked between queries and rows (never interrupting one)."""

    def __init__(self, deadline: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.deadline = deadline
        self._clock = clock

    @classmethod
    def start(cls, seconds: float, clock: Callable[[], float] = time.monotonic) -> ReadBudget:
        return cls(clock() + seconds, clock)

    def exhausted(self) -> bool:
        return self._clock() >= self.deadline

    def remaining(self) -> float:
        return max(0.0, self.deadline - self._clock())


@dataclass(frozen=True)
class Rows:
    """PostgresRows: a failed read is never an empty successful one."""

    available: bool
    rows: list[Any]
    truncated: bool = False
    reason: str | None = None

    @classmethod
    def of(cls, rows: list[Any], truncated: bool = False) -> Rows:
        return cls(True, list(rows), truncated)

    @classmethod
    def failed(cls, reason: str) -> Rows:
        return cls(False, [], False, reason)

    @classmethod
    def partial(cls, rows: list[Any], reason: str) -> Rows:
        return cls.failed(reason) if not rows else cls(True, list(rows), False, reason)


@dataclass
class DatabaseData:
    """PostgresDatabaseData: what one engine's sections fill in, plus the raw settings later sections need."""

    name: str
    role: str | None = None
    statistics_restricted: bool = False
    sections: list[Dto] = field(default_factory=lambda: [])
    setting_values: dict[str, str] = field(default_factory=lambda: {})
    vital_signs: Dto | None = None
    sessions: list[Dto] = field(default_factory=lambda: [])
    statements: list[Dto] = field(default_factory=lambda: [])
    indexes: list[Dto] = field(default_factory=lambda: [])
    tables: list[Dto] = field(default_factory=lambda: [])
    vacuum: list[Dto] = field(default_factory=lambda: [])
    replication: Dto | None = None
    settings: list[Dto] = field(default_factory=lambda: [])
    truncated: bool = False

    def add_section(self, section: Dto) -> None:
        self.sections.append(section)
        self.truncated = self.truncated or section["truncated"]

    def section(self, section_id: str) -> Dto | None:
        return next((s for s in self.sections if s["id"] == section_id), None)

    def setting(self, name: str) -> str | None:
        return self.setting_values.get(name)

    def setting_as_float(self, name: str, fallback: float) -> float:
        return vacuum_override(self.setting(name), fallback)


@dataclass(frozen=True)
class ReadContext:
    """PostgresReadContext: the pinned connection, the live masking policy, the bounds and the shared budget."""

    conn: Any
    masker: Masker
    limits: RowLimits
    budget: ReadBudget


# ---- PostgresQuery ---------------------------------------------------------------------------------------------------


def append_sentence(reason: str | None, sentence: str) -> str:
    if not reason or not reason.strip():
        return sentence
    return f"{reason}{' ' if reason.endswith(('.', '!', '?')) else '. '}{sentence}"


def _describe(ctx: ReadContext, label: str, exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return f"{label} could not be read: {ctx.masker.mask_text(message) or type(exc).__name__}"


def read_list(ctx: ReadContext, label: str, sql: str, max_rows: int, mapper: Callable[[Row], Dto | None]) -> Rows:
    """A bounded list: ``limit max + 1`` so exceeding the bound is observed, never a full-looking page."""
    if ctx.budget.exhausted():
        return Rows.failed(f"The read budget ran out before {label} could be read.")
    rows: list[Dto] = []
    truncated = False
    reason: str | None = None
    try:
        with ctx.conn.begin_nested():
            for read, row in enumerate(ctx.conn.exec_driver_sql(_limited(sql, max_rows + 1)).mappings()):
                if read >= max_rows:
                    truncated = True
                    break
                if ctx.budget.exhausted():
                    reason = f"The read budget ran out while reading {label}."
                    break
                mapped = mapper(row)
                if mapped is not None:
                    rows.append(mapped)
    except Exception as exc:  # noqa: BLE001 - every driver error becomes the section's reason
        return Rows.failed(_describe(ctx, label, exc))
    return Rows.of(rows, truncated) if reason is None else Rows.partial(rows, reason)


def _limited(sql: str, limit: int) -> str:
    return f"{sql.replace('{limit}', str(limit)).rstrip()}\nlimit {limit}"


def read_one(ctx: ReadContext, label: str, sql: str, mapper: Callable[[Row], Any]) -> Rows:
    """A single-row query; no row is an available, empty outcome."""
    if ctx.budget.exhausted():
        return Rows.failed(f"The read budget ran out before {label} could be read.")
    try:
        with ctx.conn.begin_nested():
            row = next(iter(ctx.conn.exec_driver_sql(sql).mappings()), None)
            mapped = None if row is None else mapper(row)
    except Exception as exc:  # noqa: BLE001 - every driver error becomes the section's reason
        return Rows.failed(_describe(ctx, label, exc))
    return Rows.of([] if mapped is None else [mapped])


def _int(row: Row, column: str) -> int | None:
    value = row.get(column)
    return None if value is None else int(value)


def _float(row: Row, column: str) -> float | None:
    value = row.get(column)  # psycopg hands numeric back as Decimal
    return None if value is None else float(value)


def _str(row: Row, column: str) -> str | None:
    value = row.get(column)
    return None if value is None else str(value)


def _epoch_ms(row: Row, column: str) -> int | None:
    value = row.get(column)
    return int(value.timestamp() * 1000) if isinstance(value, datetime) else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _client_address(ctx: ReadContext, address: str | None) -> str | None:
    if address is None:
        return None
    return MASK if is_metadata_only(ctx.masker) else address


# ---- sections ------------------------------------------------------------------------------------------------------


class Collector(NamedTuple):
    id: str
    title: str
    collect: Callable[[ReadContext, DatabaseData], Dto]


def _section(
    c: Collector, status: str, reason: str | None = None, hint: str | None = None, rows: int = 0, cut: bool = False
) -> Dto:
    return {"id": c.id, "title": c.title, "status": status, "reason": reason, "hint": hint, "rowCount": rows,
            "truncated": cut}  # fmt: skip


def _list_section(c: Collector, rows: Rows, restricted_note: str | None = None) -> Dto:
    reason = rows.reason if restricted_note is None else append_sentence(rows.reason, restricted_note)
    return _section(c, "AVAILABLE", reason, rows=len(rows.rows), cut=rows.truncated)


def _settings(ctx: ReadContext, data: DatabaseData) -> Dto:
    metadata_only = is_metadata_only(ctx.masker)
    raw: dict[str, str] = {}

    def mapper(row: Row) -> Dto:
        name, value = str(row["name"]), _str(row, "setting")
        if value is not None:
            raw[name] = value  # kept for the vacuum rule even when the value is withheld
        shown = MASK if metadata_only else truncate(value, 120)
        return {"name": name, "value": shown, "unit": _str(row, "unit"), "source": _str(row, "source"),
                "note": queries.NOTABLE_SETTINGS.get(name)}  # fmt: skip

    rows = read_list(ctx, "Server settings", queries.SETTINGS_SQL, ctx.limits.max_settings, mapper)
    if not rows.available:
        return _section(SETTINGS, "FAILED", rows.reason)
    data.settings = rows.rows
    data.setting_values.update(raw)
    return _list_section(SETTINGS, rows)


def _vital_signs(ctx: ReadContext, data: DatabaseData) -> Dto:
    counters = read_one(ctx, "Database statistics", queries.DATABASE_SQL, dict)
    if not counters.available:
        return _section(VITAL_SIGNS, "FAILED", counters.reason)
    if not counters.rows:
        return _section(
            VITAL_SIGNS,
            "SKIPPED",
            "pg_stat_database reported no row for the current database.",
            "Grant the sharpit role membership of pg_monitor so it can read the database statistics views.",
        )
    row: Row = counters.rows[0]
    activity = read_one(ctx, "Session activity", queries.ACTIVITY_SQL, dict)
    session: Row = activity.rows[0] if activity.available and activity.rows and not data.statistics_restricted else {}
    hit, read = _int(row, "blks_hit"), _int(row, "blks_read")
    committed, rolled_back = _int(row, "xact_commit"), _int(row, "xact_rollback")
    backends, max_connections = _int(row, "backends"), _int(row, "max_connections")
    xid_age, freeze_max_age = _int(row, "xid_age"), _int(row, "freeze_max_age")
    blocks = None if hit is None and read is None else (hit or 0) + (read or 0)
    xacts = None if committed is None and rolled_back is None else (committed or 0) + (rolled_back or 0)
    data.vital_signs = {
        "databaseName": _str(row, "database_name"),
        "cacheHitRatio": _ratio(hit, blocks),
        "rollbackRatio": _ratio(rolled_back, xacts),
        "transactionsCommitted": committed,
        "transactionsRolledBack": rolled_back,
        "connections": backends,
        "maxConnections": max_connections,
        "connectionUsageRatio": _ratio(backends, max_connections),
        "activeSessions": _int(session, "active_sessions"),
        "idleInTransactionSessions": _int(session, "idle_in_transaction"),
        "longestTransactionSeconds": _float(session, "longest_transaction_seconds"),
        "blockedSessions": _int(session, "blocked_sessions"),
        "transactionIdAge": xid_age,
        "wraparoundLimit": freeze_max_age,
        "wraparoundUsageRatio": _ratio(xid_age, freeze_max_age),
        "databaseSizeBytes": _int(row, "database_size"),
        "deadlocks": _int(row, "deadlocks"),
        "temporaryFiles": _int(row, "temp_files"),
        "temporaryBytes": _int(row, "temp_bytes"),
    }
    if not activity.available:
        return _section(VITAL_SIGNS, "AVAILABLE", activity.reason, rows=1)
    if data.statistics_restricted:
        return _section(VITAL_SIGNS, "AVAILABLE", RESTRICTED_SESSIONS_LIMITATION, rows=1)
    return _section(VITAL_SIGNS, "AVAILABLE", rows=1)


def _sessions(ctx: ReadContext, data: DatabaseData) -> Dto:
    def mapper(row: Row) -> Dto:
        return {
            "pid": _int(row, "pid") or 0,
            "user": _str(row, "user_name"),
            "applicationName": query_text(ctx.masker, _str(row, "application_name")),
            "clientAddress": _client_address(ctx, _str(row, "client_address")),
            "state": _str(row, "state"),
            "waitEventType": _str(row, "wait_event_type"),
            "waitEvent": _str(row, "wait_event"),
            "blockedBy": _str(row, "blocked_by"),
            "stateSeconds": _float(row, "state_seconds"),
            "transactionSeconds": _float(row, "transaction_seconds"),
            "querySeconds": _float(row, "query_seconds"),
            "query": query_text(ctx.masker, _str(row, "query")),
        }

    rows = read_list(ctx, "Session activity", queries.SESSIONS_SQL, ctx.limits.max_sessions, mapper)
    if not rows.available:
        return _section(SESSIONS, "FAILED", rows.reason)
    data.sessions = rows.rows
    return _list_section(SESSIONS, rows, RESTRICTED_SESSION_LIST_LIMITATION if data.statistics_restricted else None)


def _statements(ctx: ReadContext, data: DatabaseData) -> Dto:
    extension = read_one(
        ctx,
        "pg_stat_statements availability",
        queries.EXTENSION_SQL,
        lambda row: (_str(row, "relation"), (_int(row, "exec_naming") or 0) > 0),
    )
    if not extension.available:
        return _section(STATEMENTS, "FAILED", extension.reason)
    if not extension.rows or extension.rows[0][0] is None:
        return _section(
            STATEMENTS, "SKIPPED", "The pg_stat_statements extension is not installed on this server.", INSTALL_HINT
        )
    relation, exec_naming = extension.rows[0]

    def mapper(row: Row) -> Dto:
        hits, reads = _int(row, "shared_blks_hit"), _int(row, "shared_blks_read")
        return {
            "queryId": _str(row, "query_id"),
            "query": query_text(ctx.masker, _str(row, "query")),
            "calls": _int(row, "calls"),
            "totalTimeMs": _float(row, "total_time"),
            "meanTimeMs": _float(row, "mean_time"),
            "maxTimeMs": _float(row, "max_time"),
            "rows": _int(row, "rows_returned"),
            "cacheHitRatio": None if hits is None or reads is None else _ratio(hits, hits + reads),
        }

    rows = read_list(
        ctx, "Statement statistics", statement_sql(relation, exec_naming), ctx.limits.max_statements, mapper
    )
    if not rows.available:
        return _section(STATEMENTS, "FAILED", rows.reason)
    data.statements = rows.rows
    placeholders = any(s["query"] == INSUFFICIENT_PRIVILEGE for s in rows.rows)
    restricted = data.statistics_restricted or placeholders
    return _list_section(STATEMENTS, rows, RESTRICTED_STATEMENTS_LIMITATION if restricted else None)


def _indexes(ctx: ReadContext, data: DatabaseData) -> Dto:
    def mapper(row: Row) -> Dto:
        return {
            "schema": _str(row, "schema_name"),
            "table": _str(row, "table_name"),
            "index": _str(row, "index_name"),
            "scans": _int(row, "scans"),
            "tuplesRead": _int(row, "tuples_read"),
            "sizeBytes": _int(row, "size_bytes"),
            "unique": bool(row.get("is_unique")),
            "primaryKey": bool(row.get("is_primary")),
            "constraintBacked": bool(row.get("constraint_backed")),
        }

    rows = read_list(ctx, "Index usage statistics", queries.INDEXES_SQL, ctx.limits.max_indexes, mapper)
    if not rows.available:
        return _section(INDEXES, "FAILED", rows.reason)
    data.indexes = rows.rows
    return _list_section(INDEXES, rows)


def sequential_scan_ratio(sequential: int | None, index: int | None) -> float | None:
    return None if sequential is None else _ratio(sequential, sequential + (index or 0))


def _tables(ctx: ReadContext, data: DatabaseData) -> Dto:
    def mapper(row: Row) -> Dto:
        sequential, index = _int(row, "sequential_scans"), _int(row, "index_scans")
        return {
            "schema": _str(row, "schema_name"),
            "table": _str(row, "table_name"),
            "totalSizeBytes": _int(row, "total_size"),
            "tableSizeBytes": _int(row, "table_size"),
            "indexSizeBytes": _int(row, "index_size"),
            "liveTuples": _int(row, "live_tuples"),
            "deadTuples": _int(row, "dead_tuples"),
            "sequentialScans": sequential,
            "sequentialTuplesRead": _int(row, "sequential_tuples"),
            "indexScans": index,
            "sequentialScanRatio": sequential_scan_ratio(sequential, index),
        }

    rows = read_list(ctx, "Table statistics", queries.TABLES_SQL, ctx.limits.max_tables, mapper)
    if not rows.available:
        return _section(TABLES, "FAILED", rows.reason)
    data.tables = rows.rows
    return _list_section(TABLES, rows)


def vacuum_override(rel_option: str | None, cluster_value: float) -> float:
    if rel_option is None or not rel_option.strip():
        return cluster_value
    try:
        value = float(rel_option.strip())
    except ValueError:
        return cluster_value
    return value if math.isfinite(value) else cluster_value


def is_false(rel_option: str | None) -> bool:
    """Every unambiguous PostgreSQL spelling of false; ``o`` (on or off?) is not one."""
    if rel_option is None or not rel_option.strip():
        return False
    value = rel_option.strip().lower()
    if value in {"0", "f", "n"}:
        return True
    return len(value) >= 2 and any(word.startswith(value) for word in ("false", "off", "no"))


def vacuum_threshold(live: int | None, threshold: float, scale_factor: float, max_threshold: float) -> int | None:
    """Floored, as PostgreSQL compares an integer dead count against it; a negative cap means no cap."""
    if live is None:
        return None
    trigger = threshold + scale_factor * live
    if max_threshold >= 0:
        trigger = min(trigger, max_threshold)
    return math.floor(trigger)


def _dead_ratio(live: int | None, dead: int | None) -> float | None:
    return None if dead is None else _ratio(dead, dead + (live or 0))


def _vacuum(ctx: ReadContext, data: DatabaseData) -> Dto:
    autovacuum = str(data.setting("autovacuum")).lower() != "off"
    threshold = data.setting_as_float("autovacuum_vacuum_threshold", 50)
    scale_factor = data.setting_as_float("autovacuum_vacuum_scale_factor", 0.2)
    max_threshold = data.setting_as_float("autovacuum_vacuum_max_threshold", -1)  # PostgreSQL 18; absent = no cap

    def mapper(row: Row) -> Dto:
        live, dead = _int(row, "live_tuples"), _int(row, "dead_tuples")
        enabled = autovacuum and not is_false(_str(row, "rel_autovacuum_enabled"))
        trigger = vacuum_threshold(
            live,
            vacuum_override(_str(row, "rel_threshold"), threshold),
            vacuum_override(_str(row, "rel_scale_factor"), scale_factor),
            vacuum_override(_str(row, "rel_max_threshold"), max_threshold),
        )
        return {
            "schema": _str(row, "schema_name"),
            "table": _str(row, "table_name"),
            "liveTuples": live,
            "deadTuples": dead,
            "deadTupleRatio": _dead_ratio(live, dead),
            "vacuumThreshold": trigger,
            "vacuumDue": enabled and dead is not None and trigger is not None and dead > trigger,
            "autovacuumEnabled": enabled,
            "lastVacuum": _epoch_ms(row, "last_vacuum"),
            "lastAutoVacuum": _epoch_ms(row, "last_autovacuum"),
            "lastAnalyze": _epoch_ms(row, "last_analyze"),
            "lastAutoAnalyze": _epoch_ms(row, "last_autoanalyze"),
        }

    rows = read_list(ctx, "Vacuum statistics", queries.VACUUM_SQL, ctx.limits.max_vacuum_tables, mapper)
    if not rows.available:
        return _section(VACUUM, "FAILED", rows.reason)
    data.vacuum = rows.rows
    if data.setting("autovacuum_vacuum_threshold") is None:
        note = 'The autovacuum settings could not be read, so "due" is computed from PostgreSQL\'s defaults.'
        return _list_section(VACUUM, rows, note)
    return _section(VACUUM, "AVAILABLE", rows.reason, ESTIMATE_LIMITATION, len(rows.rows), rows.truncated)


def _replication(ctx: ReadContext, data: DatabaseData) -> Dto:
    recovery = read_one(
        ctx, "Recovery state", queries.RECOVERY_SQL, lambda r: (bool(r["in_recovery"]), bool(r["has_checkpointer"]))
    )
    if not recovery.available:
        return _section(REPLICATION, "FAILED", recovery.reason)
    in_recovery, has_checkpointer = recovery.rows[0] if recovery.rows else (False, False)
    replicas: list[Dto] = []
    replicas_available = truncated = False
    limitations: list[str] = []  # every sub-read's reason is kept, so the standby note never hides a real failure
    if in_recovery:
        limitations.append(STANDBY_LIMITATION)
    else:

        def mapper(row: Row) -> Dto:
            return {
                "applicationName": _str(row, "application_name"),
                "clientAddress": _client_address(ctx, _str(row, "client_addr")),
                "state": _str(row, "state"),
                "syncState": _str(row, "sync_state"),
                "sentLagBytes": _int(row, "sent_lag"),
                "flushLagBytes": _int(row, "flush_lag"),
                "replayLagBytes": _int(row, "replay_lag"),
            }

        rows = read_list(ctx, "Replication statistics", queries.REPLICAS_SQL, ctx.limits.max_replicas, mapper)
        if rows.available:
            replicas, replicas_available, truncated = rows.rows, True, rows.truncated
            if rows.reason is not None:
                limitations.append(rows.reason)
            if replicas and data.statistics_restricted:
                limitations.append(RESTRICTED_REPLICA_LIMITATION)
        else:
            limitations.append(rows.reason or "")
    checkpoints = read_one(ctx, "Checkpoint statistics", checkpoint_sql(has_checkpointer), dict)
    checkpoint: Row = checkpoints.rows[0] if checkpoints.available and checkpoints.rows else {}
    if not checkpoints.available:
        limitations.append(checkpoints.reason or "")
    slots = read_one(ctx, "Replication slots", queries.SLOTS_SQL, dict)
    slot: Row = slots.rows[0] if slots.available and slots.rows else {}
    if not slots.available:
        limitations.append(slots.reason or "")
    write_ms = _float(checkpoint, "write_time")
    data.replication = {
        "inRecovery": in_recovery,
        "replicas": replicas,
        "checkpointsTimed": _int(checkpoint, "checkpoints_timed"),
        "checkpointsRequested": _int(checkpoint, "checkpoints_requested"),
        "checkpointWriteSeconds": None if write_ms is None else write_ms / 1000,
        "replicationSlots": _int(slot, "slots"),
        "inactiveReplicationSlots": _int(slot, "inactive_slots"),
        "walLevel": data.setting("wal_level"),
        "replicasAvailable": replicas_available,
    }
    reason = " ".join(limitations) if limitations else None
    return _section(REPLICATION, "AVAILABLE", reason, rows=len(replicas), cut=truncated)


# PostgresInsightService.COLLECTORS order: settings first, because vacuum and replication read its raw values
SETTINGS = Collector("settings", "Notable settings", _settings)
VITAL_SIGNS = Collector("vital-signs", "Vital signs", _vital_signs)
SESSIONS = Collector("sessions", "Sessions", _sessions)
STATEMENTS = Collector("statements", "Statement ranking", _statements)
INDEXES = Collector("indexes", "Index usage", _indexes)
TABLES = Collector("tables", "Largest relations", _tables)
VACUUM = Collector("vacuum", "Autovacuum health", _vacuum)
REPLICATION = Collector("replication", "Replication, checkpoints and WAL", _replication)
COLLECTORS = (SETTINGS, VITAL_SIGNS, SESSIONS, STATEMENTS, INDEXES, TABLES, VACUUM, REPLICATION)


def collect(conn: Any, masker: Masker, limits: RowLimits, budget: ReadBudget) -> DatabaseData:
    """Every section of one engine, on a connection ``sqla.bounded_read_only`` already pinned read-only."""
    ctx = ReadContext(conn, masker, limits, budget)
    data = DatabaseData("")
    role = read_one(
        ctx, "Connected role", queries.ROLE_SQL, lambda r: (_str(r, "role_name"), bool(r.get("monitoring")))
    )
    data.role, monitoring = role.rows[0] if role.available and role.rows else (None, False)
    data.statistics_restricted = not monitoring
    for collector in COLLECTORS:
        if budget.exhausted():
            data.add_section(_section(collector, "SKIPPED", BUDGET_SKIPPED))
        else:
            data.add_section(collector.collect(ctx, data))
    return data
