"""Lane A-mysql safety rows (spec §6.1 item 3, §6.4): the read is POST-only, read-only and never commits."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from tests.engine.collectors.mysql.fakes import FakeMySqlEngine, FakeRegistry

from fastapi import FastAPI
from sharpit import install

PANEL = "mysql"
GET_ROWS = ["/sharpit/api/mysql"]
WRITE_ROWS = [("POST", "/sharpit/api/mysql/read")]
CLI_ACTIONS = ["mysql_read"]

LOCAL = ("127.0.0.1", 50000)


def _client(*engines: tuple[str, Any], **options: Any) -> tuple[TestClient, Any]:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    if engines:
        handle.context.capture.engine_registry = FakeRegistry(*engines)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False), handle.context


def test_mysql_get_no_side_effects() -> None:
    engine = FakeMySqlEngine()
    client, _ctx = _client(("primary", engine))
    response = client.get("/sharpit/api/mysql")
    assert response.status_code == 200
    assert engine.conn.sql == []
