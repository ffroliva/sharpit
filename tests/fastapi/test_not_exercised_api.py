"""Declared route exercise coverage over real HTTP capture."""

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install

API = "/sharpit/api/runtime-insights"


def test_a_route_nobody_called_is_listed_and_a_called_one_is_not():
    app = FastAPI()

    @app.get("/called/{item_id}")
    @app.get("/uncalled")
    def endpoint(item_id: str = ""):
        return item_id

    install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/called/7").status_code == 200
        assert client.get(API).json()["notExercised"] == ["GET /uncalled"]


def test_a_plain_starlette_route_called_once_is_not_listed_without_a_limitation():
    app = FastAPI()
    app.add_route(
        "/plain/{name}", lambda request: __import__("starlette.responses", fromlist=["JSONResponse"]).JSONResponse({})
    )
    install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/plain/a").status_code == 200
        report = client.get(API).json()
        assert report["notExercised"] == []
        assert (
            "1 declared HTTP route is left out because its captured route template is not available."
            in report["limitations"]
        )


def test_included_router_and_mounted_fastapi_routes_match_their_labels():
    from fastapi import APIRouter

    app = FastAPI()
    router = APIRouter()
    router.add_api_route("/items/{id:int}", lambda id: {})
    app.include_router(router, prefix="/api")
    sub = FastAPI()
    sub.add_api_route("/child/{name}", lambda name: {})
    app.mount("/sub", sub)
    install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/items/7").status_code == 200
        assert client.get("/sub/child/a").status_code == 200
        assert client.get(API).json()["notExercised"] == []


def test_a_mounted_starlette_subapp_route_is_left_out_with_a_limitation():
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    app = FastAPI()
    app.mount("/sub", Starlette(routes=[Route("/child/{name}", lambda request: JSONResponse({}))]))
    install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/sub/child/a").status_code == 200
        report = client.get(API).json()
        assert report["notExercised"] == []
        assert any("route template is not available" in text for text in report["limitations"])


def test_a_request_path_never_appears_in_not_exercised():
    app = FastAPI()
    app.add_api_route("/declared", lambda: {})
    install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/not-declared/private-token-123").status_code == 404
        assert client.get(API).json()["notExercised"] == ["GET /declared"]


def test_a_low_footprint_transition_refuses_even_after_resume():
    from sharpit.engine.lowfootprint import LowFootprintService
    from sharpit.fastapi.capture import HOOK_CAPTURE_MIDDLEWARE

    app = FastAPI()
    app.add_api_route("/uncalled", lambda: {})
    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        ctx = handle.context
        ctx.capture.wiring.suspend_hook(HOOK_CAPTURE_MIDDLEWARE)
        assert client.get("/uncalled").status_code == 200
        ctx.capture.wiring.resume_hook(HOOK_CAPTURE_MIDDLEWARE)
        report = client.get(API).json()
        assert report["notExercised"] == []
        assert any("HTTP recording was suspended" in text for text in report["limitations"])
        control = LowFootprintService(ctx.capture.hooks)
        control.suspend()
        control.resume()
        assert client.get(API).json()["notExercised"] == []


def test_the_mcp_tool_returns_the_same_unexercised_routes():
    app = FastAPI()
    app.add_api_route("/uncalled", lambda: {})
    install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON")
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_runtime_insights"}}
        result = client.post("/sharpit/api/mcp", json=call).json()["result"]["structuredContent"]
        assert result["notExercised"] == client.get(API).json()["notExercised"]
        assert result["notExercised"] == ["GET /uncalled"]


@pytest.mark.parametrize("surface", ["http", "mcp"])
def test_declared_secret_route_labels_are_masked_in_http_and_mcp_output(surface):
    secret = "AKIAIOSFODNN7EXAMPLE"
    app = FastAPI()
    app.add_api_route("/k/" + secret, lambda: {})
    install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON")
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        if surface == "http":
            response = client.get(API)
            body = response.json()
        else:
            call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_runtime_insights"}}
            response = client.post("/sharpit/api/mcp", json=call)
            body = response.json()["result"]["structuredContent"]
        assert secret not in response.text
        assert body["notExercised"] == ["******"]
