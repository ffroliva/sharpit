"""MySQL/MariaDB read-only reads against a real server (0.5.0 spec §5.0, plan F5b Task 3): the acceptance tests.

They need a leased server: ``SHARPIT_TEST_MYSQL_URL`` (``mysql://user:pass@host:port/db``, read with pymysql) whose user
may create a table in that database. Without it they skip.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from sharpit.engine import sqla

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

MYSQL_URL = os.environ.get("SHARPIT_TEST_MYSQL_URL", "")
NEEDS_MYSQL = pytest.mark.skipif(not MYSQL_URL, reason="requires a leased MySQL/MariaDB via SHARPIT_TEST_MYSQL_URL")
ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION = 1792


def _engine(**kwargs: Any) -> Any:
    pytest.importorskip("pymysql")
    url = MYSQL_URL.replace("mysql://", "mysql+pymysql://", 1) if MYSQL_URL.startswith("mysql://") else MYSQL_URL
    return sa.create_engine(url, pool_size=1, max_overflow=0, **kwargs)  # one connection: the next checkout is it


def _read(engine: Any, fn: Any) -> Any:
    try:
        return asyncio.run(sqla.run_db_read(engine, fn, 5.0, read_only=True))
    except Exception as exc:  # noqa: BLE001 - the tests assert on what came back
        return exc


@NEEDS_MYSQL
def test_mysql_read_only_wrapper_rejects_write() -> None:
    engine = _engine()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS sharpit_ro_probe (id INT)")
    try:
        outcome = _read(engine, lambda c: c.exec_driver_sql("INSERT INTO sharpit_ro_probe VALUES (1)"))
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT count(*) FROM sharpit_ro_probe").scalar()
            read_only = conn.exec_driver_sql("SELECT @@SESSION.transaction_read_only").scalar()

        assert getattr(getattr(outcome, "orig", None), "args", (None,))[0] == ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION
        assert rows == 0
        assert read_only == 0
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS sharpit_ro_probe")
        engine.dispose()


@NEEDS_MYSQL
def test_mysql_autocommit_engine_refused() -> None:
    engine = _engine(isolation_level="AUTOCOMMIT")
    try:
        outcome = _read(engine, lambda c: c.exec_driver_sql("SELECT 1").scalar())

        assert isinstance(outcome, sqla.ReadOnlyUnavailable)
    finally:
        engine.dispose()
