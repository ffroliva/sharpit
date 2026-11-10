"""A secret in a runtime journal event never reaches JSON, MCP or CLI output (W5a scenario 3).

The canary is ``secrets.token_hex(16)``, so only masking by name or position can hide it. It is offered to the live
journal the way a capture source will: a ``password=`` message, an ``Authorization`` header and a ``password`` field.
Every GET route on the mount, every MCP tool and every CLI command (but the OSV scan, which calls out) must not show it.

No surface renders journal events yet (``records()`` has no route), so the control that proves the canary is there to
leak is ``records()`` itself: hidden under the defaults, shown with masking off.
"""

from __future__ import annotations

import contextlib
import json
import secrets
from collections.abc import Iterator
from typing import Any, NamedTuple

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

import surface
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.fastapi.adapter import SharpitMount

MASKING_OFF: dict[str, Any] = {"expose_values": "FULL", "mask_secrets": False}
TOKEN = "test-token"
PARAM_SAMPLES = {"file": "app.js", "id": "0123456789abcdef", "name": "nope", "rule_id": "RAPI-MAP-001"}
PARAM_SAMPLES |= {"tool": "get_overview"}
NETWORK = ("/vulnerabilities/scan", "vulnerabilities_scan")  # the OSV scan calls out
DESTRUCTIVE = ("/clear", "clear_")  # run last: they empty the stores the other calls read


class World(NamedTuple):
    client: TestClient
    app: FastAPI
    journal: RuntimeJournal


@pytest.fixture(scope="module")
def canary() -> str:
    return secrets.token_hex(16)


def _event(canary: str) -> dict[str, object]:
    return {
        "source": "http",
        "message": f"login password={canary}",
        "headers": {"Authorization": f"Bearer {canary}"},
        "password": canary,
    }


@contextlib.contextmanager
def _world(canary: str, state_dir: str, *, masking_off: bool) -> Iterator[World]:
    app = FastAPI()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        mcp_enabled="ON",
        cli_enabled=True,
        stream_max_seconds=0.05,
        authentication_token=TOKEN,
        state_dir=state_dir,
        **(MASKING_OFF if masking_off else {}),
    )
    try:
        with TestClient(
            app, base_url="http://localhost", client=("127.0.0.1", 50000), headers={"Authorization": f"Bearer {TOKEN}"}
        ) as client:
            journal = handle.context.capture.journal
            assert journal is not None, "the runtime journal is on by default"
            assert journal.offer(_event(canary)) is True
            yield World(client, app, journal)
    finally:
        handle.uninstall_capture()


@pytest.fixture(scope="module")
def masked(canary: str, tmp_path_factory: pytest.TempPathFactory) -> Iterator[World]:
    with _world(canary, str(tmp_path_factory.mktemp("state")), masking_off=False) as world:
        yield world


def _get_routes(app: FastAPI) -> list[str]:
    mount = next(r for r in app.router.routes if isinstance(r, SharpitMount))
    return sorted(
        "/sharpit" + r.path_format.format(**{p: PARAM_SAMPLES[p] for p in r.param_convertors})
        for r in mount.routes
        if isinstance(r, Route) and "GET" in (r.methods or set()) and not r.path_format.endswith("/stream")
    )


def _mcp(world: World) -> dict[str, str]:
    def call(name: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": {}}}

    return {
        f"MCP {name}": world.client.post("/sharpit/api/mcp", json=call(name)).text
        for name in surface.expected_mcp_tool_names()
    }


def _cli(world: World) -> dict[str, str]:
    names = sorted(
        (n for n in surface.expected_cli_commands() if n not in NETWORK), key=lambda n: n.startswith(DESTRUCTIVE)
    )
    return {f"CLI {n}": world.client.post(f"/sharpit/api/cli/tools/{n}", json={}).text for n in names}


def _json(world: World) -> dict[str, str]:
    return {f"GET {path}": world.client.get(path).text for path in _get_routes(world.app)}


def test_journal_records_hide_the_canary_and_show_it_with_masking_off(
    canary: str, masked: World, tmp_path_factory: pytest.TempPathFactory
) -> None:
    assert canary not in json.dumps(masked.journal.records("http"))
    with _world(canary, str(tmp_path_factory.mktemp("state")), masking_off=True) as exposed:
        assert canary in json.dumps(exposed.journal.records("http"))


@pytest.mark.parametrize("surface_name", ["json", "mcp", "cli"])
def test_journal_canary_never_reaches(surface_name: str, masked: World, canary: str) -> None:
    texts = {"json": _json, "mcp": _mcp, "cli": _cli}[surface_name](masked)
    assert texts, f"{surface_name}: no output was checked"
    leaks = sorted(where for where, text in texts.items() if canary in text)
    assert leaks == [], f"{surface_name} shows the journal canary"
