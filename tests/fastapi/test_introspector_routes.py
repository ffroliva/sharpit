from pathlib import Path

import pytest
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse as StarletteText
from starlette.routing import BaseRoute, Host, Mount, Route, WebSocketRoute

from conftest import SideEffectGuard
from fastapi import APIRouter, FastAPI, Request, UploadFile, WebSocket
from sharpit import install
from sharpit.engine.spi import RouteInfo
from sharpit.fastapi.introspector import FastApiIntrospector

LOCAL = ("127.0.0.1", 50000)


async def plain(_request: Request) -> StarletteText:
    return StarletteText("x")


async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.close()


class Odd(BaseRoute):
    async def handle(self, scope, receive, send) -> None: ...  # type: ignore[no-untyped-def]

    def matches(self, scope):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def url_path_for(self, name, /, **path_params):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def _app(tmp_path: Path) -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}", name="read_item")
    def read_item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    @app.api_route("/multi", methods=["GET", "POST"])
    def multi() -> dict[str, str]:
        return {}

    @app.post("/upload")
    def upload(file: UploadFile) -> dict[str, str]:
        return {}

    @app.post("/body")
    def body(payload: dict[str, int]) -> dict[str, str]:
        return {}

    @app.get("/text", response_class=PlainTextResponse)
    def text() -> str:
        return "x"

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.close()

    router = APIRouter()

    @router.get("/ping")
    def ping() -> str:
        return "pong"

    app.include_router(router, prefix="/v1")
    app.router.routes.append(Route("/starlette", plain, methods=["GET"]))
    app.router.routes.append(WebSocketRoute("/raw-ws", ws_endpoint))
    app.mount("/static", StaticFiles(directory=tmp_path), name="static")
    app.mount("/sub", Starlette(routes=[Route("/a", plain), Mount("/deep", routes=[Route("/b", plain)])]))
    app.router.routes.append(Host("api.example.com", app=Starlette(routes=[Route("/h", plain)])))
    app.router.routes.append(Odd())
    install(app, enabled="ON", show_banner=False)
    return app


def _by(routes: list[RouteInfo]) -> dict[tuple[str, str], RouteInfo]:
    return {(m, r.path): r for r in routes for m in (r.methods or ("ANY",))}


def test_routes_exact_rows(tmp_path: Path, no_side_effects: SideEffectGuard):
    routes = FastApiIntrospector(_app(tmp_path), "/sharpit").routes()
    assert sorted(_by(routes)) == sorted(
        [
            ("GET", "/items/{item_id}"),
            ("GET", "/multi"),
            ("POST", "/multi"),
            ("POST", "/upload"),
            ("POST", "/body"),
            ("GET", "/text"),
            ("WS", "/ws"),
            ("GET", "/v1/ping"),
            ("GET", "/starlette"),
            ("WS", "/raw-ws"),
            ("ANY", "/static/{path}"),
            ("GET", "/sub/a"),
            ("GET", "/sub/deep/b"),
            ("GET", "/h"),
            ("GET", "/openapi.json"),
            ("GET", "/docs"),
            ("GET", "/docs/oauth2-redirect"),
            ("GET", "/redoc"),
            ("ANY", "(any)"),  # the custom BaseRoute: best-effort row, no crash
        ]
    )
    assert len(routes) == len({(r.methods, r.path) for r in routes})  # no sharpit rows, no duplicates


def test_row_details(tmp_path: Path, no_side_effects: SideEffectGuard):
    rows = _by(FastApiIntrospector(_app(tmp_path), "/sharpit").routes())
    item = rows["GET", "/items/{item_id}"]
    assert (item.handler, item.name, item.produces, item.consumes, item.host) == (
        f"{__name__}:_app.<locals>.read_item",
        "read_item",
        "application/json",
        None,
        None,
    )
    assert rows["POST", "/upload"].consumes == "multipart/form-data"
    assert rows["POST", "/body"].consumes == "application/json"
    assert rows["GET", "/text"].produces == "text/plain"
    assert rows["GET", "/starlette"].produces is None
    assert rows["WS", "/ws"].handler.endswith("_app.<locals>.ws")
    assert rows["WS", "/raw-ws"].handler == f"{__name__}:ws_endpoint"
    assert rows["GET", "/h"].host == "api.example.com"
    assert rows["ANY", "/static/{path}"].handler == "starlette.staticfiles:StaticFiles"
    assert "HEAD" not in {m for m, _ in rows}


