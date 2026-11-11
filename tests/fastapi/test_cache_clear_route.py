from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.cache.clear import InProcessCacheProvider

LOCAL = ("127.0.0.1", 50000)


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def test_route_clear_one_evicts() -> None:
    cache: dict[str, str] = {"key": "value"}
    provider = InProcessCacheProvider()
    provider.register("in_process", "items", cache)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post(
            "/sharpit/api/cache/clear",
            json={"managerName": "in_process", "cacheName": "items", "confirm": True},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleared"
        assert resp.json()["caches"] == ["in_process/items"]
        assert len(cache) == 0


def test_route_clear_all_evicts() -> None:
    c1: dict[str, str] = {"a": "1"}
    c2: dict[str, str] = {"b": "2"}
    provider = InProcessCacheProvider()
    provider.register("m1", "c1", c1)
    provider.register("m1", "c2", c2)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleared"
        assert resp.json()["clearedCaches"] == 2
        assert len(c1) == 0
        assert len(c2) == 0


def test_route_clear_requires_confirmation() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": False})
        assert resp.status_code == 400
        assert resp.json()["status"] == "confirmation_required"


def test_route_clear_disabled_409() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, cache_clear_enabled=False)

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": True})
        assert resp.status_code == 409
        assert resp.json()["status"] == "disabled"


def test_route_clear_unavailable_when_no_backend() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": True})
        assert resp.status_code == 409
        assert resp.json()["status"] == "unavailable"


def test_route_clear_unknown_cache_404() -> None:
    provider = InProcessCacheProvider()
    provider.register("m1", "c1", {})

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post(
            "/sharpit/api/cache/clear",
            json={"managerName": "m1", "cacheName": "missing", "confirm": True},
        )
        assert resp.status_code == 404
        assert resp.json()["status"] == "not_found"
