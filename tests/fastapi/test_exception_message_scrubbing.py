"""Exception and cause messages on every projection: REST, request profile, MCP and CLI (port of BootUI 2.5.0).

BootUI's ``ExceptionsService.displayMessage`` scrubs the user-input literals of framework messages outside ``FULL``
(``MessageExposure.scrubBindingLiterals``); sharpit reads the same rule wherever it shows a stored message.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.adapter import SharpitHandle

LOCAL = ("127.0.0.1", 50000)
SENTINEL = "ordinary-sentinel-91"
MAIN = f"{SENTINEL}-main"
CAUSE = f"{SENTINEL}-cause"
SHOWN = "invalid literal for int() with base 10: '{}'"
_HANDLES: list[SharpitHandle] = []
log = logging.getLogger("host.app")


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _app(**options: Any) -> FastAPI:
    app = FastAPI()

    @app.get("/bad")
    def bad() -> None:  # pyright: ignore[reportUnusedFunction]
        try:
            float(CAUSE)
        except ValueError as cause:
            raise ValueError(SHOWN.format(MAIN)) from cause

    settings = {"enabled": "ON", "show_banner": False, "stream_max_seconds": 0.05, "cli_enabled": True, **options}
    _HANDLES.append(install(app, **{"mcp_enabled": "ON", **settings}))
    return app


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)


def _rpc(client: TestClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return client.post("/sharpit/api/mcp", json=call).json()["result"]["structuredContent"]


def _projections(client: TestClient) -> dict[str, str]:
    """Every place the failing request's messages are shown, as one JSON text each."""
    assert client.get("/bad").status_code == 500
    listed = client.get("/sharpit/api/exceptions").json()
    gid = listed["groups"][0]["id"]
    entry = next(e for e in client.get("/sharpit/api/activity").json()["entries"] if e["type"] == "REQUEST")
    return {
        "rest-list": json.dumps(listed),
        "rest-detail": json.dumps(client.get(f"/sharpit/api/exceptions/{gid}").json()),
        "request-profile": json.dumps(client.get(f"/sharpit/api/activity/request/{entry['id']}").json()),
        "mcp-list": json.dumps(_rpc(client, "get_exceptions", {})),
        "mcp-detail": json.dumps(_rpc(client, "get_exception_detail", {"id": gid})),
        "mcp-profile": json.dumps(_rpc(client, "get_request_profile", {"id": entry["id"]})),
        "cli-list": json.dumps(client.post("/sharpit/api/cli/tools/get_exceptions", json={}).json()),
        "cli-detail": json.dumps(client.post("/sharpit/api/cli/tools/get_exception_detail", json={"id": gid}).json()),
    }


def test_exception_messages_are_scrubbed_on_rest_projections() -> None:
    client = _client(_app())

    shown = _projections(client)

    for surface in ("rest-list", "rest-detail", "request-profile"):
        assert SENTINEL not in shown[surface], surface
        assert SHOWN.format("******") in shown[surface], surface


def test_exception_messages_are_scrubbed_on_mcp_and_cli() -> None:
    client = _client(_app())

    shown = _projections(client)

    for surface in ("mcp-list", "mcp-detail", "mcp-profile", "cli-list", "cli-detail"):
        assert SENTINEL not in shown[surface], surface
        assert SHOWN.format("******") in shown[surface], surface


def test_exception_messages_are_scrubbed_with_secret_masking_off() -> None:
    client = _client(_app(mask_secrets=False))

    shown = _projections(client)

    assert all(SENTINEL not in text for text in shown.values())


def test_exception_messages_are_verbatim_in_full() -> None:
    client = _client(_app(expose_values="FULL"))

    shown = _projections(client)

    for surface, text in shown.items():
        assert MAIN in text, surface
    assert CAUSE in shown["rest-detail"]


def test_exception_messages_are_omitted_in_metadata_only() -> None:
    client = _client(_app(expose_values="METADATA_ONLY"))

    shown = _projections(client)

    assert all(SENTINEL not in text for text in shown.values())
    assert json.loads(shown["rest-list"])["groups"][0]["message"] is None


def test_exception_message_projection_has_no_side_effects(no_side_effects: SideEffectGuard) -> None:
    app = create_app(show_banner=False, state_dir=str(no_side_effects.state_dir), mcp_enabled="ON")
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(app) as client:
        no_side_effects.block_network()
        try:
            int(SENTINEL)
        except ValueError:
            log.exception("seen by the agent")
        listed = _rpc(client, "get_exceptions", {})
        gid = listed["groups"][0]["id"]
        detail = _rpc(client, "get_exception_detail", {"id": gid})
        rest = client.get(f"/sharpit/api/exceptions/{gid}").json()
    app.state.sharpit.uninstall_capture()
    assert SENTINEL not in json.dumps([listed, detail, rest])
    assert no_side_effects.violations == []
