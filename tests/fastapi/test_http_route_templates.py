"""The ``route`` of an exchange (0.5.0 release council): a template, never a raw value of the request's path."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from fastapi import APIRouter, FastAPI
from sharpit import install

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/http-exchanges"
ROUTES = f"{API}/routes"
JWT = "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".dozjgNryP4J3jVmNHl0w5N"
ALPHABETIC = "resetToken" + "Abc"  # reads like a route word: mask_route keeps it
PLAIN_SEGMENT = "items"


def _sub_app() -> FastAPI:
    sub = FastAPI()
    sub.get(f"/{PLAIN_SEGMENT}/{{i}}")(lambda i: {})
    return sub


def _mounted(path: str, sub: Any) -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.router.routes.append(Mount(path, app=sub))
    install(app, enabled="ON", show_banner=False, mcp_enabled="ON")
    return app, TestClient(app, base_url="http://localhost", client=LOCAL)


def _route_row(client: TestClient) -> dict[str, Any]:
    rows = client.get(API).json()["exchanges"]
    return rows[0]


@pytest.mark.parametrize("value", [JWT, ALPHABETIC], ids=["jwt", "alphabetic"])
def test_a_mount_parameter_is_its_template_in_the_row(value: str) -> None:
    _, client = _mounted("/share/{tok}", _sub_app())

    assert client.get(f"/share/{value}/items/1").status_code == 200

    row = _route_row(client)
    assert (row["route"], row["routeSource"]) == ("/share/{tok}/items/{i}", "FRAMEWORK_TEMPLATE")


@pytest.mark.parametrize("value", [JWT, ALPHABETIC], ids=["jwt", "alphabetic"])
def test_a_mount_parameter_never_reaches_the_routes_report(value: str) -> None:
    _, client = _mounted("/share/{tok}", _sub_app())
    client.get(f"/share/{value}/items/1")

    report = client.get(ROUTES).json()

    assert value not in json.dumps(report), "the route, and the row id built from it"
    assert [r["id"] for r in report["routes"]] == ["GET /share/{tok}/items/{i}"]


def test_a_mount_parameter_shadowed_by_the_route_is_still_its_template() -> None:
    # the route's {i} overwrites the mount's in path_params, so the mount's value is not there to be found
    _, client = _mounted("/t/{i}", _sub_app())

    client.get(f"/t/{ALPHABETIC}/items/1")

    assert _route_row(client)["route"] == "/t/{i}/items/{i}"


def test_nested_mounts_keep_every_template() -> None:
    middle = FastAPI()
    middle.router.routes.append(Mount("/in/{inner}", app=_sub_app()))
    _, client = _mounted("/out/{outer}", middle)

    client.get(f"/out/{ALPHABETIC}/in/{JWT}/items/1")

    assert _route_row(client)["route"] == "/out/{outer}/in/{inner}/items/{i}"


def test_a_literal_mount_keeps_its_prefix() -> None:
    _, client = _mounted("/sub", _sub_app())

    client.get("/sub/items/1")

    row = _route_row(client)
    assert (row["route"], row["routeSource"]) == ("/sub/items/{i}", "FRAMEWORK_TEMPLATE")


def test_a_mount_the_walk_cannot_reach_falls_back_to_the_masked_path() -> None:
    # wrapped in plain ASGI, the sub-app's routes are out of the table: the prefix cannot be shown to be a template
    sub = _sub_app()

    async def wrapper(scope: Any, receive: Any, send: Any) -> None:
        await sub(scope, receive, send)

    hidden = Starlette(routes=[Mount("/deep/{tok}", app=wrapper)])
    _, client = _mounted("/share", hidden)

    client.get(f"/share/deep/{JWT}/items/1")

    assert JWT not in _route_row(client)["route"]


def test_a_root_path_from_the_server_is_not_part_of_the_route() -> None:
    app = FastAPI(root_path="/behind-proxy")
    app.get("/pets/{pet_id}")(lambda pet_id: {})
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    client.get("/pets/7")

    row = _route_row_of(client)
    assert (row["route"], row["routeSource"]) == ("/pets/{pet_id}", "FRAMEWORK_TEMPLATE")


def _route_row_of(client: TestClient) -> dict[str, Any]:
    return client.get(f"/behind-proxy{API}").json()["exchanges"][0]


def test_an_include_router_prefix_is_never_lost() -> None:
    router = APIRouter()
    router.get("/items/{i}")(lambda i: {})
    app = FastAPI()
    app.include_router(router, prefix="/api")
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    client.get("/api/items/12345")

    row = _route_row(client)
    assert row["route"].startswith("/api/items/"), "a template that does not match the path is not the route"
    assert "12345" not in row["route"]


def test_an_include_router_prefix_under_a_mount_is_never_lost() -> None:
    router = APIRouter()
    router.get("/items/{i}")(lambda i: {})
    sub = FastAPI()
    sub.include_router(router, prefix="/v1")
    _, client = _mounted("/sub", sub)

    client.get("/sub/v1/items/12345")

    row = _route_row(client)
    assert row["route"].startswith("/sub/v1/items/")
    assert "12345" not in row["route"]


def test_a_plain_starlette_route_shows_no_raw_value() -> None:
    # Starlette 1.x sets scope["route"] itself, older ones do not: either answer is safe, neither is the raw path
    async def endpoint(_: Any) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/owners/{owner}", endpoint)])
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    client.get("/owners/123")

    assert "123" not in _route_row(client)["route"]
