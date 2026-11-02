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
    def __init__(self, rows: list[Row], on_row: Callable[[int], None] | None = None) -> None:
        self._rows = rows
        self._on_row = on_row

    def scalar(self) -> Any:
        return next(iter(self._rows[0].values())) if self._rows else None

    def mappings(self) -> Iterator[Mapping[str, Any]]:
        for index, row in enumerate(self._rows):
            if self._on_row is not None:
                self._on_row(index)
            yield row


class _Dialect:
    def __init__(self, name: str) -> None:
        self.name = name
        self.is_async = False
        self.server_version_info = (16, 4)


class FakePgConnection:
    def __init__(self, dialect: str = "postgresql") -> None:
        self.dialect = _Dialect(dialect)
        self.setup_error: str | None = None  # raised by the SET statements, like a connection dropped mid-setup
        self.read_only_setting = "on"  # 'off' is what an AUTOCOMMIT connection reports after SET TRANSACTION READ ONLY
        self.rolled_back = 0
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
        if sql.startswith("SET "):
            if self.setup_error is not None:
                raise RuntimeError(self.setup_error)
            return _Result([])
        if sql == "SELECT current_setting('transaction_read_only')":
            return _Result([{"transaction_read_only": self.read_only_setting}])
        kind = kind_of(sql)
        if kind in self.failures:
            self.aborted = True
            raise RuntimeError(self.failures[kind])
        rows = self.rows.get(kind, default_rows(kind))
        limit = _limit_of(sql)
        return _Result(rows if limit is None else rows[:limit], self.on_row.get(kind))

    def in_transaction(self) -> bool:
        return True

    def rollback(self) -> None:
        self.rolled_back += 1
        self.aborted = False

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


class FakePgEngine:
    """Enough of a sync ``Engine`` for ``sqla.run_db_read``: ``dialect`` and ``connect()``."""

    def __init__(self, conn: FakePgConnection | None = None, refuse: str | None = None) -> None:
        self.conn = conn or FakePgConnection()
        self.dialect = self.conn.dialect
        self.refuse = refuse
        self.connects = 0

    @contextmanager
    def connect(self) -> Generator[FakePgConnection]:
        self.connects += 1
        if self.refuse is not None:
            raise RuntimeError(self.refuse)
        yield self.conn


class FakeRegistry:
    def __init__(self, *engines: tuple[str, Any]) -> None:
        self._engines = list(engines)
        self.calls = 0

    def engines(self) -> list[tuple[str, Any]]:
        self.calls += 1
        return list(self._engines)


def _limit_of(sql: str) -> int | None:
    tail = sql.rstrip().rsplit(None, 2)
    if len(tail) == 3 and tail[1].lower() == "limit" and tail[2].isdigit():
        return int(tail[2])
    return None
