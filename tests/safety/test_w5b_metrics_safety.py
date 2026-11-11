from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Gauge

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.metrics import prometheus

PANEL = "metrics"
GET_ROWS = ["/sharpit/api/metrics", "/sharpit/api/metrics/detail"]
WRITE_ROWS: list[tuple[str, str]] = []


@pytest.fixture
def private_registry(monkeypatch: pytest.MonkeyPatch) -> CollectorRegistry:
    registry = CollectorRegistry()
    monkeypatch.setattr(prometheus, "REGISTRY", registry)
    return registry


def test_metrics_reads_have_no_side_effects(
    no_side_effects: SideEffectGuard, private_registry: CollectorRegistry
) -> None:
    calls: list[int] = []
    Gauge("guarded", "", registry=private_registry).set_function(lambda: calls.append(1) or 1.0)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        no_side_effects.block_network()
        assert client.get(GET_ROWS[0]).json()["meters"][0]["name"] == "guarded"
        assert client.get(GET_ROWS[1], params={"name": "guarded"}).json()["totalSamples"] == 1
    assert len(calls) == 2  # the host collector really ran under the guard
    assert no_side_effects.violations == []


def test_metrics_has_no_write_routes() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.post(GET_ROWS[0]).status_code in {404, 405}


def test_metrics_gated_when_panel_disabled(private_registry: CollectorRegistry) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, panels={"metrics": {"enabled": False}})
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.get(GET_ROWS[0]).status_code == 403
