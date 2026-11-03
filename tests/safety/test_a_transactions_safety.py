from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install

LOCAL = ("127.0.0.1", 50000)


def test_transaction_get_and_stream_do_not_trigger_side_effects(no_side_effects: SideEffectGuard) -> None:
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
            report = client.get("/sharpit/api/transactions")
            stream = client.get("/sharpit/api/transactions/stream")
        assert report.status_code == 200, "the transaction GET route must serve a cached report"
        assert stream.status_code == 200, "the transaction stream must not open external resources"
        assert no_side_effects.violations == [], "transaction GET and stream must not open sockets"
    finally:
        handle.uninstall_capture()


PANEL = "transactions"
GET_ROWS = ["/sharpit/api/transactions", "/sharpit/api/transactions/stream"]
WRITE_ROWS = [
    ("POST", "/sharpit/api/transactions/clear"),
    ("POST", "/sharpit/api/transactions/recording"),
]
