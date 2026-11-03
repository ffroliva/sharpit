"""Every introspecting surface leaves user route code alone (spec §5, review rows 1-2; PLAN.md Review Focus 4).

A trap route and a trap mount record every property read and method call made on them. Every GET under the sharpit
API, every MCP read tool and the REST API scan (CLI) run against an app that holds them; the trap stays untouched.
Later lanes add a surface by adding ``tests/fastapi/trap_surfaces_<lane>.py`` with ``GET_PATHS``, ``MCP_TOOLS`` or
``CLI_TOOLS`` lists (each optional); this file is never edited for that.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from starlette.routing import BaseRoute, Match, Mount, Route

from conftest import get_paths
from fastapi import APIRouter, FastAPI
from sharpit import install
from sharpit.engine.tools import TOOLS

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
