import json
import types
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import fastapi.routing
import pytest
from fastapi.security import OAuth2PasswordBearer
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from conftest import SideEffectGuard
from fastapi import APIRouter, Depends, FastAPI
from sharpit import install
from sharpit.engine.collectors.beans import beans_report
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import ProviderInfo
from sharpit.fastapi.introspector import FastApiIntrospector, _classify  # pyright: ignore[reportPrivateUsage]

LOCAL = ("127.0.0.1", 50000)
HERE = __name__


def get_db() -> Iterator[str]:
    yield "a"


_other = types.ModuleType("beans_other_mod")
exec("def get_db():\n    yield 'b'\n", _other.__dict__)  # noqa: S102 - a second module defining the same name
other_get_db: Any = _other.__dict__["get_db"]


def get_settings() -> str:
    return "s"


def get_repo(db: str = Depends(get_db), settings: str = Depends(get_settings)) -> str:
    return db + settings


def app_level() -> None: ...


def router_level() -> None: ...


def fake_db(settings: str = Depends(get_settings)) -> str:
    return "fake" + settings


class SessionMiddleware:
    """Stand-in for Starlette's (which needs ``itsdangerous``, not a sharpit dependency): same secret kwarg."""

    def __init__(self, app: ASGIApp, secret_key: str) -> None:
        self.app = app
        self.secret_key = secret_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


def _by_name(app: FastAPI) -> dict[str, ProviderInfo]:
    return {p.name: p for p in FastApiIntrospector(app).providers()}


def test_same_function_name_in_two_modules_distinct():
    app = FastAPI()

    @app.get("/a")
    def a(x: str = Depends(get_db), y: str = Depends(other_get_db)) -> None: ...

    names = set(_by_name(app))
    assert {f"{HERE}:get_db", "beans_other_mod:get_db"} <= names


def test_callable_instance_named_by_class_and_second_gets_suffix():
    first = OAuth2PasswordBearer(tokenUrl="t1")
    second = OAuth2PasswordBearer(tokenUrl="t2")
    app = FastAPI()

    @app.get("/a")
    def a(t: str = Depends(first)) -> None: ...

    @app.get("/b")
    def b(t: str = Depends(second), again: str = Depends(first)) -> None: ...

    beans = _by_name(app)
    base = "fastapi.security.oauth2:OAuth2PasswordBearer"
    assert base in beans
    assert f"{base}#2" in beans
    assert f"{base}#3" not in beans
    assert beans[base].type_name == base
    assert beans[base].scope == "request"


def test_nested_depends_edges():
    app = FastAPI()

    @app.get("/a")
    def a(repo: str = Depends(get_repo)) -> None: ...

    beans = _by_name(app)
    assert beans[f"{HERE}:get_repo"].dependencies == (f"{HERE}:get_db", f"{HERE}:get_settings")
    assert beans[f"{HERE}:get_db"].dependencies == ()


def test_router_and_app_level_dependencies_included():
    app = FastAPI(dependencies=[Depends(app_level)])
    router = APIRouter(dependencies=[Depends(router_level)])

    @router.get("/r")
    def r() -> None: ...

    app.include_router(router, prefix="/p")
    beans = _by_name(app)
    assert f"{HERE}:app_level" in beans
    assert f"{HERE}:router_level" in beans


def test_middleware_bean_never_leaks_kwargs():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="s3cr3t")
    app.add_middleware(GZipMiddleware, minimum_size=500)
    beans = _by_name(app)
    assert beans[f"{HERE}:SessionMiddleware"].scope == "singleton"
    gzip = beans["starlette.middleware.gzip:GZipMiddleware"]
    assert gzip.scope == "singleton"
    assert gzip.classification == "FRAMEWORK"
    report = beans_report(_ctx(app), None, None, None, None)
    assert "s3cr3t" not in json.dumps(report)


def test_dependency_override_is_a_bean_and_original_carries_overridden_by():
    app = FastAPI()

    @app.get("/a")
    def a(db: str = Depends(get_db)) -> None: ...

    app.dependency_overrides[get_db] = fake_db
    beans = _by_name(app)
    assert f"{HERE}:fake_db" in beans
    assert beans[f"{HERE}:get_db"].overridden_by == f"{HERE}:fake_db"
    assert beans[f"{HERE}:fake_db"].overridden_by is None
    assert beans[f"{HERE}:fake_db"].dependencies == (f"{HERE}:get_settings",)  # the override's own Depends


@asynccontextmanager
async def host_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def test_lifespan_bean_is_host_lifespan():
    app = FastAPI(lifespan=host_lifespan)
    handle = install(app, enabled="ON", show_banner=False)
    names = {p.name: p for p in handle.context.introspector.providers()}
    assert names[f"{HERE}:host_lifespan"].scope == "singleton"
    assert not any(n.startswith("sharpit.") for n in names)


