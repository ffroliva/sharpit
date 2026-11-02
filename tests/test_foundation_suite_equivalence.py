from __future__ import annotations

import json

import pytest
from starlette.routing import Mount

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.tools import TOOLS, CallContext, call_tool


def test_foundation_suite_equivalence(pytester: pytest.Pytester) -> None:
    app = FastAPI(title="foundation")
    handle = install(app, enabled="ON", show_banner=False)
    tools = TOOLS
    tool_names = [tool.name for tool in tools]
    overview = call_tool(CallContext(handle.context, {}), "get_overview", {}, via="mcp")
    mount = next(route for route in app.router.routes if isinstance(route, Mount) and route.path == "/sharpit")
    route_paths = [route.path for route in mount.app.routes]

    assert tool_names[0] == "get_overview"
    assert overview["applicationName"] == "foundation"
    assert route_paths[:4] == ["/", "/assets/{file}", "/api/auth/session", "/api/panels"]
    assert route_paths.index("/api/exceptions/stream") < route_paths.index("/api/exceptions/{id}")
    assert route_paths[-2:] == ["/api/cli", "/api/cli/tools/{tool}"]

    pytester.makepyfile("def test_report_control(): pass")
    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")
    data = json.loads((pytester.path / "report.json").read_text())

    assert result.ret == 0
    assert data["schema"] == "sharpit-report/1"
    assert data["status"] == "unknown"
