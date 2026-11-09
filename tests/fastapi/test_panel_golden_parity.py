"""Live 2.2.0 parity of the panels whose only check was the 1.17.0 conformance test, or none."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from golden import assert_parity

API = "/sharpit/api"


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    state_dir: Path = tmp_path_factory.mktemp("state")
    app = create_app(show_banner=False, state_dir=str(state_dir))
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def _get(client: TestClient, path: str) -> dict[str, Any]:
    response = client.get(f"{API}/{path}")
    assert response.status_code == 200
    return response.json()


def test_beans_golden_parity(client: TestClient):
    assert_parity("beans", "captured", _get(client, "beans"))


def test_cli_golden_parity(client: TestClient):
    assert_parity("cli", "captured", _get(client, "cli"))


def test_config_golden_parity(client: TestClient):
    assert_parity("config", "captured", _get(client, "config"))


def test_dismissed_findings_golden_parity(client: TestClient):
    assert_parity("dismissed-findings", "captured", _get(client, "dismissed-findings"))


def test_dismissed_rules_golden_parity(client: TestClient):
    assert_parity("dismissed-rules", "captured", _get(client, "dismissed-rules"))


def test_http_probe_golden_parity(client: TestClient):
    response = client.post(f"{API}/http-probe", json={"method": "GET", "path": "/openapi.json"})
    assert response.status_code == 200
    assert response.json()["status"] == 200
    assert_parity("http-probe", "captured", response.json())


def test_loggers_golden_parity(client: TestClient):
    assert_parity("loggers", "captured", _get(client, "loggers"))


def test_mappings_flat_golden_parity(client: TestClient):
    assert_parity("mappings", "flat", _get(client, "mappings/flat"))


def test_panels_golden_parity(client: TestClient):
    assert_parity("panels", "captured", _get(client, "panels"))
