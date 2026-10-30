"""Smoke test for an installed sharpit wheel: serve the sample app and fetch the overview.

Run from the repository root with PYTHONPATH=. and the venv python, after installing the wheel plus fastapi, pydantic-settings,
uvicorn and httpx. Fails if sharpit was imported from the source tree instead of the installed wheel.
"""

from __future__ import annotations

import sys
from pathlib import Path

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

import sharpit

location = Path(sharpit.__file__).resolve()
assert "site-packages" in location.parts, f"sharpit came from {location}, not an installed wheel"
assert (location.parent / "py.typed").is_file(), "py.typed missing from the wheel"
assert (location.parent / "ui" / "static" / "index.html").is_file(), "ui/static/index.html missing from the wheel"

with TestClient(
    create_app(enabled="ON", show_banner=False), base_url="http://localhost", client=("127.0.0.1", 50000)
) as client:
    overview = client.get("/sharpit/api/overview")
    shell = client.get("/sharpit/")
print(f"sharpit {sharpit.__version__} from {location.parent}")
print(f"GET /sharpit/api/overview -> {overview.status_code}")
print(f"GET /sharpit/ -> {shell.status_code}")
sys.exit(0 if overview.status_code == 200 and shell.status_code == 200 else 1)
