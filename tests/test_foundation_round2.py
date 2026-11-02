"""Lane F review round 2 (ponytail-review.md + coordinator): flag-flip-safe foundation tests and re-armable slots.

Each panel test sets the flag of the panel under test both ways (``monkeypatch.setitem`` on
``sharpit.engine.panels04.IMPLEMENTED``, the runtime source), so an owner lane flipping its own flag never turns a
foundation test red.
"""

from __future__ import annotations

import importlib.util
import json
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import golden
from fastapi import FastAPI
from golden import UnverifiedParityWarning, assert_parity
from sharpit import install
from sharpit.engine import panels04, sqla, tools
from sharpit.engine.panels import PANELS
from sharpit.settings import load_settings

LOCAL = ("127.0.0.1", 50000)
CAPTURE_04 = ("transactions", "security-logs")
DISCOVERY_04 = ("postgresql", "mysql", "database-advisor", "sqlalchemy-statistics")
LEGACY_CAPTURE = ("http-exchanges", "exceptions", "sql-trace", "activity", "log-tail")
LEGACY_DISCOVERY = ("alembic", "database-connection-pools", "health", "sql-trace")
needs_sqlalchemy = pytest.mark.skipif(importlib.util.find_spec("sqlalchemy") is None, reason="needs SQLAlchemy")


def _flags(monkeypatch: pytest.MonkeyPatch, implemented: dict[str, bool]) -> None:
    for panel_id, value in implemented.items():
        monkeypatch.setitem(panels04.IMPLEMENTED, panel_id, value)


# --- finding 1: flag-flip-safe replacements ---------------------------------------------------------------------


@pytest.mark.parametrize("panel_id", sorted(panels04.PANEL_04_IDS))
@pytest.mark.parametrize("implemented", [False, True], ids=["flag-false", "flag-true"])
def test_panel_surface_follows_its_flag(monkeypatch: pytest.MonkeyPatch, panel_id: str, implemented: bool) -> None:
    _flags(monkeypatch, {panel_id: implemented})
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    listed = {panel["id"] for panel in client.get("/sharpit/api/panels").json()["panels"]}
    assert (panel_id in listed) is implemented
    if not implemented:
        assert client.get(f"/sharpit/api/{panel_id}").status_code == 404


@pytest.mark.parametrize("panel_id", sorted(panels04.PANEL_04_IDS))
@pytest.mark.parametrize("implemented", [False, True], ids=["flag-false", "flag-true"])
def test_panel_tools_follow_its_flag(monkeypatch: pytest.MonkeyPatch, panel_id: str, implemented: bool) -> None:
    from importlib import import_module

    module = import_module(f"sharpit.engine.tools04.{panel_id.replace('-', '_')}")
    planted = object()
    monkeypatch.setattr(module, "TOOLS", (planted,))
    monkeypatch.setattr(module, "COMMANDS", {f"get_{panel_id}_probe": f"{panel_id} probe"})
    _flags(monkeypatch, {panel_id: implemented})

    lane_tools, lane_commands = panels04.tool_definitions()

    assert (planted in lane_tools) is implemented
    assert (f"get_{panel_id}_probe" in lane_commands) is implemented


@pytest.mark.parametrize("panel_id", CAPTURE_04)
@pytest.mark.parametrize("implemented", [False, True], ids=["flag-false", "flag-true"])
def test_capture_middleware_follows_the_panel_flag(
    monkeypatch: pytest.MonkeyPatch, panel_id: str, implemented: bool
) -> None:
    _flags(monkeypatch, {**dict.fromkeys(CAPTURE_04, False), panel_id: implemented})
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, panels={p: {"enabled": False} for p in LEGACY_CAPTURE})
    wiring = handle.context.capture.wiring

    assert wiring is not None
    assert wiring.middleware_added is implemented


@pytest.mark.parametrize("panel_id", DISCOVERY_04)
@pytest.mark.parametrize("implemented", [False, True], ids=["flag-false", "flag-true"])
def test_engine_discovery_follows_the_panel_flag(
    monkeypatch: pytest.MonkeyPatch, panel_id: str, implemented: bool
) -> None:
    calls: list[tuple[bool, bool]] = []

    def add(_ctx: Any, *, statements: bool, discovery: bool) -> bool:
        calls.append((statements, discovery))
        return False

    monkeypatch.setattr(sqla, "add", add)
    _flags(monkeypatch, {**dict.fromkeys(DISCOVERY_04, False), panel_id: implemented})
    install(FastAPI(), enabled="ON", show_banner=False, panels={p: {"enabled": False} for p in LEGACY_DISCOVERY})

    assert calls
    assert calls[0] == (False, implemented)


def _settings_error(panels: dict[str, object]) -> str | None:
    try:
        load_settings({"panels": panels}, {})
    except ValueError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize("implemented", [False, True], ids=["flag-false", "flag-true"])
def test_panel_settings_follow_the_flag(monkeypatch: pytest.MonkeyPatch, implemented: bool) -> None:
    panel_id = "postgresql"
    _flags(monkeypatch, {panel_id: implemented})
    known = ", ".join(p.id for p in PANELS if panels04.IMPLEMENTED.get(p.id, True))

    error = _settings_error({panel_id: {"enabled": False}})

    if implemented:
        assert error is None
    else:
        assert error == f"Unknown sharpit panel(s): {panel_id}; known panels: {known}"


