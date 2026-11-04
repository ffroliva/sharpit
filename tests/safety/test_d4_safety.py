"""Lane D4 safety rows: the 2.2.0 vulnerabilities, mcp-server and rest-api reads stay side-effect free.

Base panels only: no ``PANEL``, no new route (their GET routes are rows in tests/test_safety_matrix.py::ROWS).
``get_vulnerabilities_report`` takes optional ``query``/``limit`` only, so it needs no ``TOOL_ARGS``.
"""

from __future__ import annotations

from typing import Any

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import SideEffectGuard

GETS = ["/sharpit/api/vulnerabilities", "/sharpit/api/mcp-server", "/sharpit/api/rest-api"]


def _client(state_dir: Any) -> TestClient:
    app = create_app(show_banner=False, state_dir=str(state_dir), mcp_enabled="ON")
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def test_d4_drift_reads_have_no_side_effects(no_side_effects: SideEffectGuard):
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(no_side_effects.state_dir) as client:
        client.get("/owners")
        no_side_effects.block_network()
        statuses = {path: client.get(path).status_code for path in GETS}
        arguments = {"query": "a", "limit": 3}
        call = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_vulnerabilities_report", "arguments": arguments},
        }
        result = client.post("/sharpit/api/mcp", json=call).json().get("result", {})
    assert statuses == dict.fromkeys(GETS, 200)
    assert result.get("isError") is False, "query and limit are accepted on get_vulnerabilities_report"
    assert no_side_effects.violations == []
