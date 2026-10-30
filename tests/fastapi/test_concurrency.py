"""A slow first config scan must not hold up other panels, nor the host's event loop (Task P1 item 3)."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors import config as config_module

LOCAL = ("127.0.0.1", 50000)
PING = {"jsonrpc": "2.0", "id": 1, "method": "ping"}


def test_other_panels_are_not_serialised_behind_a_slow_config_scan(monkeypatch: pytest.MonkeyPatch):
    started, release = threading.Event(), threading.Event()

    def slow_scan(_roots: Any) -> list[Any]:
        started.set()
        release.wait(10)  # far longer than the other requests may take
        return []

    monkeypatch.setattr(config_module, "scan_packages", slow_scan)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:  # one event loop for every request
        config = threading.Thread(target=client.get, args=("/sharpit/api/config",))
        config.start()
        assert started.wait(5)
        results: dict[str, int] = {}

        def others() -> None:
            # async handlers (mcp, toggle) run on the loop; mcp-server is a sync handler in the threadpool
            results["mcp"] = client.post("/sharpit/api/mcp", json=PING).status_code
            results["toggle"] = client.post("/sharpit/api/mcp-server/toggle", json={"enabled": False}).status_code
            results["mcp-server"] = client.get("/sharpit/api/mcp-server").status_code

        other = threading.Thread(target=others)
        other.start()
        other.join(3)
        finished_while_scanning = not other.is_alive()
        release.set()
        other.join(10)
        config.join(10)
    assert finished_while_scanning, "a panel request waited for the config scan"
    assert results == {"mcp": 200, "toggle": 200, "mcp-server": 200}
