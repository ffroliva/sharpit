"""The ``mysql`` panel routes and contract parity."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.engine.collectors.mysql.fakes import FakeMySqlEngine, FakeRegistry

import golden
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla, tools
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.mysql.service import mysql_report
from sharpit.engine.context import SharpitContext
from sharpit.engine.sqla import readonly
from sharpit.settings import load_settings

pytestmark = pytest.mark.needs_sqlalchemy
pytest.importorskip("sqlalchemy")

LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/mysql"
READ = "/sharpit/api/mysql/read"


def _client(*engines: tuple[str, Any], **options: Any) -> tuple[TestClient, Any]:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    if engines:
        handle.context.capture.engine_registry = FakeRegistry(*engines)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False), handle.context


class _Introspector:
    def app_info(self) -> Any:
        return None

    def routes(self) -> list[Any]:
        return []

    def providers(self) -> list[Any]:
        return []


ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())


def _ctx() -> SharpitContext:
    return SharpitContext(load_settings({"config_scan": False}, {}), ACTIVATION, _Introspector())


def test_report_golden_parity() -> None:
    payload = mysql_report(_ctx())
    golden.assert_parity("mysql", "report", payload)


def test_mysql_read_uses_verified_read_only_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: MySqlValuesTests (verified read-only path)
    bounded_calls = 0
    bounded_ro_calls = 0

    orig_bounded = readonly.bounded
    orig_bounded_ro = readonly.bounded_read_only

    def spy_bounded(conn: Any, fn: Any, stmt: Any = None) -> Any:
        nonlocal bounded_calls
        bounded_calls += 1
        return orig_bounded(conn, fn, stmt)

    def spy_bounded_ro(conn: Any, fn: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal bounded_ro_calls
        bounded_ro_calls += 1
        return orig_bounded_ro(conn, fn, *args, **kwargs)

    monkeypatch.setattr(readonly, "bounded", spy_bounded)
    monkeypatch.setattr(readonly, "bounded_read_only", spy_bounded_ro)

    client, _ = _client(("primary", FakeMySqlEngine()))
    response = client.post(READ)
    assert response.status_code == 200
    assert bounded_calls == 0
    assert bounded_ro_calls == 1


def test_autocommit_engine_is_unavailable() -> None:
    # ported: MySqlValuesTests (autocommit engine refused)
    engine = FakeMySqlEngine()
    engine.options = {"isolation_level": "AUTOCOMMIT"}
    client, _ = _client(("primary", engine))
    response = client.post(READ)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ERROR"
    assert any(sqla.READ_ONLY_REFUSED in d.get("message", "") for d in body.get("diagnostics", []))


def test_unknown_driver_unavailable() -> None:
    # ported: MySqlDataSourceDetectionTests.nonMySqlSkipped
    class FakeSqliteEngine:
        dialect = type("Dialect", (), {"name": "sqlite"})()
        options: dict[str, Any] = {}

    client, _ = _client(("primary", FakeSqliteEngine()))
    response = client.post(READ)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DISABLED"
    assert body["message"] == (
        "No MySQL datasource was found. This panel reads MySQL's own statistics views, "
        "so it has nothing to report for other database products."
    )
    assert any(
        "Skipped: this datasource is SQLite, not MySQL." in d.get("message", "") for d in body.get("diagnostics", [])
    )


def test_read_only_blocks_read() -> None:
    # contract §6: read-only blocks POST /read with 403
    engine = FakeMySqlEngine()
    client, _ = _client(("primary", engine), read_only=True)
    assert client.get(URL).status_code == 200
    assert client.post(READ).status_code == 403
    assert engine.connects == 0


def test_inactive_mysql_paths_404() -> None:
    # spec §7.6: inactive sharpit paths answer 404
    active_client, _ = _client(("primary", FakeMySqlEngine()), enabled="ON")
    assert active_client.get(URL).status_code == 200
    inactive_client, _ = _client(("primary", FakeMySqlEngine()), enabled="OFF")
    assert inactive_client.get(URL).status_code == 404
    assert inactive_client.post(READ).status_code == 404


def test_mcp_tools_list_has_only_get() -> None:
    # BootUI McpToolCatalog: get_mysql_report is read, mysql_read is CLI-only action
    by_name = {t.name: t for t in tools.TOOLS if t.panel == "mysql"}
    assert sorted(by_name) == ["get_mysql_report", "mysql_read"]
    assert by_name["get_mysql_report"].action is False
    assert by_name["mysql_read"].action is True
    assert tools.COMMANDS["get_mysql_report"] == "db mysql report"
    assert tools.COMMANDS["mysql_read"] == "db mysql read"
    client, _ = _client(("primary", FakeMySqlEngine()), mcp_enabled="ON")
    listed = client.post(
        "/sharpit/api/mcp",
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        headers={"content-type": "application/json"},
    ).json()
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert "get_mysql_report" in names
    assert "mysql_read" not in names
