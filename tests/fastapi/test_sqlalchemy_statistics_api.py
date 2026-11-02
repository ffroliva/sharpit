"""``sqlalchemy-statistics`` endpoints and MCP tool (lane A-sqlalchemy-statistics, Task 4).

No golden parity test: tiny-ledger has no Hibernate statistics, so no ``captured.json`` / ``provisional.json`` exists
(``checklist.md`` item 1).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.collectors.sqlastats import REPORT_KEYS, STATISTICS_KEYS  # noqa: E402
from sharpit.fastapi.adapter import SharpitHandle  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

API = "/sharpit/api/sqlalchemy-statistics"
_HANDLES: list[SharpitHandle] = []


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _app(**options: Any) -> TestClient:
    engine = sa.create_engine("sqlite://")
    app = FastAPI()

    @app.get("/pets")
    def pets() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        with engine.connect() as conn:
            for i in range(6):
                conn.execute(sa.text("select :i"), {"i": i})
        return {"n": 6}

    handle = install(app, enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False, **options)
    _HANDLES.append(handle)
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), raise_server_exceptions=False)


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/sharpit/api/mcp", json=body).json()


def _get(client: TestClient) -> dict[str, Any]:
    response = client.get(API)
    assert response.status_code == 200
    return response.json()


def test_get_delegates():
    # ported: HibernateStatisticsControllerTests.statisticsDelegatesToEngineServiceWhenAvailable
    client = _app()
    client.get("/pets")
    body = _get(client)
    assert tuple(body) == REPORT_KEYS
    assert body["available"] is True
    assert set(body["statistics"]) == set(STATISTICS_KEYS)
    assert body["statistics"]["queryExecutionCount"] == 6


def test_n_plus_one_route_from_a_real_request():
    client = _app()
    client.get("/pets")
    entries = _get(client)["statistics"]["nPlusOne"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["method"] == "GET"
    assert entry["route"].endswith(".pets")
    assert entry["executionsPerRequest"] == 6


def test_unavailable_mirrors_sql_trace_reason():
    # ported: HibernateStatisticsControllerTests.statisticsReportsUnavailableWhenStatisticsDisabled
    body = _get(_app(sql_trace_enabled=False))
    assert body["available"] is False
    assert body["unavailableReason"] == sqla.TRACING_DISABLED
    assert set(body["statistics"]) == set(STATISTICS_KEYS)


def test_enable_returns_report_unchanged():
    # ported: HibernateStatisticsControllerTests.enableDelegatesToEngineService
    client = _app()
    client.get("/pets")
    before = _get(client)
    response = client.post(f"{API}/enable")
    assert response.status_code == 200
    assert response.json() == before


def test_enable_read_only_403():
    client = _app(read_only=True)
    assert client.post(f"{API}/enable").status_code == 403


def test_mcp_read_tool_only():
    client = _app(mcp_enabled="ON")
    client.get("/pets")
    names = [t["name"] for t in _rpc(client, "tools/list")["result"]["tools"]]
    assert "get_sqlalchemy_statistics" in names
    assert "enable_sqlalchemy_statistics" not in names
    result = _rpc(client, "tools/call", {"name": "get_sqlalchemy_statistics", "arguments": {}})["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["statistics"]["queryExecutionCount"] == 6