@pytest.mark.parametrize("implemented", [False, True], ids=["flag-false", "flag-true"])
def test_panel_env_for_an_unimplemented_panel_is_ignored(monkeypatch: pytest.MonkeyPatch, implemented: bool) -> None:
    # finding 7: SHARPIT_PANELS_<ID>_* for an unimplemented id is ignored like an unknown id (no warning)
    _flags(monkeypatch, {"postgresql": implemented})
    s = load_settings({}, {"SHARPIT_PANELS_POSTGRESQL_ENABLED": "garbage"})
    warned = any("SHARPIT_PANELS_POSTGRESQL_ENABLED" in w for w in s.warnings)
    assert warned is implemented


def test_sql_trace_modules_are_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    # replaces test_sql_trace_route_and_tool_modules_are_discovered: COMMANDS maps tool name -> CLI command path
    from sharpit.engine.tools04 import sql_trace as sql_trace_tools

    probe_tool = object()
    monkeypatch.setattr(sql_trace_tools, "TOOLS", (probe_tool,))
    monkeypatch.setattr(sql_trace_tools, "COMMANDS", {"get_sql_trace_insights": "sql-trace insights"})
    lane_tools, lane_commands = panels04.tool_definitions()
    assert probe_tool in lane_tools
    assert lane_commands.get("get_sql_trace_insights") == "sql-trace insights"


# --- finding 2: lane attachers re-arm across lifespan restarts; the slot says when SQLAlchemy is absent ---------


@needs_sqlalchemy
@pytest.mark.needs_sqlalchemy
def test_lane_attacher_survives_lifespan_restart() -> None:
    import sqlalchemy as sa

    engine = sa.create_engine("sqlite://")
    calls: list[int] = []

    def on_begin(conn: Any) -> None:
        calls.append(1)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    attachers: list[Callable[[], Callable[[], None] | None]] = getattr(handle.context.capture, "attachers", [])
    attachers.append(lambda: sqla.add_connection_listener("begin", on_begin))
    for _cycle in range(2):
        with TestClient(app), engine.begin() as conn:
            conn.execute(sa.text("select 1"))

    assert calls == [1, 1]
    assert sa.event.contains(sa.engine.Engine, "begin", on_begin) is False


def test_connection_listener_says_when_sqlalchemy_is_not_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqla, "sqlalchemy_module", lambda: None)
    assert sqla.add_connection_listener("begin", lambda *_: None) is None


@needs_sqlalchemy
@pytest.mark.needs_sqlalchemy
def test_lane_attacher_retries_after_a_late_sqlalchemy_import(monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlalchemy as sa

    real = sqla.sqlalchemy_module
    monkeypatch.setattr(sqla, "sqlalchemy_module", lambda: None)  # "not imported yet" at install time
    engine = sa.create_engine("sqlite://")
    calls: list[int] = []

    def on_begin(conn: Any) -> None:
        calls.append(1)

    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    attachers: list[Callable[[], Callable[[], None] | None]] = getattr(handle.context.capture, "attachers", [])
    attachers.append(lambda: sqla.add_connection_listener("begin", on_begin))
    handle.context.capture.wiring.on_startup(handle.context)  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
    monkeypatch.setattr(sqla, "sqlalchemy_module", real)  # the app imported SQLAlchemy later
    with TestClient(app), engine.begin() as conn:
        conn.execute(sa.text("select 1"))

    assert calls == [1]
    assert sa.event.contains(sa.engine.Engine, "begin", on_begin) is False


# --- the report-only and baseline options are real ----------------------------------------------------------------


def test_report_only_and_baseline_options_have_real_help(pytester: pytest.Pytester) -> None:
    out = " ".join(pytester.runpytest("--help").stdout.str().split())
    assert "--sharpit-report-only report findings without gating pytest" in out
    assert "--sharpit-baseline=PATH compare findings with a baseline file" in out
    assert "--sharpit-write-baseline" in out
    assert "write a baseline after a complete run" in out
    assert "reserved for 0.4.0" not in out


# --- finding 4: name-specific fixtures win over the shared ones --------------------------------------------------


def test_golden_loader_prefers_named_provisional_over_shared_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(golden, "ROOT", tmp_path)
    folder = tmp_path / "postgresql"
    folder.mkdir()
    (folder / "captured.json").write_text(json.dumps({"version": "16"}), encoding="utf-8")
    (folder / "sessions.provisional.json").write_text(json.dumps({"sessions": []}), encoding="utf-8")

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        try:
            assert_parity("postgresql", "sessions", {"sessions": []})
            error: str | None = None
        except AssertionError as exc:
            error = str(exc)

    assert error is None
    assert [w.category for w in seen] == [UnverifiedParityWarning]


# --- finding 5: a lane tool never shadows a base tool -----------------------------------------------------------


def _merge_error(lane_tools: tuple[Any, ...], lane_commands: dict[str, str]) -> str | None:
    try:
        tools.merge_lane_tools(tools.TOOLS, tools.COMMANDS, lane_tools, lane_commands)
    except ValueError as exc:
        return str(exc)
    return None


def test_lane_tool_colliding_with_a_base_tool_is_refused() -> None:
    clash = tools.TOOLS[0]
    assert _merge_error((clash,), {}) == f"lane tool name(s) collide with existing tools: {clash.name}"
    assert (
        _merge_error((), {"get_overview": "overview"}) == "lane CLI command(s) collide with existing ones: get_overview"
    )
    assert _merge_error((), {}) is None
