"""``sql-trace/insights`` reads have no side effects (lane A-sqltrace-insights; AGENTS.md safety model 4)."""

from __future__ import annotations

import pytest

try:  # no module-level skip: the shared safety matrix imports this file for its rows
    import sqlalchemy as sa
except ImportError:
    sa = None

from examples.fastapi_sample.app import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from conftest import SideEffectGuard  # noqa: E402

PANEL = "sql-trace"
GET_ROWS = ["/sharpit/api/sql-trace/insights"]
WRITE_ROWS: list[tuple[str, str]] = []


@pytest.mark.needs_sqlalchemy
def test_insights_get_no_side_effects(no_side_effects: SideEffectGuard):
    engine = sa.create_engine("sqlite://")
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON", engines=[engine])
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        with engine.connect() as conn:
            conn.execute(sa.text("select 1"))
        no_side_effects.block_network()
        response = client.get("/sharpit/api/sql-trace/insights")
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_sql_trace_insights"}}
        tool = client.post("/sharpit/api/mcp", json=call)
    assert response.status_code == 200
    assert response.json()["window"]["retainedStatements"] >= 1
    assert tool.json()["result"]["isError"] is False
    assert no_side_effects.violations == []
