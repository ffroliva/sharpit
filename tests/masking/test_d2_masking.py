"""Lane D2 masking rows: a secret in a path no route matched never reaches a route label (MASKED_PATH)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import tools

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJkMiJ9.c2lnbmF0dXJlLWJ5dGVz"


def test_unmatched_path_secret_never_reaches_route_labels(tmp_state_dir: Path):
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, state_dir=str(tmp_state_dir))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    client.get(f"/reset/{JWT}")
    routes = client.get("/sharpit/api/http-exchanges/routes").text
    exchanges = client.get("/sharpit/api/http-exchanges").json()["exchanges"]
    tool = tools.summarize_http_routes(handle.context.capture.exchanges)
    assert JWT not in routes
    assert JWT not in str(tool)
    assert [(e["route"], e["routeSource"]) for e in exchanges] == [("/reset/{value}", "MASKED_PATH")]
