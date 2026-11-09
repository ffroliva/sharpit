"""A real in-process scan feeds the ORM, runtime and vendor rules (coordinator ruling for A-dbadv-2, wiring)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")
orm = pytest.importorskip("sqlalchemy.orm")
QueuePool = pytest.importorskip("sqlalchemy.pool").QueuePool

SCAN = "/sharpit/api/database-advisor/scan"


def test_live_scan_runs_orm_runtime_and_vendor_rules() -> None:
    engine = sa.create_engine(
        "sqlite://", poolclass=QueuePool, pool_size=1, max_overflow=0, connect_args={"check_same_thread": False}
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    reg = orm.registry()
    user = type("User", (), {})  # the registry holds mapped classes weakly: keep a reference for the whole test
    columns = (sa.Column("id", sa.Integer, primary_key=True), sa.Column("email", sa.String(50)))
    reg.map_imperatively(user, sa.Table("users", reg.metadata, *columns))
    reg.configure()
    app = FastAPI()
    options: dict[str, Any] = {"enabled": "ON", "show_banner": False, "config_scan": False}
    handle = install(app, **options, models=(reg,), sql_trace_capture_parameters=True)
    handle.context.capture.engine_registry.add(engine)  # the real registry: SQL Trace routes by it
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT * FROM users WHERE id = 1").fetchall()
        conn.exec_driver_sql("SELECT * FROM users WHERE id = 2").fetchall()
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))

    report: dict[str, Any] = client.post(SCAN).json()
    fired = [r["id"] for r in report["results"]]
    reasons = {d["source"]: d["message"] for d in report["diagnostics"]}

    assert user.__name__ == "User"
    assert "DB-HIB-006" in fired
    assert "DB-RUNTIME-001" in fired
    assert "DB-PG-001" in reasons
    assert "not read" not in reasons["DB-PG-001"]
