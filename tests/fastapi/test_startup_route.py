from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import sharpit
from conftest import golden
from fastapi import FastAPI


# ported: StartupControllerTests.startupReturnsStepsFromTimeline
def test_startup_route_returns_host_lifespan_step(no_side_effects) -> None:
    app = FastAPI()
    sharpit.install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))

    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        response = client.get("/sharpit/api/startup")
    no_side_effects.block_network()
    no_side_effects.rebaseline()

    assert response.status_code == 200
    assert response.json()["steps"][0]["name"] == "asgi.lifespan.startup"
    no_side_effects.verify()


# ported: StartupControllerTests.startupReturnsEmptyWhenActuatorUnavailable
def test_startup_disabled_returns_empty(no_side_effects) -> None:
    app = FastAPI()
    sharpit.install(
        app, enabled="ON", startup_enabled=False, show_banner=False, state_dir=str(no_side_effects.state_dir)
    )

    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        response = client.get("/sharpit/api/startup")
    no_side_effects.block_network()
    no_side_effects.rebaseline()

    assert response.status_code == 200
    assert response.json() == {"steps": []}
    no_side_effects.verify()


def test_startup_records_on_event_hosts(no_side_effects) -> None:
    app = FastAPI()

    @app.on_event("startup")
    async def host_startup() -> None:
        pass

    sharpit.install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        response = client.get("/sharpit/api/startup")
    no_side_effects.block_network()
    no_side_effects.rebaseline()

    assert response.status_code == 200
    assert response.json()["steps"][0]["name"] == "asgi.lifespan.startup"
    no_side_effects.verify()


def test_startup_golden_shape_23(no_side_effects) -> None:
    app = FastAPI()
    sharpit.install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        payload = client.get("/sharpit/api/startup").json()
    no_side_effects.block_network()
    no_side_effects.rebaseline()

    gold = golden("2.3.0/startup/captured")
    assert set(payload) == set(gold)
    assert set(payload["steps"][0]) == set(gold["steps"][0])
    no_side_effects.verify()


def _steps(app: FastAPI, no_side_effects) -> list[dict]:
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        steps = client.get("/sharpit/api/startup").json()["steps"]
    no_side_effects.block_network()
    no_side_effects.rebaseline()
    return steps


def test_startup_duration_measures_the_host_lifespan(no_side_effects) -> None:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.sleep(0.05)
        yield

    app = FastAPI(lifespan=lifespan)
    sharpit.install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))

    assert _steps(app, no_side_effects)[0]["durationMs"] >= 50
    no_side_effects.verify()


def test_startup_keeps_only_the_first_lifespan_run(no_side_effects) -> None:
    app = FastAPI()
    sharpit.install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))

    first = _steps(app, no_side_effects)
    second = _steps(app, no_side_effects)

    assert len(first) == 1
    assert second == first
    no_side_effects.verify()


def test_startup_records_nothing_when_the_host_startup_raises(no_side_effects) -> None:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        raise RuntimeError("boom")
        yield

    app = FastAPI(lifespan=lifespan)
    handle = sharpit.install(app, enabled="ON", show_banner=False, state_dir=str(no_side_effects.state_dir))

    no_side_effects.unblock_network()
    with pytest.raises(RuntimeError), TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)):
        pass
    no_side_effects.block_network()
    no_side_effects.rebaseline()

    assert handle.context.startup.report() == {"steps": []}
    assert handle.context.startup_time_ms is None
    no_side_effects.verify()
