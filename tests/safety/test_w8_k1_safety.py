from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.cache.clear import InProcessCacheProvider

PANEL = "cache"
GET_ROWS: list[str] = []
WRITE_ROWS = [("POST", "/sharpit/api/cache/clear")]

LOCAL = ("127.0.0.1", 50000)


def _client(app: Any, peer: tuple[str, int] = LOCAL) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=peer)


def test_cache_clear_refused_read_only_cache_intact() -> None:
    cache: dict[str, str] = {"key": "value"}
    provider = InProcessCacheProvider()
    provider.register("in_process", "data", cache)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, read_only=True)
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"confirm": True, "all": True})
        assert resp.status_code == 403
        assert resp.json()["error"] == "sharpit panel access denied"
        assert "read-only via SHARPIT_READ_ONLY=true" in resp.json()["reason"]
        assert len(cache) == 1
        assert cache["key"] == "value"


def test_cache_clear_refused_when_panel_read_only() -> None:
    cache: dict[str, str] = {"key": "value"}
    provider = InProcessCacheProvider()
    provider.register("in_process", "data", cache)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, panels={"cache": {"read_only": True}})
    handle.context.cache_provider = provider  # type: ignore[attr-defined]

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"confirm": True, "all": True})
        assert resp.status_code == 403
        assert resp.json()["error"] == "sharpit panel access denied"
        assert "Panel is read-only via SHARPIT_PANELS_CACHE_READ_ONLY=true" in resp.json()["reason"]
        assert len(cache) == 1


def test_cache_clear_refused_when_panel_disabled() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, panels={"cache": {"enabled": False}})

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"confirm": True, "all": True})
        assert resp.status_code == 403
        assert resp.json()["error"] == "sharpit panel access denied"
        assert "Panel is disabled via SHARPIT_PANELS_CACHE_ENABLED=false" in resp.json()["reason"]


def test_cache_clear_refused_when_inactive() -> None:
    app = FastAPI()
    install(app, enabled="OFF", show_banner=False)

    with _client(app) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"confirm": True, "all": True})
        assert resp.status_code == 404


def test_cache_clear_refused_without_token() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, authentication_token="secret-token", allow_non_localhost=True)

    # Request from non-loopback peer without auth header
    remote_peer = ("198.51.100.1", 50000)
    with _client(app, peer=remote_peer) as client:
        resp = client.post("/sharpit/api/cache/clear", json={"confirm": True, "all": True})
        assert resp.status_code == 401


def test_cache_clear_refused_on_cross_site() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)

    with _client(app) as client:
        resp = client.post(
            "/sharpit/api/cache/clear",
            headers={"Sec-Fetch-Site": "cross-site"},
            json={"confirm": True, "all": True},
        )
        assert resp.status_code == 403


def test_cache_clear_refused_on_forbidden_host() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)

    with _client(app) as client:
        resp = client.post(
            "/sharpit/api/cache/clear",
            headers={"Host": "evil.com"},
            json={"confirm": True, "all": True},
        )
        assert resp.status_code == 403


def test_cache_clear_routes_rest_only() -> None:
    from sharpit.engine import tools

    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    mcp_tools = [t.name for t in tools.TOOLS]
    assert not any("cache_clear" in name or "clear_cache" in name for name in mcp_tools)
