"""The README's first screen states facts the code must keep true."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402

README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_panel_count_matches_the_panels_the_console_lists():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    try:
        client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
        count = len(client.get("/sharpit/api/panels").json()["panels"])
    finally:
        handle.uninstall_capture()
    assert f"**What you get:** {count} panels." in README.read_text(encoding="utf-8")
