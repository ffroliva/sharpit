"""SQL Trace without SQLAlchemy (spec §6.2, §13.1): sharpit never imports it, and an old or absent one is unavailable.

These run in both CI jobs: nothing here imports SQLAlchemy at module level.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
import types
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import NEEDS_SQLALCHEMY_MISSING, sqlalchemy_imports_without_marker
from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.capture.sqltrace import REPORT_KEYS

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ("127.0.0.1", 50000)


def _client(app: Any) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)], cwd=ROOT, capture_output=True, text=True, timeout=60
    )


def _sql_panel(client: TestClient) -> dict[str, Any]:
    return next(p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "sql-trace")


def test_sqlalchemy_not_imported_after_install():
    done = _run(
        """
        import sys
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import sharpit

        app = FastAPI()
        app.get("/host")(lambda: {})
        sharpit.install(app, enabled="ON", show_banner=False, mcp_enabled="ON", cli_enabled=True)
        with TestClient(app) as client:
            client.get("/host")
            client.get("/sharpit/api/sql-trace")
            client.get("/sharpit/api/database-connection-pools/pools")
            client.get("/sharpit/api/panels")
            client.post("/sharpit/api/cli/tools/clear_sql_traces", json={})
        loaded = sorted(m for m in sys.modules if m.split(".")[0] in ("sqlalchemy", "aiosqlite", "alembic", "greenlet"))
        print(loaded)
        """
    )
    assert (done.returncode, done.stdout.strip()) == (0, "[]"), done.stderr


def test_sqlalchemy_blocked_reports_unavailable():
    # sys.modules["sqlalchemy"] = None is how CPython spells "not installed" to an import
    done = _run(
        """
        import json, sys
        sys.modules["sqlalchemy"] = None
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import sharpit

        app = FastAPI()
        handle = sharpit.install(app, enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False)
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            report = client.get("/sharpit/api/sql-trace").json()
            panel = [p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "sql-trace"][0]
        print(json.dumps([report["available"], report["unavailableReason"], panel["available"]]))
        """
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == '[false, "SQLAlchemy is not imported by this application", false]'


def test_old_sqlalchemy_unavailable(monkeypatch: pytest.MonkeyPatch):
    old = types.ModuleType("sqlalchemy")
    old.__version__ = "1.4.52"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sqlalchemy", old)
    assert sqla.sqlalchemy_module() is None
    old_reason = "SQLAlchemy 1.4.52 is imported, but sharpit needs 2.0 or later"
    assert sqla.unavailable_reason() == old_reason
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False)
    try:
        client = _client(app)
        assert (_sql_panel(client)["available"], _sql_panel(client)["unavailableReason"]) == (False, old_reason)
        report = client.get("/sharpit/api/sql-trace").json()
        assert tuple(report) == REPORT_KEYS
        assert report["unavailableReason"] == old_reason
        assert sqla.routed(handle.context) == (False, False)
    finally:
        handle.uninstall_capture()


@pytest.mark.skipif(importlib.util.find_spec("sqlalchemy") is not None, reason="runs in the no-sqlalchemy CI job")
def test_sqla_panels_empty_state_without_sqlalchemy():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False)
    try:
        client = _client(app)
        assert sqla.unavailable_reason() == "SQLAlchemy is not imported by this application"
        assert (_sql_panel(client)["available"], _sql_panel(client)["unavailableReason"]) == (False, sqla.UNAVAILABLE)
        report = client.get("/sharpit/api/sql-trace").json()
        assert (report["available"], report["entries"], report["dataSources"]) == (False, [], [])
        assert sqla.attached() == dict.fromkeys(sqla.attached(), False)
    finally:
        handle.uninstall_capture()


@pytest.mark.skipif(importlib.util.find_spec("sqlalchemy") is not None, reason="runs in the no-sqlalchemy CI job")
def test_sql_trace_available_through_sqlite3_without_sqlalchemy():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    try:
        client = _client(app)
        assert sqla.unavailable_reason() == sqla.UNAVAILABLE
        assert (_sql_panel(client)["available"], _sql_panel(client)["unavailableReason"]) == (True, None)
        assert client.get("/sharpit/api/sql-trace").json()["available"] is True
        assert sqla.attached() == dict.fromkeys(sqla.attached(), False)
    finally:
        handle.uninstall_capture()


@pytest.mark.skipif(importlib.util.find_spec("sqlalchemy") is not None, reason="runs in the no-sqlalchemy CI job")
def test_sqlalchemy_absent_empty_state():
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False)
    try:
        client = _client(app)
        report = client.get("/sharpit/api/database-connection-pools/pools").json()
        assert report == {"hikariPresent": False, "total": 0, "pools": []}
        panel = next(
            p for p in client.get("/sharpit/api/panels").json()["panels"] if p["id"] == "database-connection-pools"
        )
        assert (panel["available"], panel["unavailableReason"]) == (False, sqla.UNAVAILABLE)
    finally:
        handle.uninstall_capture()


@pytest.mark.parametrize(
    ("source", "found"),
    [
        ("import sqlalchemy as sa\n", ["sqlalchemy"]),
        ("from sqlalchemy.ext.asyncio import AsyncSession\n", ["sqlalchemy.ext.asyncio"]),
        ("import greenlet\nimport os\n", ["greenlet"]),
        ("import sqlalchemy\nimport pytest\npytestmark = pytest.mark.needs_sqlalchemy\n", []),
        ("import pytest\nsa = pytest.importorskip('sqlalchemy')\n", []),  # a skip, never an import error
        ("def f():\n    import sqlalchemy\n", []),  # lazy: imported only when the test runs
    ],
)
def test_collection_hook_requires_marker(source: str, found: list[str]):
    assert sqlalchemy_imports_without_marker(source) == found
    assert "needs_sqlalchemy" in NEEDS_SQLALCHEMY_MISSING
