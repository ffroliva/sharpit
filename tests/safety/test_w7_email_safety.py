"""Email reads have no side effects, and DELETE /email is an action the read-only gates refuse."""

from __future__ import annotations

from pathlib import Path

from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import SideEffectGuard

PANEL = "email"
GET_ROWS = [
    "/sharpit/api/email",
    "/sharpit/api/email/{id}",
    "/sharpit/api/email/{id}/eml",
]
WRITE_ROWS = [("DELETE", "/sharpit/api/email")]
PATH_PARAMS = {"id": "email-1"}
TOOL_ARGS = {}
TOOL_SEEDS = {}
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_every_email_row_is_swept_over_a_captured_message(no_side_effects: SideEffectGuard):
    # finding W7-E r2 #7: the shared sweep answers its email-1 rows with 404s (nothing captured); here they are seeded
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        client.get("/owners")
        recorder = getattr(app.state.sharpit.context.capture, "mail", None)
        assert recorder is not None
        recorder.record("app@example.test", ["b@example.test"], "Subject: seeded\n\nbody\n")  # no socket
        no_side_effects.block_network()
        no_side_effects.watch_sources(EXAMPLES)
        for row in GET_ROWS:
            response = client.get(row.format(**PATH_PARAMS))
            assert response.status_code == 200, row
    assert no_side_effects.violations == []
