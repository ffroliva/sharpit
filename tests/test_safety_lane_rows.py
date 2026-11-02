"""F-rest item 2: the shared route tables take an implemented panel's rows from its lane safety file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

import safety
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import panels04
from sharpit.fastapi.routes import data as data_routes

WRITE = frozenset({"POST", "DELETE"})
LANE_FILE = """PANEL = "data"
GET_ROWS = ["/sharpit/api/data/probe"]
WRITE_ROWS = [("POST", "/sharpit/api/data/probe")]
"""


def _app() -> FastAPI:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False)
    return app


def _plant_data_routes(monkeypatch: pytest.MonkeyPatch, implemented: bool) -> None:
    def probe(request: Request) -> JSONResponse:
        return JSONResponse({})

    def build_routes(ctx: Any, host_app: Any) -> list[BaseRoute]:
        api = ctx.settings.api_path[len(ctx.settings.path) :]
        return [Route(f"{api}/data/probe", probe, methods=["GET", "POST"])]

    monkeypatch.setattr(data_routes, "build_routes", build_routes)
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", implemented)


def test_lane_rows_complete_the_route_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", False)
    before_writes = safety.route_formats(_app(), WRITE)
    before_gets = safety.route_formats(_app(), frozenset({"GET"}))
    (tmp_path / "test_a_data_safety.py").write_text(LANE_FILE, encoding="utf-8")
    _plant_data_routes(monkeypatch, implemented=True)

    lane_gets, lane_writes = safety.lane_rows(tmp_path)
    app = _app()

    assert safety.route_formats(app, WRITE) - before_writes - lane_writes == set()
    assert {p for _m, p in safety.route_formats(app, frozenset({"GET"})) - before_gets} - lane_gets == set()


def test_route_without_a_lane_row_is_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", False)
    before = safety.route_formats(_app(), WRITE)
    _plant_data_routes(monkeypatch, implemented=True)

    _gets, lane_writes = safety.lane_rows(tmp_path)  # no lane file

    assert safety.route_formats(_app(), WRITE) - before - lane_writes == {("POST", "/sharpit/api/data/probe")}


def test_lane_rows_of_an_unimplemented_panel_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "test_a_data_safety.py").write_text(LANE_FILE, encoding="utf-8")
    monkeypatch.setitem(panels04.IMPLEMENTED, "data", False)
    assert safety.lane_rows(tmp_path) == (set(), set())
