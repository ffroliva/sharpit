from __future__ import annotations

import asyncio

import httpx
import pytest

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.panels import Panel
from sharpit.engine.panels04 import IMPLEMENTED as ALL_IMPLEMENTED

LOCAL = ("127.0.0.1", 50000)
ALL_PANEL_IDS = {
    "data",
    "transactions",
    "postgresql",
    "mysql",
    "traces",
    "security",
    "security-logs",
    "database-advisor",
    "architecture",
    "sqlalchemy-statistics",
    "fastapi-security",
    "fastapi",
    "metrics",
    "startup",
    "profile-diff",
    "scheduled",
}
EXPECTED_IDS = {panel_id for panel_id, implemented in ALL_IMPLEMENTED.items() if not implemented}
PANEL_IDS = EXPECTED_IDS  # whichever 0.4 panels are still unimplemented: flip-safe


@pytest.fixture(scope="module")
def asgi_loop():
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


def test_panel_implemented_defaults_true() -> None:
    panel = Panel("legacy", "Legacy", False, "/legacy")

    assert panel.implemented is True


def test_unimplemented_panel_gets_have_no_side_effects(no_side_effects: SideEffectGuard, asgi_loop) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))

    async def check() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            panels_response = await client.get("/sharpit/api/panels")
            assert panels_response.status_code == 200
            for panel_id in sorted(PANEL_IDS):
                response = await client.get(f"/sharpit/api/{panel_id}")
                assert response.status_code == 404, panel_id

    asgi_loop.run_until_complete(check())


def test_all_0_4_panel_flags_are_registered() -> None:
    assert set(ALL_IMPLEMENTED) == ALL_PANEL_IDS
