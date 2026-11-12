"""``GET /sql-trace/insights`` and the ``get_sql_trace_insights`` MCP tool (lane A-sqltrace-insights, Task 2)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402
from tests.golden import assert_parity  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

API = "/sharpit/api/sql-trace/insights"
_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _client(**options: Any) -> TestClient:
    engine = sa.create_engine("sqlite://")
    app = FastAPI()

    @app.get("/orders/{order_id}")
    def order(order_id: int) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        with engine.connect() as conn:
            conn.execute(sa.text("select 1"))
            return {"id": conn.execute(sa.text(f"select {order_id}")).scalar()}

    settings = {"enabled": "ON", "show_banner": False, "mcp_enabled": "ON", "sql_trace_sqlite3_enabled": False}
    _HANDLES.append(install(app, **{**settings, **options}))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    for order_id in (1, 2, 3):
        client.get(f"/orders/{order_id}")
    with engine.connect() as conn:
        conn.execute(sa.text("select 'background'"))  # outside any request: the unattributed bucket
    return client


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/sharpit/api/mcp", json=body).json()


def test_insights_golden_parity():
    response = _client().get(API)
    assert response.status_code == 200
    assert_parity("sql-trace", "insights", response.json())


def test_insights_attributes_requests_to_masked_routes():
    response = _client().get(API)
    assert response.status_code == 200
    routes = response.json()["attribution"]["routes"]
    assert [(r["id"], r["requests"], r["executions"]) for r in routes] == [("GET /orders/{value}", 3, 6)]


def test_insights_unavailable_when_tracing_off():
    response = _client(sql_trace_enabled=False).get(API)
    assert response.status_code == 200
    assert response.json()["unavailableReason"] == "SQL tracing is disabled via SHARPIT_SQL_TRACE_ENABLED=false"


def test_insights_respects_panel_disabled():
    response = _client(panels={"sql-trace": {"enabled": False}}).get(API)
    assert response.status_code == 403


def test_mcp_tools_list_has_only_get():
    client = _client()
    names = [t["name"] for t in _rpc(client, "tools/list")["result"]["tools"]]
    assert [n for n in names if "sql_trace_insights" in n] == ["get_sql_trace_insights"]
    result = _rpc(client, "tools/call", {"name": "get_sql_trace_insights", "arguments": {}})["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["window"]["retainedStatements"] == 7
