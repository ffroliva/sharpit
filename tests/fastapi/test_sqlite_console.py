"""The raw sqlite3 source in the console (spec 0.3.0 §8.4-8.6, hardening rows A1-A6).

Every case is derived: BootUI wraps a JDBC ``DataSource``, so there is no BootUI oracle for a driver swap.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from fastapi import FastAPI
from sharpit import attach_sql_sources, detach_sql_sources, install
from sharpit.engine import sqla, tools
from sharpit.engine.capture.sqltrace import MASK
from sharpit.engine.sources import dispatch, sqlite
from sharpit.fastapi.adapter import SharpitHandle

REAL_CONNECT = sqlite3.connect
_HANDLES: list[SharpitHandle] = []
SECRET = "sk_live_" + "a1b2c3d4e5f6a7b8c9d0"


@pytest.fixture(autouse=True)
def _clean_slate() -> Iterator[None]:
    sqla.detach_all()
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()
    detach_sql_sources()
    sqlite.detach_all()
    sqlite3.connect = REAL_CONNECT
    dispatch.set_session_sink(None)
    sqla.detach_all()


def _install(**options: Any) -> SharpitHandle:
    handle = install(FastAPI(), **{"enabled": "ON", "show_banner": False, **options})
    _HANDLES.append(handle)
    return handle


def test_console_shows_sqlite3_data_source():
    handle = _install()
    report = tools.sql_trace_report(handle.context)
    assert report["available"] is True
    assert "sqlite3" in report["dataSources"]
    connection = sqlite3.connect(":memory:")
    connection.execute("select 1")
    entries = tools.sql_trace_report(handle.context)["entries"]
    assert [e["sql"] for e in entries] == ["select ?"]
    connection.close()


def test_console_shows_early_connections_limitation():
    """A6: a connection opened before capture started is a displayed limit."""
    early = REAL_CONNECT(":memory:")
    handle = _install()
    report = tools.sql_trace_report(handle.context)
    assert sqlite.EARLY_CONNECTIONS in report["warnings"]
    early.close()


def test_console_positional_secret_masked_when_capture_on():
    """A4: a vendor token as a positional parameter is masked by its shape."""
    handle = _install(sql_trace_capture_parameters=True)
    connection = sqlite3.connect(":memory:")
    connection.execute("create table t (v text)")
    connection.execute("insert into t values (?)", (SECRET,))
    entries = tools.sql_trace_report(handle.context)["entries"]
    assert entries[0]["parameters"] == [MASK]
    assert SECRET not in str(entries)
    connection.close()


def test_third_party_call_site_shown_no_parameters(tmp_path: Path):
    """A3: another library's sqlite use is visible by call site, with no rows and no parameters."""
    package_dir = tmp_path / "site-packages"
    package_dir.mkdir()
    (package_dir / "cookie_reader.py").write_text("def read(c):\n    return c.execute('select ?', ('x',)).fetchall()\n")
    spec = importlib.util.spec_from_file_location("cookie_reader", package_dir / "cookie_reader.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handle = _install()
    connection = sqlite3.connect(":memory:")
    module.read(connection)
    entry = tools.sql_trace_report(handle.context)["entries"][0]
    assert entry["callSite"].startswith("test_sqlite_console:test_third_party_call_site_shown")
    assert entry["parameters"] == []
    connection.close()


def test_sqlite3_switch_off_keeps_stdlib():
    _install(sql_trace_sqlite3_enabled=False)
    assert sqlite3.connect is REAL_CONNECT
    assert sqlite.is_attached() is False


def test_inactive_install_leaves_stdlib():
    """A2: an inactive install attaches nothing."""
    _install(enabled="OFF")
    assert sqlite3.connect is REAL_CONNECT


def test_sql_trace_switch_off_keeps_stdlib():
    _install(sql_trace_enabled=False)
    assert sqlite3.connect is REAL_CONNECT


def test_attach_sql_sources_and_install_share_one_attachment():
    """Spec §8.5: ``attach_sql_sources()`` then ``install()`` is one patch, and the console leaving keeps it."""
    status = attach_sql_sources(enabled="ON")
    assert status.enabled is True
    patched = sqlite3.connect
    assert patched is not REAL_CONNECT
    handle = _install()
    assert sqlite3.connect is patched
    handle.uninstall_capture()
    assert sqlite3.connect is patched
    detach_sql_sources()
    assert sqlite3.connect is REAL_CONNECT


def test_detach_sql_sources_idempotent():
    detach_sql_sources()
    attach_sql_sources(enabled="ON")
    detach_sql_sources()
    detach_sql_sources()
    assert sqlite3.connect is REAL_CONNECT


def test_session_holder_survives_context_removal():
    """The plugin's attachment outlives an app's lifespan shutdown."""
    assert sqlite.attach("session") is True
    patched = sqlite3.connect
    handle = _install()
    handle.uninstall_capture()
    assert sqlite3.connect is patched
    assert sqlite.is_attached() is True
    sqlite.detach_all()
    assert sqlite3.connect is REAL_CONNECT


def test_attach_sql_sources_denied_under_prod_profile(monkeypatch: pytest.MonkeyPatch):
    """A1/A2: a production profile keeps sqlite3 stock; ``SHARPIT_ENABLED=ON`` enables it with the warning."""
    monkeypatch.setenv("APP_ENV", "production")
    status = attach_sql_sources()
    assert status.enabled is False
    assert sqlite3.connect is REAL_CONNECT
    forced = attach_sql_sources(enabled="ON")
    assert forced.enabled is True
    assert forced.warnings
    assert sqlite3.connect is not REAL_CONNECT


def test_attach_sql_sources_respects_both_switches():
    assert attach_sql_sources(enabled="ON", sql_trace_enabled=False).enabled is True
    assert sqlite3.connect is REAL_CONNECT
    assert attach_sql_sources(enabled="ON", sql_trace_sqlite3_enabled=False).enabled is True
    assert sqlite3.connect is REAL_CONNECT
