"""Connection pool endpoints (F7, spec §7.7, §13.2): the report, one pool's snapshot by name, and the MCP tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

LOCAL = ("127.0.0.1", 50000)
POOLS = "/sharpit/api/database-connection-pools/pools"


def _client(*engines: Any, **options: Any) -> TestClient:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, mcp_enabled="ON", engines=list(engines), **options)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def test_pools_and_snapshot_by_name(tmp_path: Path):
    client = _client(sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}", poolclass=sa.QueuePool))
    (pool,) = client.get(POOLS).json()["pools"]
    assert "/" in pool["poolName"]  # sqlite+pysqlite:///...: the snapshot route takes a path-shaped name
    resp = client.get(f"{POOLS}/{quote(pool['poolName'], safe='')}/snapshot")
    assert resp.status_code == 200 and tuple(resp.json()) == ("timestamp", "active", "idle", "total", "pending")


def test_snapshot_unknown_404(tmp_path: Path):
    client = _client(sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}", poolclass=sa.NullPool))
    assert client.get(f"{POOLS}/nope/snapshot").status_code == 404
    (pool,) = client.get(POOLS).json()["pools"]
    assert client.get(f"{POOLS}/{quote(pool['poolName'], safe='')}/snapshot").status_code == 404  # no statistics


def test_get_database_connection_pools_mcp(tmp_path: Path):
    client = _client(sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}", poolclass=sa.QueuePool))
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_database_connection_pools"}}
    result = client.post("/sharpit/api/mcp", json={**call, "params": {**call["params"], "arguments": {}}}).json()
    content = result["result"]["structuredContent"]
    assert (content["hikariPresent"], content["total"]) == (True, 1)
