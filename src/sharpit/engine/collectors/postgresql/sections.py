"""The eight ``postgresql`` panel sections, read through one pinned read-only connection.

Port of BootUI ``engine/postgres`` (``PostgresQuery``, ``PostgresRows``, ``PostgresReadBudget``,
``PostgresDatabaseData`` and the eight ``*Collector`` classes). ``conn`` is the SQLAlchemy ``Connection`` that
``sqla.bounded_read_only`` hands over; only ``exec_driver_sql`` and ``begin_nested`` are used, so no SQLAlchemy import
is needed here. Every query runs in its own savepoint: PostgreSQL aborts the whole transaction on any error, and one
refused view must not turn every later section into "current transaction is aborted".
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NamedTuple

from sharpit.engine.collectors.postgresql.limits import RowLimits
from sharpit.engine.collectors.postgresql.querytext import is_metadata_only
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
        return cls(False, rows, not truncated)

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
    del ctx, label, sql, max_rows, mapper
    return Rows(False, [])


def read_one(ctx: ReadContext, label: str, sql: str, mapper: Callable[[Row], Any]) -> Rows:
    del ctx, label, sql, mapper
    return Rows(False, [])


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
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


def _vital_signs(ctx: ReadContext, data: DatabaseData) -> Dto:
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


def _sessions(ctx: ReadContext, data: DatabaseData) -> Dto:
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


def _statements(ctx: ReadContext, data: DatabaseData) -> Dto:
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


def _indexes(ctx: ReadContext, data: DatabaseData) -> Dto:
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


def sequential_scan_ratio(sequential: int | None, index: int | None) -> float | None:
    return None if sequential is None else _ratio(sequential, sequential + (index or 0))


def _tables(ctx: ReadContext, data: DatabaseData) -> Dto:
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


def vacuum_override(rel_option: str | None, cluster_value: float) -> float:
    del rel_option, cluster_value
    return 0.0


def is_false(rel_option: str | None) -> bool:
    del rel_option
    return False


def vacuum_threshold(live: int | None, threshold: float, scale_factor: float, max_threshold: float) -> int | None:
    del live, threshold, scale_factor, max_threshold
    return 0


def _dead_ratio(live: int | None, dead: int | None) -> float | None:
    return None if dead is None else _ratio(dead, dead + (live or 0))


def _vacuum(ctx: ReadContext, data: DatabaseData) -> Dto:
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


def _replication(ctx: ReadContext, data: DatabaseData) -> Dto:
    del ctx, data
    return {"id": "", "title": "", "status": "FAILED", "reason": "", "hint": "", "rowCount": 0, "truncated": False}


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
    del conn, masker, limits, budget
    return DatabaseData("")
