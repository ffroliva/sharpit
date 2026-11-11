"""Safety rows for the profile-diff panel (spec §4, §6.3, W5b Task P)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

PANEL = "profile-diff"
GET_ROWS = ["/sharpit/api/profile-diff"]
WRITE_ROWS: list[tuple[str, str]] = []

LOCAL = ("127.0.0.1", 50000)
PATHS = ("/sharpit/api/profile-diff",)


def _client(**options: object) -> TestClient:
    app = FastAPI()
    install(app, show_banner=False, config_scan=False, **{"enabled": "ON", **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def test_profile_diff_has_no_write_routes() -> None:
    assert WRITE_ROWS == []


@pytest.mark.parametrize("path", PATHS)
def test_cross_site_request_is_refused(path: str) -> None:
    response = _client().get(path, headers={"Origin": "http://evil.example"})
    assert response.status_code == 403
    assert response.json() == {"error": "sharpit rejected a cross-site request."}


@pytest.mark.parametrize("path", PATHS)
def test_inactive_install_answers_404(path: str) -> None:
    assert _client(enabled="OFF").get(path).status_code == 404
