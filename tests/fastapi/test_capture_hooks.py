"""Each capture hook of spec §6.1 is installed only when a panel that needs it is enabled.

Task 3 covers step 3 (the log handler), Task 4 step 2 (the exception-handler wrappers), Task 5 steps 4a (engine
discovery) and 4b (statement listeners).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.panels import panel_is_implemented
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import LOG_PANELS, WrappingHandlers


def _log_handlers() -> list[logging.Handler]:
    loggers = [logging.root, *(lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger))]
    return [h for lg in loggers for h in lg.handlers if isinstance(h, SharpitLogHandler)]


def _log_handler_present(handle: SharpitHandle) -> bool:
    wiring = handle.context.capture.wiring
    own = wiring.log_handler if wiring is not None else None
    return own is not None and own in _log_handlers()


def _handlers_wrapped(handle: SharpitHandle) -> bool:
    wiring = handle.context.capture.wiring
    return wiring is not None and isinstance(wiring.app.exception_handlers, WrappingHandlers)


def _sql_discovery(handle: SharpitHandle) -> bool:
    return sqla.routed(handle.context)[1] and sqla.attached()[sqla.DISCOVERY_EVENT]


def _sql_statements(handle: SharpitHandle) -> bool:
    return sqla.routed(handle.context)[0] and all(sqla.attached()[e] for e in sqla.STATEMENT_EVENTS)


# (disabled panels, hook, probe run while the app is started)
HOOKS: list[Any] = [
    (("log-tail", "exceptions"), "log handler", _log_handler_present),
    (("exceptions",), "exception handlers", _handlers_wrapped),
    pytest.param(sqla.DISCOVERY_PANELS, "sql discovery", _sql_discovery, marks=pytest.mark.needs_sqlalchemy),
    pytest.param(("sql-trace",), "sql statements", _sql_statements, marks=pytest.mark.needs_sqlalchemy),
]


def _started(disabled: tuple[str, ...]) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    app.get("/host")(lambda: {})
    options: dict[str, Any] = {"panels": {p: {"enabled": False} for p in disabled}}
    return app, install(app, enabled="ON", show_banner=False, **options)


@pytest.mark.parametrize(("disabled", "hook", "present"), HOOKS, ids=["log", "handlers", "sql-4a", "sql-4b"])
def test_disabled_panel_installs_no_hook(
    disabled: tuple[str, ...], hook: str, present: Callable[[SharpitHandle], bool]
):
    if hook.startswith("sql"):
        pytest.importorskip("sqlalchemy")  # imported before install(): the listeners attach at install
    before = _log_handlers()
    app, handle = _started(disabled)
    with TestClient(app) as client:
        client.get("/host")
        assert not present(handle), hook
        if set(LOG_PANELS) <= set(disabled):  # no log panel left: no sharpit log handler anywhere
            assert _log_handlers() == before
    for panel in disabled:  # any one of the panels left enabled is enough to install the hook
        if not panel_is_implemented(panel):
            continue
        app, handle = _started(tuple(p for p in disabled if p != panel))
        with TestClient(app) as client:
            client.get("/host")
            assert present(handle), (hook, panel)


def test_unimplemented_security_logs_does_not_add_capture_middleware() -> None:
    app = FastAPI()
    disabled = ("http-exchanges", "exceptions", "sql-trace", "activity", "log-tail")
    handle = install(app, enabled="ON", show_banner=False, panels={p: {"enabled": False} for p in disabled})
    wiring = handle.context.capture.wiring

    assert wiring is not None
    assert wiring.middleware_added is False


def test_unimplemented_database_panels_do_not_enable_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bool, bool]] = []

    def add(_ctx: Any, *, statements: bool, discovery: bool) -> bool:
        calls.append((statements, discovery))
        return False

    monkeypatch.setattr(sqla, "add", add)
    app = FastAPI()
    disabled = ("alembic", "database-connection-pools", "health", "sql-trace")
    install(app, enabled="ON", show_banner=False, panels={p: {"enabled": False} for p in disabled})

    assert calls
    assert calls[0] == (False, False)
