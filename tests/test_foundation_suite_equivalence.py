from __future__ import annotations

import json

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.tool_registry import catalogue
from sharpit.engine.tools import CallContext, call_tool


def test_foundation_suite_equivalence(pytester: pytest.Pytester) -> None:
    app = FastAPI(title="foundation")
    handle = install(app, enabled="ON", show_banner=False)
    tools = catalogue()
    tool_names = [tool.name for tool in tools]
    overview = call_tool(CallContext(handle.context, {}), "get_overview", {}, via="mcp")

    assert tool_names[0] == "get_overview"
    assert overview["applicationName"] == "foundation"

    pytester.makepyfile("def test_report_control(): pass")
    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")
    data = json.loads((pytester.path / "report.json").read_text())

    assert result.ret == 0
    assert data["schema"] == "sharpit-report/1"
    assert data["status"] == "unknown"