def test_lifespan_bean_unwraps_include_router_merges():
    # FastAPI wraps the lifespan in a merged one per include_router; real apps install() after including routers
    app = FastAPI(lifespan=host_lifespan)
    for prefix in ("/r1", "/r2", "/r3"):
        router = APIRouter()

        @router.get("/x")
        def x() -> None: ...

        app.include_router(router, prefix=prefix)
    handle = install(app, enabled="ON", show_banner=False)
    names = {p.name: p for p in handle.context.introspector.providers()}
    bean = names[f"{HERE}:host_lifespan"]
    assert bean.scope == "singleton"
    assert bean.classification == "APPLICATION"
    assert not any("merged_lifespan" in n for n in names)


@pytest.mark.skipif(not hasattr(fastapi.routing, "_DefaultLifespan"), reason="older FastAPI has no _DefaultLifespan")
def test_no_lifespan_with_routers_is_default_lifespan():
    app = FastAPI()
    app.include_router(APIRouter(), prefix="/r")
    handle = install(app, enabled="ON", show_banner=False)
    names = {p.name: p for p in handle.context.introspector.providers()}
    assert names["fastapi.routing:_DefaultLifespan"].classification == "FRAMEWORK"
    assert not any("merged_lifespan" in n for n in names)


def test_every_dependency_resolves_to_a_bean():
    app = FastAPI(dependencies=[Depends(app_level)])
    app.add_middleware(SessionMiddleware, secret_key="x")

    @app.get("/a")
    def a(repo: str = Depends(get_repo), t: str = Depends(OAuth2PasswordBearer(tokenUrl="t"))) -> None: ...

    app.dependency_overrides[get_settings] = fake_db
    providers = FastApiIntrospector(app).providers()
    names = {p.name for p in providers}
    assert len(names) == len(providers)
    assert all(dep in names for p in providers for dep in p.dependencies)


def test_classification_application_vs_framework():
    app = FastAPI()

    @app.get("/a")
    def a(db: str = Depends(get_db), t: str = Depends(OAuth2PasswordBearer(tokenUrl="t"))) -> None: ...

    beans = _by_name(app)
    assert beans[f"{HERE}:get_db"].classification == "APPLICATION"
    assert beans["fastapi.security.oauth2:OAuth2PasswordBearer"].classification == "FRAMEWORK"
    assert beans[f"{HERE}:get_db"].resource == f"{__file__}:{get_db.__code__.co_firstlineno}"


def test_real_session_middleware_never_leaks_secret():
    pytest.importorskip("itsdangerous")
    from starlette.middleware.sessions import SessionMiddleware as RealSession  # noqa: PLC0415

    app = FastAPI()
    app.add_middleware(RealSession, secret_key="s3cr3t")
    assert _by_name(app)["starlette.middleware.sessions:SessionMiddleware"].classification == "FRAMEWORK"
    assert "s3cr3t" not in json.dumps(beans_report(_ctx(app), None, None, None, None))


def test_stdlib_named_app_package_outside_stdlib_is_application(tmp_path: Any, monkeypatch: pytest.MonkeyPatch):
    fake = types.ModuleType("email.appdeps")
    fake.__file__ = str(tmp_path / "email" / "appdeps.py")
    monkeypatch.setitem(__import__("sys").modules, "email.appdeps", fake)
    assert _classify("email.appdeps:get_db") == "APPLICATION"
    assert _classify("asyncio.locks:Lock") == "PLATFORM"


def test_broken_route_is_skipped_not_fatal():
    app = FastAPI()

    @app.get("/a")
    def a(db: str = Depends(get_db)) -> None: ...

    class Boom:
        @property
        def dependant(self) -> Any:
            raise RuntimeError("boom")

    app.router.routes.append(Boom())  # type: ignore[arg-type]
    assert f"{HERE}:get_db" in _by_name(app)


def test_beans_route(no_side_effects: SideEffectGuard):
    no_side_effects.unblock_network()  # the Windows Proactor loop TestClient starts connects a self-pipe socketpair
    app = FastAPI()

    @app.get("/a")
    def a(repo: str = Depends(get_repo)) -> None: ...

    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)
    body = client.get("/sharpit/api/beans", params={"q": "get_", "classification": "application", "limit": 2}).json()
    assert [b["name"] for b in body["beans"]] == [f"{HERE}:get_db", f"{HERE}:get_repo"]
    assert body["page"]["matched"] == 3
    assert body["page"]["hasMore"] is True
    assert client.get("/sharpit/api/beans", params={"offset": "x"}).status_code == 400


def _ctx(app: FastAPI) -> SharpitContext:
    return install(app, enabled="ON", show_banner=False).context
