"""Every introspecting surface leaves user route code alone (spec §5, review rows 1-2; PLAN.md Review Focus 4).

A trap route and a trap mount record every property read and method call made on them. Every GET under the sharpit
API, every MCP read tool and the REST API scan (CLI) run against an app that holds them; the trap stays untouched.
Later lanes add a surface by adding ``tests/fastapi/trap_surfaces_<lane>.py`` with ``GET_PATHS``, ``MCP_TOOLS`` or
``CLI_TOOLS`` lists (each optional); this file is never edited for that.
"""

from __future__ import annotations

import builtins
import importlib.util
import io
import linecache
import os
import sys
import tokenize
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.routing import BaseRoute, Match, Mount, Route

from conftest import get_paths
from fastapi import APIRouter, Depends, FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.sources import sqlite
from sharpit.engine.tools import TOOLS
from sharpit.fastapi.introspector import FastApiIntrospector

LOCAL = ("127.0.0.1", 50000)
TOUCHED: list[str] = []


class TrapRoute(BaseRoute):
    """A custom route class: every property read and method call on it is recorded."""

    @property
    def __class__(self) -> type:  # pyright: ignore[reportIncompatibleMethodOverride]  # isinstance() reads it
        TOUCHED.append("TrapRoute.__class__")
        return TrapRoute

    @property
    def path(self) -> str:
        TOUCHED.append("TrapRoute.path")
        return "/trap"

    @property
    def endpoint(self) -> object:
        TOUCHED.append("TrapRoute.endpoint")
        return None

    def effective_candidates(self) -> list[object]:
        TOUCHED.append("TrapRoute.effective_candidates")
        return []

    def matches(self, scope: Any) -> tuple[Match, dict[str, Any]]:
        TOUCHED.append("TrapRoute.matches")
        return Match.NONE, {}

    def url_path_for(self, name: str, /, **path_params: Any) -> Any:
        TOUCHED.append("TrapRoute.url_path_for")
        raise AssertionError("url_path_for was called")


class TrapMount(Mount):
    """A ``Mount`` subclass whose ``routes`` property is user code."""

    @property
    def routes(self) -> list[BaseRoute]:
        TOUCHED.append("TrapMount.routes")
        return []


async def _plain(_request: Any) -> None:
    raise AssertionError("an endpoint was called")


def _trap_app() -> FastAPI:
    app = FastAPI()
    app.get("/items")(lambda: "items")
    router = APIRouter()
    router.routes.append(TrapRoute())
    app.include_router(router, prefix="/v1")
    app.router.routes.append(TrapRoute())
    app.router.routes.append(TrapMount("/m", routes=[Route("/a", _plain), TrapRoute()]))
    return app


def _lane_surfaces(name: str) -> list[str]:
    found: list[str] = []
    for file in sorted(Path(__file__).parent.glob("trap_surfaces_*.py")):
        spec = importlib.util.spec_from_file_location(f"_trap_{file.stem}", file)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        found.extend(getattr(module, name, []))
    return found


GET_PATHS = sorted({p for p in get_paths() if "{" not in p} | set(_lane_surfaces("GET_PATHS")))
# get_paths() installs the sample app at collection: undo its sqlite3/SQLAlchemy hooks now, or a module collected
# later (test_sqlite_console's REAL_CONNECT) records the patched sqlite3.connect as the real one
sqlite.detach_all()
sqla.detach_all()
MCP_TOOLS = sorted({t.name for t in TOOLS if not t.action} | set(_lane_surfaces("MCP_TOOLS")))
CLI_TOOLS = sorted({"rest_api_scan"} | set(_lane_surfaces("CLI_TOOLS")))


def test_trap_route_untouched_by_every_introspecting_surface():
    TOUCHED.clear()
    app = _trap_app()
    install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON", cli_enabled=True)
    TOUCHED.clear()  # install() itself is not a read surface
    with TestClient(app, base_url="http://localhost", client=LOCAL) as client:
        for path in GET_PATHS:
            client.get(path)
        client.get("/sharpit/api/fastapi-security/explain", params={"method": "GET", "path": "/trap"})
        for number, tool in enumerate(MCP_TOOLS):
            call: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": number,
                "method": "tools/call",
                "params": {"name": tool, "arguments": {}},
            }
            client.post("/sharpit/api/mcp", json=call)
        for tool in CLI_TOOLS:
            client.post(f"/sharpit/api/cli/tools/{tool}", json={})
    assert TOUCHED == []


