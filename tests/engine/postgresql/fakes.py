"""A fake SQLAlchemy-shaped PostgreSQL connection (port of BootUI ``PostgresTestDataSources``).

Queries are routed to a kind by their text, as BootUI's fake does. A failed statement outside a savepoint aborts the
transaction, as PostgreSQL does, so a collector that forgets ``begin_nested()`` poisons every later query.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

Row = dict[str, Any]


def kind_of(sql: str) -> str:  # ported: PostgresTestDataSources.QueryKind.of
    checks = (
        ("current_user", "ROLE"),
        ("current_database() as database_name", "VITALS"),
        ("from pg_settings", "SETTINGS"),
        ("pg_blocking_pids", "SESSIONS"),
        ("from pg_stat_activity", "ACTIVITY"),
        ("pg_extension", "EXTENSION"),
        ("pg_stat_statements s", "STATEMENTS"),
        ("from pg_stat_user_indexes", "INDEXES"),
        ("order by total_size", "TABLES"),
        ("n_dead_tup desc", "VACUUM"),
        ("pg_is_in_recovery", "RECOVERY"),
        ("from pg_stat_replication", "REPLICAS"),
        ("pg_stat_bgwriter", "CHECKPOINTS"),
        ("pg_stat_checkpointer", "CHECKPOINTS"),
        ("from pg_replication_slots", "SLOTS"),
    )
    for needle, kind in checks:
        if needle in sql:
            return kind
    raise AssertionError(f"unexpected SQL: {sql}")


def _settings() -> list[Row]:
    values = (
        ("autovacuum", "on"),
        ("autovacuum_vacuum_threshold", "50"),
        ("autovacuum_vacuum_scale_factor", "0.2"),
        ("fsync", "on"),
        ("full_page_writes", "on"),
        ("track_io_timing", "on"),
        ("wal_level", "replica"),
    )
    return [{"name": n, "setting": v, "unit": None, "source": "default"} for n, v in values]


def default_rows(kind: str) -> list[Row]:
    defaults: dict[str, list[Row]] = {
        "ROLE": [{"role_name": "sharpit", "monitoring": True}],
        "SETTINGS": _settings(),
        "VITALS": [
            {
                "database_name": "app",
                "database_size": 1024,
                "xact_commit": 100,
                "xact_rollback": 0,
                "blks_read": 1,
                "blks_hit": 99,
                "backends": 1,
                "deadlocks": 0,
                "temp_files": 0,
                "temp_bytes": 0,
                "xid_age": 1,
                "freeze_max_age": 200_000_000,
                "max_connections": 100,
            }
        ],
        "ACTIVITY": [
            {"active_sessions": 1, "idle_in_transaction": 0, "blocked_sessions": 0, "longest_transaction_seconds": 0.0}
        ],
        "SESSIONS": [
            {
                "pid": 42,
                "user_name": "app",
                "application_name": "sample-app",
                "client_address": "127.0.0.1",
                "state": "active",
                "wait_event_type": None,
                "wait_event": None,
                "blocked_by": None,
                "state_seconds": 0.2,
                "transaction_seconds": 0.4,
                "query_seconds": 0.2,
                "query": "select 1",
            }
        ],
        "EXTENSION": [{"relation": "pg_stat_statements", "exec_naming": 1}],
        "RECOVERY": [{"in_recovery": False, "has_checkpointer": False}],
        "CHECKPOINTS": [{"checkpoints_timed": 10, "checkpoints_requested": 0, "write_time": 0.0}],
        "SLOTS": [{"slots": 0, "inactive_slots": 0}],
    }
    return defaults.get(kind, [])


class _Result:
    def __init__(self, rows: list[Row], on_row: Callable[[int], None] | None) -> None:
        self._rows = rows
        self._on_row = on_row

    def mappings(self) -> Iterator[Mapping[str, Any]]:
        for index, row in enumerate(self._rows):
            if self._on_row is not None:
                self._on_row(index)
            yield row


class FakePgConnection:
    def __init__(self) -> None:
        self.rows: dict[str, list[Row]] = {}
        self.failures: dict[str, str] = {}
        self.on_row: dict[str, Callable[[int], None]] = {}
        self.sql: list[str] = []
        self.aborted = False
        self.savepoints = 0

    def with_rows(self, kind: str, *rows: Row) -> FakePgConnection:
        self.rows[kind] = list(rows)
        return self

    def fail(self, kind: str, message: str) -> FakePgConnection:
        self.failures[kind] = message
        return self

    def exec_driver_sql(self, sql: str) -> _Result:
        if self.aborted:
            raise RuntimeError("current transaction is aborted, commands ignored until end of transaction block")
        self.sql.append(sql)
        kind = kind_of(sql)
        if kind in self.failures:
            self.aborted = True
            raise RuntimeError(self.failures[kind])
        rows = self.rows.get(kind, default_rows(kind))
        limit = _limit_of(sql)
        return _Result(rows if limit is None else rows[:limit], self.on_row.get(kind))

    @contextmanager
    def begin_nested(self) -> Generator[None]:
        if self.aborted:
            raise RuntimeError("current transaction is aborted, commands ignored until end of transaction block")
        self.savepoints += 1
        try:
            yield
        except BaseException:
            self.aborted = False  # ROLLBACK TO SAVEPOINT
            raise


def _limit_of(sql: str) -> int | None:
    tail = sql.rstrip().rsplit(None, 2)
    if len(tail) == 3 and tail[1].lower() == "limit" and tail[2].isdigit():
        return int(tail[2])
    return None
