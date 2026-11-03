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
