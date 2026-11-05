"""The database advisor scan against leased servers (0.5.0 plan A-dbadv-1 Task 5; scenario rows 22, 23, 28).

They need ``SHARPIT_TEST_POSTGRES_URL`` (``postgresql+psycopg://...``) and/or ``SHARPIT_TEST_MYSQL_URL``
(``mysql://user:pass@host:port/db``, read with pymysql) whose user may create a table. Without them they skip; the
coordinator runs them on leased servers (``gate/leased-pg.log``, ``gate/leased-mysql.log``).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from sharpit.engine import sqla
from sharpit.engine.sqla import inspect as sqla_inspect

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

PG_URL = os.environ.get("SHARPIT_TEST_POSTGRES_URL", "")
MYSQL_URL = os.environ.get("SHARPIT_TEST_MYSQL_URL", "")
SERVERS = [
    pytest.param(
        PG_URL,
        id="postgresql",
        marks=pytest.mark.skipif(not PG_URL, reason="requires a leased PostgreSQL via SHARPIT_TEST_POSTGRES_URL"),
    ),
    pytest.param(
        MYSQL_URL.replace("mysql://", "mysql+pymysql://", 1),
        id="mysql",
        marks=pytest.mark.skipif(not MYSQL_URL, reason="requires a leased MySQL via SHARPIT_TEST_MYSQL_URL"),
    ),
]


def _engine(url: str) -> Any:
    return sa.create_engine(url, pool_size=1, max_overflow=0)  # one connection: the next checkout is the read's


@pytest.mark.parametrize("url", SERVERS)
def test_read_only_wrapper_rejects_write(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # scenario row 23: a write attempted from inside the advisor's catalog read is refused by the server
    engine = _engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS sharpit_dbadv_probe (id INTEGER PRIMARY KEY)")
    inspector_class = sa.engine.reflection.Inspector
    original = inspector_class.get_columns
    refused: list[str] = []

    def get_columns(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            with self.bind.begin_nested():
                self.bind.exec_driver_sql("INSERT INTO sharpit_dbadv_probe VALUES (1)")
        except Exception as exc:  # noqa: BLE001 - the test asserts on the refusal
            refused.append(type(exc).__name__)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(inspector_class, "get_columns", get_columns)
    try:
        found = asyncio.run(
            sqla.run_db_read(
                engine, lambda c: sqla_inspect.catalog(c, sqla_inspect.CatalogBounds()), 5.0, read_only=True
            )
        )
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT count(*) FROM sharpit_dbadv_probe").scalar()

        assert refused
        assert rows == 0
        assert "sharpit_dbadv_probe" in [t["name"] for t in found["tables"]]
    finally:
        monkeypatch.undo()
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS sharpit_dbadv_probe")
        engine.dispose()


@pytest.mark.parametrize("url", SERVERS)
def test_server_limits_are_read(url: str) -> None:
    # the pool rules' evidence: max_connections is read by name on both servers
    engine = _engine(url)
    try:
        found = asyncio.run(
            sqla.run_db_read(
                engine, lambda c: sqla_inspect.catalog(c, sqla_inspect.CatalogBounds()), 5.0, read_only=True
            )
        )

        assert "max_connections" in found["server"]
    finally:
        engine.dispose()


# --- lane A-dbadv-2: the vendor rules against a server, through the scan's own read-only read --------------------

PG_VENDOR = ("DB-PG-001", "DB-PG-002", "DB-PG-003", "DB-PG-004", "DB-PG-005", "DB-SERVER-001", "DB-SERVER-002")
MYSQL_VENDOR = ("DB-SCHEMA-010", "DB-MYSQL-001", "DB-MYSQL-002", "DB-MYSQL-003")


def _vendor_scan(url: str, dialect: str) -> tuple[list[str], dict[str, str], int, set[str], set[str]]:
    """Evaluated rule ids, skip reasons, probe rows after, and the table names before/after the scan's read."""
    from sharpit.engine.collectors.database_advisor import catalog, report  # noqa: PLC0415 - after importorskip

    engine = _engine(url)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS sharpit_dbadv2_probe (id INTEGER PRIMARY KEY)")
        before = set(sa.inspect(engine).get_table_names())
        found = asyncio.run(
            sqla.run_db_read(
                engine,
                lambda c: catalog._catalog_and_vendor(c, sqla_inspect.CatalogBounds()),  # noqa: SLF001
                5.0,
                read_only=True,
            )
        )
        source = catalog.Source("db", dialect, "driver", "AVAILABLE", None, found)
        evaluation = report.evaluate([source])
        reasons = {d["source"]: d["message"] for d in evaluation.detail.diagnostics}
        with engine.connect() as conn:
            rows = int(conn.exec_driver_sql("SELECT count(*) FROM sharpit_dbadv2_probe").scalar() or 0)
        after = set(sa.inspect(engine).get_table_names())
        return list(evaluation.evaluated), reasons, rows, before, after
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS sharpit_dbadv2_probe")
        engine.dispose()


@pytest.mark.skipif(not PG_URL, reason="requires a leased PostgreSQL via SHARPIT_TEST_POSTGRES_URL")
def test_pg_vendor_rules_against_server() -> None:
    evaluated, reasons, rows, before, after = _vendor_scan(PG_URL, "postgresql")

    assert [rule for rule in PG_VENDOR if rule in evaluated]
    assert [rule for rule in PG_VENDOR if "not read" in reasons.get(rule, "")] == []
    assert rows == 0
    assert after == before


@pytest.mark.skipif(not MYSQL_URL, reason="requires a leased MySQL via SHARPIT_TEST_MYSQL_URL")
def test_mysql_vendor_rules_against_server() -> None:
    url = MYSQL_URL.replace("mysql://", "mysql+pymysql://", 1)
    evaluated, reasons, rows, before, after = _vendor_scan(url, "mysql")

    assert [rule for rule in MYSQL_VENDOR if rule in evaluated]
    assert [rule for rule in MYSQL_VENDOR if "not read" in reasons.get(rule, "")] == []
    assert rows == 0
    assert after == before
