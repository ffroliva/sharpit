"""Panel availability (spec §13.1 "available when" column): ``GET {api}/panels`` for every 0.2.0 panel.

Nothing here imports SQLAlchemy: the SQLAlchemy rows fake ``sys.modules``, so this runs in the no-sqlalchemy job too.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla

LOCAL = ("127.0.0.1", 50000)
INI = str(Path(__file__).resolve().parents[1] / "fixtures" / "alembic" / "linear" / "alembic.ini")
ONLY_EXCEPTIONS = {"panels": {p: {"enabled": False} for p in ("http-exchanges", "sql-trace", "activity", "log-tail")}}
NO_INI = (
    "No Alembic configuration: alembic.ini not found and no [tool.alembic] in pyproject.toml"  # tests run in the root
)
OLD = "SQLAlchemy 1.4.52 is imported, but sharpit needs 2.0 or later"

# (row id, panel, install options, sqlalchemy in sys.modules: "absent" | "old" | None (as is), expected reason)
ROWS: list[tuple[str, str, dict[str, Any], str | None, str | None]] = [
    ("activity", "activity", {}, None, None),
    ("http-exchanges", "http-exchanges", {}, None, None),
    ("exceptions", "exceptions", {}, None, None),
    ("exceptions-other-capture-off", "exceptions", ONLY_EXCEPTIONS, None, None),
    ("sql-trace-switched-off", "sql-trace", {"sql_trace_enabled": False}, None, sqla.TRACING_DISABLED),
    ("sql-trace-no-sqlalchemy", "sql-trace", {}, "absent", sqla.UNAVAILABLE),
    ("log-tail", "log-tail", {}, None, None),
    ("alembic-no-ini", "alembic", {}, None, NO_INI),
    ("alembic-ini", "alembic", {"alembic_config": INI}, "absent", None),  # reading files needs no SQLAlchemy (C4)
    ("pools-no-sqlalchemy", "database-connection-pools", {}, "absent", sqla.UNAVAILABLE),
    ("pools-old-sqlalchemy", "database-connection-pools", {}, "old", OLD),
    ("health", "health", {}, "absent", None),
    ("threads", "threads", {}, "absent", None),
    ("rest-api", "rest-api", {}, None, "Not built yet"),  # Task 10
    ("http-probe", "http-probe", {}, None, "Not built yet"),  # Task 11
]


@pytest.mark.parametrize(("panel", "options", "sqlalchemy", "reason"), [r[1:] for r in ROWS], ids=[r[0] for r in ROWS])
def test_panel_availability_0_2_0(
    monkeypatch: pytest.MonkeyPatch, panel: str, options: dict[str, Any], sqlalchemy: str | None, reason: str | None
):
    if sqlalchemy == "absent":
        monkeypatch.delitem(sys.modules, "sqlalchemy", raising=False)
    elif sqlalchemy == "old":
        old = types.ModuleType("sqlalchemy")
        old.__version__ = "1.4.52"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "sqlalchemy", old)
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, **options)
    try:
        body = TestClient(app, base_url="http://localhost", client=LOCAL).get("/sharpit/api/panels").json()
    finally:
        handle.uninstall_capture()
    row = next(p for p in body["panels"] if p["id"] == panel)
    assert (row["available"], row["unavailableReason"]) == (reason is None, reason)


def test_pools_availability_follows_sqlalchemy():
    # with SQLAlchemy as this process has it (imported or not): the panel says exactly what the bridge says
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    try:
        body = TestClient(app, base_url="http://localhost", client=LOCAL).get("/sharpit/api/panels").json()
    finally:
        handle.uninstall_capture()
    row = next(p for p in body["panels"] if p["id"] == "database-connection-pools")
    assert row["unavailableReason"] == sqla.unavailable_reason()
