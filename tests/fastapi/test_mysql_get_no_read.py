"""``GET /mysql`` never reads, even with SQLAlchemy imported (the safety row passes early without it)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.engine.collectors.mysql.fakes import FakeMySqlEngine, FakeRegistry

from fastapi import FastAPI
from sharpit import install

pytestmark = pytest.mark.needs_sqlalchemy
pytest.importorskip("sqlalchemy")


def test_mysql_get_runs_no_sql_with_sqlalchemy_imported() -> None:
    engine = FakeMySqlEngine()
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    handle.context.capture.engine_registry = FakeRegistry(("primary", engine))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    client.get("/sharpit/api/mysql")
    assert engine.conn.sql == []