class _Provider:
    """A class bean (its line is the class's, without reading the file)."""

    def __call__(self) -> str:
        raise AssertionError("a dependency was called")


def _function_provider() -> str:
    raise AssertionError("a dependency was called")


def test_beans_resource_never_opens_the_source_file(monkeypatch: pytest.MonkeyPatch):
    # spec §4.4 / §14 beans row (R-fastapi-security Task 3): ``resource`` comes from compiled metadata
    app = FastAPI()
    app.get("/a", dependencies=[Depends(_function_provider), Depends(_Provider())])(lambda: "a")
    here = os.path.realpath(__file__)
    opened: list[str] = []
    for owner, attr in ((builtins, "open"), (io, "open"), (tokenize, "_builtin_open")):
        original = getattr(owner, attr)

        def spy(file: Any, *args: Any, _original: Any = original, _name: str = attr, **kwargs: Any) -> Any:
            if isinstance(file, str) and os.path.realpath(file) == here:
                opened.append(_name)
            return _original(file, *args, **kwargs)

        monkeypatch.setattr(owner, attr, spy)
    linecache.checkcache()
    monkeypatch.setattr(linecache, "cache", {})  # a warm cache would hide a read
    beans = {p.name: p.resource for p in FastApiIntrospector(app, "/sharpit").providers()}
    assert opened == []
    assert beans[f"{__name__}:_function_provider"] == f"{__file__}:{_function_provider.__code__.co_firstlineno}"


LAZY_TOUCHED: list[str] = []


class _LazyProxy:
    """A class-level lazy object (a settings proxy): any attribute read runs its own code."""

    def __getattr__(self, name: str) -> Any:
        LAZY_TOUCHED.append(name)
        raise AttributeError(name)

    @property
    def __class__(self) -> type:  # pyright: ignore[reportIncompatibleMethodOverride]  # isinstance() reads it
        LAZY_TOUCHED.append("__class__")
        return _LazyProxy


def _lazy_call(self: object) -> str:
    raise AssertionError("a dependency was called")


# type()-built: no ``__firstlineno__`` on any Python, so the 3.12 fallback runs on every interpreter
_TypeBuilt = type("_TypeBuilt", (), {"settings": _LazyProxy(), "__call__": _lazy_call})


def test_class_provider_line_never_touches_class_attributes():
    # council R-fastapi-security #2: the 3.12 class-line fallback read ``__func__`` off every class attribute
    app = FastAPI()
    app.get("/l", dependencies=[Depends(_TypeBuilt())])(lambda: "l")
    LAZY_TOUCHED.clear()
    beans = {p.name: p.resource for p in FastApiIntrospector(app, "/sharpit").providers()}
    assert LAZY_TOUCHED == []
    assert beans[f"{__name__}:_TypeBuilt"] == f"{__file__}:{_lazy_call.__code__.co_firstlineno}"


def test_class_provider_resource_is_its_definition_line():
    # council R-fastapi-security #3: the class branch of ``_first_line`` (3.13+ class line, 3.12 first ``def``)
    app = FastAPI()
    app.get("/c", dependencies=[Depends(_Provider())])(lambda: "c")
    beans = {p.name: p.resource for p in FastApiIntrospector(app, "/sharpit").providers()}
    if sys.version_info >= (3, 13):
        line = vars(_Provider)["__firstlineno__"]
    else:
        line = _Provider.__call__.__code__.co_firstlineno
    assert beans[f"{__name__}:_Provider"] == f"{__file__}:{line}"


HOOK_ARMED = [False]


class _Checker:
    """A callable-instance dependency whose ``__getattr__`` raises while armed."""

    def __call__(self) -> None:
        raise AssertionError("a dependency was called")

    def __getattr__(self, name: str) -> Any:
        if HOOK_ARMED[0]:
            raise RuntimeError(name)
        raise AttributeError(name)


def test_callable_instance_provider_hook_never_runs():
    # council R-fastapi-security #4: ``hasattr(obj, "__qualname__")`` ran the instance's ``__getattr__``
    app = FastAPI()
    app.get("/q", dependencies=[Depends(_Checker())])(lambda: "q")
    HOOK_ARMED[0] = True
    try:
        names: Any = [p.name for p in FastApiIntrospector(app, "/sharpit").providers()]
    except RuntimeError as exc:
        names = f"raised RuntimeError: {exc}"
    finally:
        HOOK_ARMED[0] = False
    assert f"{__name__}:_Checker" in names
