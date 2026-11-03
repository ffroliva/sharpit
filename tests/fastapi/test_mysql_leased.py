"""MySQL leased tests: verified read-only wrapper and full panel read against real MySQL 8.4."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

MYSQL_URL = os.environ.get("SHARPIT_TEST_MYSQL_URL", "")
NEEDS_MYSQL = pytest.mark.skipif(not MYSQL_URL, reason="requires leased MySQL via SHARPIT_TEST_MYSQL_URL")
ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION = 1792
LOCAL = ("127.0.0.1", 50000)


def _engine(**kwargs: Any) -> Any:
    pytest.importorskip("pymysql")
    url = MYSQL_URL.replace("mysql://", "mysql+pymysql://", 1) if MYSQL_URL.startswith("mysql://") else MYSQL_URL
    return sa.create_engine(url, pool_size=1, max_overflow=0, **kwargs)


def _read(engine: Any, fn: Any) -> Any:
    try:
        return asyncio.run(sqla.run_db_read(engine, fn, 5.0, read_only=True))
    except Exception as exc:  # noqa: BLE001
        return exc


@NEEDS_MYSQL
def test_read_only_wrapper_rejects_write() -> None:
    engine = _engine()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS sharpit_mysql_probe (id INT)")
    try:
        outcome = _read(engine, lambda c: c.exec_driver_sql("INSERT INTO sharpit_mysql_probe VALUES (1)"))
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT count(*) FROM sharpit_mysql_probe").scalar()
            read_only = conn.exec_driver_sql("SELECT @@SESSION.transaction_read_only").scalar()

        assert getattr(getattr(outcome, "orig", None), "args", (None,))[0] == ER_CANT_EXECUTE_IN_READ_ONLY_TRANSACTION
        assert rows == 0
        assert read_only == 0
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS sharpit_mysql_probe")
        engine.dispose()


@NEEDS_MYSQL
def test_full_read_against_mysql_84() -> None:
    engine = _engine()
    try:
        app = FastAPI()
        handle = install(app, enabled="ON", show_banner=False, config_scan=False)
        if handle.context.capture.engine_registry is not None:
            handle.context.capture.engine_registry.add(engine)

        client = TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)
        response = client.post("/sharpit/api/mysql/read")
        assert response.status_code == 200
        report = response.json()
        assert report["status"] in ("READ", "PARTIAL")
        assert report["dataSourcesRead"] >= 1
        ds = report["dataSources"][0]
        assert ds["name"].startswith("mysql+pymysql://")  # EngineRegistry names an engine by its URL
        assert ds["capabilities"]["serverVersion"] is not None
        assert len(ds["sections"]) == 7
        assert client.get("/sharpit/api/mysql").json() == report
    finally:
        engine.dispose()
