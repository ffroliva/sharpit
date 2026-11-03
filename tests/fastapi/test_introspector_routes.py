from pathlib import Path
from typing import Any

import pytest
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse as StarletteText
from starlette.routing import BaseRoute, Host, Mount, Route, WebSocketRoute

from conftest import SideEffectGuard
from fastapi import APIRouter, Depends, FastAPI, Request, UploadFile, WebSocket
from sharpit import install
from sharpit.engine.collectors.restapi.rules import application_routes
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
    assert secret not in route.handler
    assert "0x" not in route.handler


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
    assert body["page"]["matched"] == 1
    assert body["total"] > 10
    everything = client.get("/sharpit/api/mappings/flat").json()["mappings"]
    assert not [m for m in everything if m["pattern"].startswith("/sharpit")]
    assert client.get("/sharpit/api/mappings/flat", params={"limit": "x"}).status_code == 400


def test_self_referencing_mount_stops_with_a_row(no_side_effects: SideEffectGuard):
    loop = Mount("/loop", routes=[Route("/x", plain)])
    loop.routes.append(loop)
    app = Starlette(routes=[loop])
    rows = _by(FastApiIntrospector(app, None).routes())
    assert ("GET", "/loop/x") in rows
    assert ("ANY", "/loop/loop/{path}") in rows


def test_mount_chain_deeper_than_cap_stops_with_a_row(no_side_effects: SideEffectGuard):
    inner: Starlette = Starlette(routes=[Route("/leaf", plain)])
    for _ in range(40):
        inner = Starlette(routes=[Mount("/n", app=inner)])
    paths = [r.path for r in FastApiIntrospector(inner, None).routes()]
    assert len(paths) == 1
    assert paths[0].endswith("/{path}")
    assert paths[0].count("/n") == 33


def test_lazy_include_router_expansion_never_calls_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_side_effects: SideEffectGuard
):
    app = _app(tmp_path)
    included = next((r for r in app.routes if hasattr(r, "effective_candidates")), None)
    if included is None:
        pytest.skip("this FastAPI expands include_router eagerly")

    calls: list[str] = []
    monkeypatch.setattr(included, "effective_candidates", lambda: calls.append("called") or [])
    rows = _by(FastApiIntrospector(app, "/sharpit").routes())
    assert calls == []
    assert ("GET", "/v1/ping") in rows


@pytest.mark.parametrize("path", ["/dev-tools", "/dev-tools/"])
def test_custom_sharpit_path_excluded(path: str, no_side_effects: SideEffectGuard):
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, path=path.rstrip("/"))
    assert not [r for r in FastApiIntrospector(app, path).routes() if r.path.startswith("/dev-tools")]


class TimedRoute(APIRoute):
    """A user ``route_class``: a real ``APIRoute`` subclass, as ``APIRouter(route_class=...)`` builds."""


def test_custom_apiroute_subclass_still_classified(no_side_effects: SideEffectGuard):
    router = APIRouter(route_class=TimedRoute)

    @router.get("/timed")
    def timed() -> str:  # pyright: ignore[reportUnusedFunction]
        return "t"

    app = FastAPI()
    app.include_router(router)
    intro = FastApiIntrospector(app, "/sharpit")
    mappings = [(r.methods, r.path, r.handler) for r in intro.routes() if r.path == "/timed"]
    rest_api = [r.path for r in application_routes(intro.api_model().routes)]  # as the rest-api scan reads it
    security = [(r.path, r.opaque) for r in intro.security_model().routes]
    assert mappings == [
        (("GET",), "/timed", f"{__name__}:test_custom_apiroute_subclass_still_classified.<locals>.timed")
    ]
    assert rest_api == ["/timed"]
    assert security == [("/timed", False)]


class CountingMount(Mount):
    reads = 0

    @property
    def routes(self) -> list[BaseRoute]:
        CountingMount.reads += 1
        return []


