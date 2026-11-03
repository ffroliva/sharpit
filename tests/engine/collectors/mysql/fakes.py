"""Fake SQLAlchemy-shaped MySQL connection for unit testing collectors without I/O."""

from __future__ import annotations

from collections.abc import Generator, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

Row = dict[str, Any]


def kind_of(sql: str) -> str:
    checks = (
        ("@@version", "CAPABILITIES"),
        ("database()", "DATABASE"),
        ("SHOW GLOBAL STATUS", "STATUS"),
        ("SHOW GLOBAL VARIABLES", "VARIABLES"),
        ("performance_schema.threads", "SESSIONS"),
        ("information_schema.PROCESSLIST", "SESSIONS"),
        ("events_statements_summary_by_digest", "STATEMENTS"),
        ("information_schema.STATISTICS", "INDEXES"),
        ("information_schema.TABLES", "TABLES"),
        ("sys.innodb_lock_waits", "LOCK_WAITS"),
        ("performance_schema.data_lock_waits", "LOCK_WAITS"),
        ("replication_connection_status", "REPLICATION"),
        ("SHOW REPLICA STATUS", "REPLICATION"),
        ("SHOW SLAVE STATUS", "REPLICATION"),
    )
    for needle, kind in checks:
        if needle in sql:
            return kind
    return "UNKNOWN"


def default_rows(kind: str) -> list[Row]:
    defaults: dict[str, list[Row]] = {
        "CAPABILITIES": [
            {
                "version": "8.4.0",
                "version_comment": "MySQL Community Server - GPL",
                "performance_schema": 1,
            }
        ],
        "DATABASE": [{"current_database": "app"}],
        "STATUS": [
            {"Variable_name": "Threads_connected", "Value": "10"},
            {"Variable_name": "Uptime", "Value": "3600"},
            {"Variable_name": "Queries", "Value": "1000"},
            {"Variable_name": "Slow_queries", "Value": "0"},
            {"Variable_name": "Innodb_buffer_pool_reads", "Value": "5"},
            {"Variable_name": "Innodb_buffer_pool_read_requests", "Value": "95"},
        ],
        "VARIABLES": [
            {"Variable_name": "max_connections", "Value": "151"},
            {"Variable_name": "version", "Value": "8.4.0"},
            {"Variable_name": "autocommit", "Value": "ON"},
        ],
        "SESSIONS": [
            {
                "id": 1,
                "user": "app",
                "host": "localhost",
                "db": "app",
                "command": "Query",
                "time": 0,
                "state": "executing",
                "info": "SELECT 1",
                "current_statement": "SELECT 1",
            }
        ],
        "STATEMENTS": [
            {
                "schema_name": "app",
                "digest": "abc123",
                "digest_text": "SELECT * FROM users WHERE id = ?",
                "count_star": 10,
                "sum_timer_wait": 10000000000,
                "avg_timer_wait": 1000000000,
                "max_timer_wait": 2000000000,
                "sum_rows_affected": 0,
                "sum_rows_sent": 10,
                "sum_rows_examined": 10,
                "sum_no_index_used": 0,
            }
        ],
        "INDEXES": [
            {
                "table_schema": "app",
                "table_name": "users",
                "index_name": "PRIMARY",
                "non_unique": 0,
                "seq_in_index": 1,
                "column_name": "id",
                "cardinality": 100,
                "index_type": "BTREE",
            }
        ],
        "TABLES": [
            {
                "table_schema": "app",
                "table_name": "users",
                "table_type": "BASE TABLE",
                "engine": "InnoDB",
                "table_rows": 100,
                "avg_row_length": 160,
                "data_length": 16384,
                "index_length": 16384,
                "data_free": 0,
            }
        ],
        "LOCK_WAITS": [],
        "REPLICATION": [],
    }
    return defaults.get(kind, [])


class _Result:
    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows

    def scalar(self) -> Any:
        return next(iter(self._rows[0].values())) if self._rows else None

    def mappings(self) -> Iterator[Mapping[str, Any]]:
        yield from self._rows


class _Dialect:
    def __init__(self, name: str = "mysql", version: tuple[int, ...] = (8, 4, 0)) -> None:
        self.name = name
        self.is_async = False
        self.is_mariadb = "mariadb" in name.lower()
        self.server_version_info = version


class FakeMySqlConnection:
    def __init__(self, dialect: str = "mysql", version: tuple[int, ...] = (8, 4, 0)) -> None:
        self.dialect = _Dialect(dialect, version)
        self.rows: dict[str, list[Row]] = {}
        self.failures: dict[str, str] = {}
        self.sql: list[str] = []
        self.savepoints = 0
        self.aborted = False

    def with_rows(self, kind: str, *rows: Row) -> FakeMySqlConnection:
        self.rows[kind] = list(rows)
        return self

    def fail(self, kind: str, message: str) -> FakeMySqlConnection:
        self.failures[kind] = message
        return self

    def exec_driver_sql(self, sql: str) -> _Result:
        self.sql.append(sql)
        kind = kind_of(sql)
        if kind in self.failures:
            raise RuntimeError(self.failures[kind])
        rows = self.rows.get(kind, default_rows(kind))
        limit = _limit_of(sql)
        return _Result(rows if limit is None else rows[:limit])

    @contextmanager
    def begin_nested(self) -> Generator[None]:
        self.savepoints += 1
        try:
            yield
        except BaseException:
            # savepoint rollback
            raise


class FakeMySqlEngine:
    def __init__(self, conn: FakeMySqlConnection | None = None, refuse: str | None = None) -> None:
        self.conn = conn or FakeMySqlConnection()
        self.dialect = self.conn.dialect
        self.refuse = refuse
        self.connects = 0

    @contextmanager
    def connect(self) -> Generator[FakeMySqlConnection]:
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
