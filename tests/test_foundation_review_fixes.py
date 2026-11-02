"""Lane F review round 1 (review.md findings 1-3): regression tests, each red before its fix."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import BaseRoute, Route

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import panels04
from sharpit.engine.panels import PANELS
from sharpit.engine.tools04 import sql_trace as sql_trace_tools
from sharpit.fastapi.routes import sql_trace as sql_trace_routes
from sharpit.settings import load_settings

BASE_PANEL_IDS = [p.id for p in PANELS if p.id not in panels04.PANEL_04_IDS]


def test_sql_trace_route_and_tool_modules_are_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    probe_tool = object()
    monkeypatch.setattr(sql_trace_tools, "TOOLS", (probe_tool,))
    monkeypatch.setattr(sql_trace_tools, "COMMANDS", {"insights-probe": "get_insights_probe"})
    tools, commands = panels04.tool_definitions()
    assert probe_tool in tools
    assert commands.get("insights-probe") == "get_insights_probe"

    def probe(request: Request) -> PlainTextResponse:
        return PlainTextResponse("probe")

    def build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]:
        api = ctx.settings.api_path[len(ctx.settings.path) :]
        return [Route(f"{api}/sql-trace/insights-probe", probe, methods=["GET"])]

    monkeypatch.setattr(sql_trace_routes, "build_routes", build_routes)
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.get("/sharpit/api/sql-trace/insights-probe").text == "probe"


def _type_error(models: object) -> str | None:
    try:
        install(FastAPI(), enabled="ON", show_banner=False, models=models)
    except TypeError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize("models", ["Base", b"Base", {"Base": 1}], ids=["str", "bytes", "mapping"])
def test_models_hook_rejects_a_string(models: object) -> None:
    message = _type_error(models)
    assert message == f"models must be a model class or an iterable of models, not {type(models).__name__}"


def _value_error(panels: dict[str, object]) -> str | None:
    try:
        load_settings({"panels": panels}, {})
    except ValueError as exc:
        return str(exc)
    return None


def test_unknown_panel_message_lists_only_implemented_panels() -> None:
    known = ", ".join(BASE_PANEL_IDS)
    assert _value_error({"nope": {"enabled": False}}) == f"Unknown sharpit panel(s): nope; known panels: {known}"
    assert _value_error({"postgresql": {"enabled": False}}) == (
        f"Unknown sharpit panel(s): postgresql; known panels: {known}"
    )
