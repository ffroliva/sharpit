from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install

LOCAL = ("127.0.0.1", 50000)


def test_security_logs_get_no_side_effects(no_side_effects: SideEffectGuard) -> None:
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(no_side_effects.state_dir),
        stream_max_seconds=0.01,
    )
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop opens a self-pipe socket pair.
    try:
        with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
            no_side_effects.block_network()
            report = client.get("/sharpit/api/security-logs")
            stream = client.get("/sharpit/api/security-logs/stream")
        assert report.status_code == 200, "the security-logs GET route serves the buffered report"
        assert stream.status_code == 200, "the security-logs stream serves change ticks"
        assert no_side_effects.violations == [], "security-logs GET and stream must have no side effects"
    finally:
        handle.uninstall_capture()


def test_inactive_security_logs_paths_404() -> None:
    app = FastAPI()
    install(app, enabled="OFF", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)
    statuses = [client.get(path).status_code for path in GET_ROWS]
    assert statuses == [404] * len(GET_ROWS), "an inactive mount must answer 404 on every security-logs path"


PANEL = "security-logs"
GET_ROWS = ["/sharpit/api/security-logs", "/sharpit/api/security-logs/stream"]
WRITE_ROWS: list[tuple[str, str]] = []