def test_handler_never_uses_repr_of_closure_values(no_side_effects: SideEffectGuard):
    secret = "s3cr3t-value"
    app = FastAPI()

    def make(token: str):  # type: ignore[no-untyped-def]
        def handler() -> str:
            return token

        return handler

    app.add_api_route("/c", make(secret))
    (route,) = [r for r in FastApiIntrospector(app, None).routes() if r.path == "/c"]
    assert secret not in route.handler and "0x" not in route.handler


def test_routes_added_after_install_appear_later(tmp_path: Path, no_side_effects: SideEffectGuard):
    app = _app(tmp_path)
    intro = FastApiIntrospector(app, "/sharpit")
    assert ("GET", "/late") not in _by(intro.routes())
    app.router.routes.append(Route("/late", plain))
    assert ("GET", "/late") in _by(intro.routes())


def test_endpoint_is_flat_json_and_sharpit_excluded(tmp_path: Path, no_side_effects: SideEffectGuard):
    no_side_effects.unblock_network()  # the Windows Proactor loop TestClient starts connects a self-pipe socketpair
    client = TestClient(_app(tmp_path), base_url="http://localhost", client=LOCAL)
    resp = client.get("/sharpit/api/mappings/flat", params={"q": "ping"})
    assert resp.status_code == 200
    body = resp.json()
    assert [(m["method"], m["pattern"]) for m in body["mappings"]] == [("GET", "/v1/ping")]
    assert body["page"]["matched"] == 1 and body["total"] > 10
    everything = client.get("/sharpit/api/mappings/flat").json()["mappings"]
    assert not [m for m in everything if m["pattern"].startswith("/sharpit")]
    assert client.get("/sharpit/api/mappings/flat", params={"limit": "x"}).status_code == 400


def test_self_referencing_mount_stops_with_a_row(no_side_effects: SideEffectGuard):
    loop = Mount("/loop", routes=[Route("/x", plain)])
    loop.routes.append(loop)
    app = Starlette(routes=[loop])
    rows = _by(FastApiIntrospector(app, None).routes())
    assert ("GET", "/loop/x") in rows and ("ANY", "/loop/loop/{path}") in rows


def test_mount_chain_deeper_than_cap_stops_with_a_row(no_side_effects: SideEffectGuard):
    inner: Starlette = Starlette(routes=[Route("/leaf", plain)])
    for _ in range(40):
        inner = Starlette(routes=[Mount("/n", app=inner)])
    paths = [r.path for r in FastApiIntrospector(inner, None).routes()]
    assert (
        len(paths) == 1 and paths[0].endswith("/{path}") and paths[0].count("/n") == 33
    )  # 32 descents plus the mount that stopped


def test_failing_include_router_expansion_yields_fallback_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_side_effects: SideEffectGuard
):
    app = _app(tmp_path)
    included = next(r for r in app.routes if hasattr(r, "effective_candidates"))

    def boom() -> None:
        raise RuntimeError("drift")

    monkeypatch.setattr(included, "effective_candidates", boom)
    rows = _by(FastApiIntrospector(app, "/sharpit").routes())
    row = rows["ANY", "/v1/{path}"]
    assert row.handler == "<unexpanded include_router>"
    assert ("GET", "/items/{item_id}") in rows  # the rest of the listing survives


@pytest.mark.parametrize("path", ["/dev-tools", "/dev-tools/"])
def test_custom_sharpit_path_excluded(path: str, no_side_effects: SideEffectGuard):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, path=path.rstrip("/"))
    assert not [r for r in FastApiIntrospector(app, path).routes() if r.path.startswith("/dev-tools")]
