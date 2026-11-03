"""Safety rows for the architecture advisor panel (spec §4, §5.5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

PANEL = "architecture"
GET_ROWS = [
    "/sharpit/api/architecture",
    "/sharpit/api/architecture/rules/{rule_id}/violations",
]
WRITE_ROWS = [
    ("POST", "/sharpit/api/architecture/scan"),
]
PATH_PARAMS = {
    "rule_id": "ARCH-PKG-001",
}
CLI_ACTIONS = ("architecture_scan",)

LOCAL = ("127.0.0.1", 50000)
PATHS = (
    "/sharpit/api/architecture",
    "/sharpit/api/architecture/rules/ARCH-PKG-001/violations",
)


def _client(**options: object) -> TestClient:
    app = FastAPI()
    install(app, show_banner=False, config_scan=False, **{"enabled": "ON", **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL)


@pytest.mark.parametrize("path", PATHS)
def test_cross_site_request_is_refused(path: str) -> None:
    # derived: guard chain runs on every request, including architecture routes
    response = _client().get(path, headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert response.json() == {"error": "sharpit rejected a cross-site request."}


@pytest.mark.parametrize("path", PATHS)
def test_inactive_install_answers_404(path: str) -> None:
    # derived: fails closed, an inactive mount answers 404 for every path
    assert _client(enabled="OFF").get(path).status_code == 404
