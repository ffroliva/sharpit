"""A full ``POST /mysql/read`` on the fake engine: the collected sections and the truncation reach the report."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.engine.collectors.mysql.fakes import FakeMySqlConnection, FakeMySqlEngine, FakeRegistry

from fastapi import FastAPI
from sharpit import install

pytestmark = pytest.mark.needs_sqlalchemy
pytest.importorskip("sqlalchemy")

LOCAL = ("127.0.0.1", 50000)
READ = "/sharpit/api/mysql/read"
SESSION = {
    "id": 1,
    "user": "app",
    "host": "localhost",
    "db": "app",
    "command": "Sleep",
    "time": 0,
    "state": None,
    "info": None,
    "current_statement": None,
}


def _read(engine: Any, **options: Any) -> dict[str, Any]:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    handle.context.capture.engine_registry = FakeRegistry(("primary", engine))
    client = TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)
    return client.post(READ).json()


def test_full_read_reports_read_status() -> None:
    report = _read(FakeMySqlEngine())
    assert report["status"] == "READ"


def test_full_read_reports_seven_sections() -> None:
    report = _read(FakeMySqlEngine())
    assert len(report["dataSources"][0]["sections"]) == 7


def test_row_cap_truncation_reaches_report() -> None:
    conn = FakeMySqlConnection().with_rows("SESSIONS", SESSION, {**SESSION, "id": 2})
    report = _read(FakeMySqlEngine(conn), mysql_max_sessions=1)
    assert report["truncated"] is True


def test_row_cap_truncation_makes_read_partial() -> None:
    conn = FakeMySqlConnection().with_rows("SESSIONS", SESSION, {**SESSION, "id": 2})
    report = _read(FakeMySqlEngine(conn), mysql_max_sessions=1)
    assert report["status"] == "PARTIAL"
