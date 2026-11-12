from __future__ import annotations

import functools
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.cache.clear import InProcessCacheProvider

LOCAL = ("127.0.0.1", 50000)


@pytest.fixture(autouse=True)
def _cache_read_lane_landed(monkeypatch: pytest.MonkeyPatch) -> None:
    """K1's route is reachable only once the Cache read lane flips the panel on (proposed deviation D-K1-2)."""
    from sharpit.engine import panels

    real = panels.panel_is_implemented
    monkeypatch.setattr(panels, "panel_is_implemented", lambda panel_id: panel_id == "cache" or real(panel_id))


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def _lru() -> Any:
    @functools.lru_cache
    def compute(x: int) -> int:
        return x

    compute(1)
    return compute


def _size(fn: Any) -> int:
    return fn.cache_info().currsize


def test_route_clear_one_evicts() -> None:
    cache = _lru()
    provider = InProcessCacheProvider()
    provider.register("in_process", "items", cache)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post(
            "/sharpit/api/cache/clear",
            json={"managerName": "in_process", "cacheName": "items", "confirm": True},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleared"
        assert resp.json()["caches"] == ["in_process/items"]
        assert _size(cache) == 0


def test_route_clear_all_evicts() -> None:
    c1 = _lru()
    c2 = _lru()
    provider = InProcessCacheProvider()
    provider.register("m1", "c1", c1)
    provider.register("m1", "c2", c2)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleared"
        assert resp.json()["clearedCaches"] == 2
        assert _size(c1) == 0
        assert _size(c2) == 0


def test_route_clear_requires_confirmation() -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)
    handle.context.cache_provider = InProcessCacheProvider()  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": False})
        assert resp.status_code == 400
        assert resp.json()["status"] == "confirmation_required"


def test_route_clear_disabled_409() -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=False)
    handle.context.cache_provider = InProcessCacheProvider()  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": True})
        assert resp.status_code == 409
        assert resp.json()["status"] == "disabled"


def test_route_clear_unavailable_when_no_backend() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": True})
        assert resp.status_code == 409
        assert resp.json()["status"] == "unavailable"


def test_route_clear_unknown_cache_404() -> None:
    provider = InProcessCacheProvider()
    provider.register("m1", "c1", _lru())

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post(
            "/sharpit/api/cache/clear",
            json={"managerName": "m1", "cacheName": "missing", "confirm": True},
        )
        assert resp.status_code == 404
        assert resp.json()["status"] == "not_found"


# finding 1: clearing is off by default, whatever the registry says
def test_route_clear_default_is_disabled_cache_intact() -> None:
    cache = _lru()
    provider = InProcessCacheProvider()
    provider.register("in_process", "items", cache)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": True})
        assert resp.status_code == 409
        assert resp.json()["status"] == "disabled"
        assert _size(cache) == 1


def test_settings_default_cache_clear_disabled() -> None:
    from sharpit.settings import SharpitSettings

    assert SharpitSettings().cache_clear_enabled is False


# findings 2 and 3 through the route
def test_route_confirm_string_false_clears_nothing() -> None:
    cache = _lru()
    provider = InProcessCacheProvider()
    provider.register("in_process", "items", cache)
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"all": True, "confirm": "false"})
        assert resp.status_code == 400
        assert _size(cache) == 1


def test_route_non_string_name_is_400_not_500() -> None:
    provider = InProcessCacheProvider()
    provider.register("in_process", "items", _lru())
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"managerName": 5, "cacheName": ["c"], "confirm": True})
        assert resp.status_code == 400
        assert resp.json()["status"] == "invalid_request"


# finding 7: a GET under the cache prefix never clears
def test_get_never_clears() -> None:
    cache = _lru()
    provider = InProcessCacheProvider()
    provider.register("in_process", "items", cache)
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, cache_clear_enabled=True)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        client.get("/sharpit/api/cache")
        client.get("/sharpit/api/cache/clear")
        assert _size(cache) == 1
