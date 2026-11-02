"""``GET/POST /sharpit/api/postgresql`` and the PostgreSQL MCP/CLI tools (port of BootUI ``PostgresqlControllerTests``).

PostgreSQL engines are ``FakePgEngine``s placed in the context's registry after install, read through the real
``sqla.run_db_read(read_only=True)``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.engine.postgresql.fakes import FakePgEngine, FakeRegistry

import golden
from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import tools
from sharpit.engine.collectors.postgresql.service import OPERATION
from sharpit.engine.singleflight import SingleFlight

sa = pytest.importorskip("sqlalchemy")

LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/postgresql"
READ = "/sharpit/api/postgresql/read"


def _client(*engines: tuple[str, Any], **options: Any) -> tuple[TestClient, Any]:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    handle.context.capture.engine_registry = FakeRegistry(*engines)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False), handle.context


def test_get_returns_the_not_read_report_before_any_read() -> None:
    # ported: PostgresqlControllerTests.getReturnsTheNotReadReportBeforeAnyRead
    engine = FakePgEngine()
    client, _ = _client(("primary", engine))
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_READ"
    assert engine.connects == 0


def test_read_performs_the_read_and_returns_a_report() -> None:
    # ported: PostgresqlControllerTests.readPerformsTheReadAndReturnsAReport
    engine = FakePgEngine()
    client, _ = _client(("primary", engine))
    response = client.post(READ)
    assert response.status_code == 200
    assert response.json()["status"] == "READ"
    assert engine.connects == 1


def test_get_returns_the_last_read_report_after_a_read() -> None:
    # ported: PostgresqlControllerTests.getReturnsTheLastReadReportAfterARead
    client, _ = _client(("primary", FakePgEngine()))
    read = client.post(READ).json()
    assert client.get(URL).json() == read


def test_get_no_side_effects(no_side_effects: SideEffectGuard) -> None:
    # spec §6.4: a GET never opens a socket and never runs SQL, even with a real PostgreSQL engine registered
    engine = sa.create_engine("postgresql+psycopg://app:secret@localhost:5432/app")
    statements: list[str] = []
    sa.event.listen(engine, "before_cursor_execute", lambda *a: statements.append(a[2]))
    sa.event.listen(engine, "checkout", lambda *_a: statements.append("<checkout>"))
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    client, _ = _client(("primary", engine), state_dir=str(no_side_effects.state_dir))
    with client:
        client.get("/sharpit/api/panels")
        no_side_effects.block_network()
        no_side_effects.rebaseline()  # install() and the engine's dialect import are not the GET under test
        response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_READ"
    assert no_side_effects.violations == []
    assert statements == []


@pytest.mark.parametrize("options", [{"read_only": True}, {"panels": {"postgresql": {"read_only": True}}}])
def test_read_only_403(options: dict[str, Any]) -> None:
    engine = FakePgEngine()
    client, _ = _client(("primary", engine), **options)
    assert client.get(URL).status_code == 200
    assert client.post(READ).status_code == 403
    assert engine.connects == 0


def test_disabled_panel_is_403() -> None:
    # contract §5: a disabled panel answers the shared 403
    engine = FakePgEngine()
    client, _ = _client(("primary", engine), panels={"postgresql": {"enabled": False}})
    assert client.get(URL).status_code == 403
    assert client.post(READ).status_code == 403
    assert engine.connects == 0


def test_concurrent_read_409() -> None:
    client, ctx = _client(("primary", FakePgEngine()))
    release = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight).try_acquire("other")
    response = client.post(READ)
    assert release is not None
    release()
    assert response.status_code == 409
    assert response.json()["operation"] == OPERATION


def test_mcp_read_tool_only() -> None:
    by_name = {t.name: t for t in tools.TOOLS if t.panel == "postgresql"}
    assert sorted(by_name) == ["get_postgresql_report", "postgresql_read"]
    assert by_name["get_postgresql_report"].action is False
    assert by_name["postgresql_read"].action is True
    assert tools.COMMANDS["get_postgresql_report"] == "db postgres report"
    assert tools.COMMANDS["postgresql_read"] == "db postgres read"
    client, _ = _client(("primary", FakePgEngine()), mcp_enabled="ON")
    listed = client.post(
        "/sharpit/api/mcp",
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        headers={"content-type": "application/json"},
    ).json()
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert "get_postgresql_report" in names
    assert "postgresql_read" not in names


def test_cli_read_returns_a_summary_without_rows() -> None:
    # ported: McpScanSummaries.postgresql (BootUI 2.2.0)
    client, _ = _client(("primary", FakePgEngine()))
    response = client.post("/sharpit/api/cli/tools/postgresql_read", content=b"{}")
    assert response.status_code == 200
    body = response.json()
    summary = body.get("result", body)
    assert summary["reportTool"] == "get_postgresql_report"
    assert summary["status"] == "READ"
    assert list(summary["databases"][0]) == ["name", "status", "message", "truncated", "sections"]
    assert list(summary["databases"][0]["sections"][0]) == ["id", "status", "reason", "rowCount", "truncated"]
    assert isinstance(summary["diagnostics"], int)
    assert client.get(URL).json()["status"] == "READ"


def test_golden_parity() -> None:
    fixtures = golden.ROOT / "postgresql"
    if not any((fixtures / name).exists() for name in ("captured.json", "provisional.json")):
        pytest.skip("no G0a captured.json or provisional postgresql fixture yet (coordinator)")
    client, _ = _client(("primary", FakePgEngine()))
    golden.assert_parity("postgresql", "report", client.post(READ).json())
