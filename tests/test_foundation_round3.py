"""Lane F review round 3 (R3-1 and the golden empty-shape minor): regression tests, each red before its fix."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import BaseRoute, Route

import golden
from fastapi import FastAPI
from golden import UnverifiedParityWarning, assert_parity
from sharpit import install
from sharpit.fastapi.routes import sql_trace as sql_trace_routes


def test_sql_trace_route_module_is_mounted(monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.parametrize("shapes", [[], [None]], ids=["empty-list", "null-only-list"])
def test_golden_list_without_shape_information_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shapes: list[Any]
) -> None:
    monkeypatch.setattr(golden, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "captured.json").write_text(json.dumps({"items": shapes}), encoding="utf-8")

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        assert_parity("data", "data", {"items": [{"anything": 1}]})

    messages = [str(w.message) for w in seen if w.category is UnverifiedParityWarning]
    assert messages == ["data/data: golden list items has no shape information; its items are unchecked"]