def test_mount_property_never_evaluated(no_side_effects: SideEffectGuard):
    CountingMount.reads = 0
    app = FastAPI()
    app.router.routes.append(CountingMount("/m", routes=[Route("/a", plain)]))
    intro = FastApiIntrospector(app, "/sharpit")
    intro.routes()
    intro.api_model()
    intro.security_model()
    intro.providers()
    assert CountingMount.reads == 0


class Slotted:
    """An app-like object without ``__dict__`` (the pytest plugin passes a SQLAlchemy ``AsyncEngine`` as the app)."""

    __slots__ = ("name",)


def _read_or_error(read: Any) -> object:
    try:
        return read()
    except TypeError as exc:  # the defect: vars() on a slotted object
        return f"raised {exc}"


def test_object_without_dict_has_no_routes():
    intro = FastApiIntrospector(Slotted())
    assert _read_or_error(intro.routes) == []
    assert _read_or_error(lambda: intro.api_model().routes) == ()
    assert _read_or_error(intro.providers) == []


ARMED = [False]
CALLS: list[str] = []


class RecordingApp(FastAPI):
    """An app subclass whose ``__getattribute__`` is user code: recorded while armed."""

    def __getattribute__(self, name: str) -> Any:
        if ARMED[0]:
            CALLS.append(f"app.{name}")
        return super().__getattribute__(name)


class RecordingRoute(APIRoute):
    def __getattribute__(self, name: str) -> Any:
        if ARMED[0]:
            CALLS.append(f"route.{name}")
        return super().__getattribute__(name)


class RaisingApp(FastAPI):
    def __getattribute__(self, name: str) -> Any:
        if ARMED[0]:
            raise RuntimeError(name)
        return super().__getattribute__(name)


class RaisingRoute(APIRoute):
    def __getattribute__(self, name: str) -> Any:
        if ARMED[0]:
            raise RuntimeError(name)
        return super().__getattribute__(name)


def _dep() -> str:
    raise AssertionError("a dependency was called")


def _outcome(read: Any) -> Any:
    try:
        return read()
    except Exception as exc:  # noqa: BLE001 - the defect: a user hook's exception escapes the introspector
        return f"raised {type(exc).__name__}: {exc}"


def _hooked_app(app_type: type[FastAPI], route_type: type[APIRoute]) -> FastAPI:
    app = app_type()
    app.router.route_class = route_type
    app.get("/a", dependencies=[Depends(_dep)])(lambda: "a")
    return app


def test_user_getattribute_never_runs_on_any_surface():
    # council R-fastapi-security #1: vars() went through the type's __getattribute__
    app = _hooked_app(RecordingApp, RecordingRoute)
    CALLS.clear()
    ARMED[0] = True
    try:
        intro = FastApiIntrospector(app, "/sharpit")
        intro.app_info()
        intro.routes()
        intro.api_model()
        intro.security_model()
        intro.providers()
    finally:
        ARMED[0] = False
    assert CALLS == []


def test_user_getattribute_that_raises_degrades():
    app = _hooked_app(RaisingApp, RaisingRoute)
    ARMED[0] = True
    try:
        intro = _outcome(lambda: FastApiIntrospector(app, "/sharpit"))
        paths = _outcome(lambda: [r.path for r in intro.routes()])
        beans = _outcome(lambda: [p.name for p in intro.providers()])
    finally:
        ARMED[0] = False
    assert isinstance(intro, FastApiIntrospector)
    assert "/a" in paths
    assert f"{__name__}:_dep" in beans


class SlottedHook:
    """No ``__dict__``, and a ``__getattr__`` that raises something other than ``AttributeError``."""

    __slots__ = ()

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(name)


def test_slotted_app_with_raising_getattr_has_no_routes():
    intro = _outcome(lambda: FastApiIntrospector(SlottedHook()))
    assert isinstance(intro, FastApiIntrospector)
    assert _outcome(intro.routes) == []
    assert _outcome(lambda: intro.api_model().routes) == ()
    assert _outcome(intro.providers) == []
