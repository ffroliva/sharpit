"""Each capture hook of spec §6.1 is installed only when a panel that needs it is enabled.

Task 3 covers step 3 (the log handler), Task 4 step 2 (the exception-handler wrappers); Task 5 adds its hooks.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.logtail import SharpitLogHandler
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


# (disabled panels, hook, probe run while the app is started)
HOOKS: list[tuple[tuple[str, ...], str, Callable[[SharpitHandle], bool]]] = [
    (("log-tail", "exceptions"), "log handler", _log_handler_present),
    (("exceptions",), "exception handlers", _handlers_wrapped),
]


def _started(disabled: tuple[str, ...]) -> tuple[FastAPI, SharpitHandle]:
    app = FastAPI()
    app.get("/host")(lambda: {})
    options: dict[str, Any] = {"panels": {p: {"enabled": False} for p in disabled}}
    return app, install(app, enabled="ON", show_banner=False, **options)


@pytest.mark.parametrize(("disabled", "hook", "present"), HOOKS, ids=[h[1] for h in HOOKS])
def test_disabled_panel_installs_no_hook(
    disabled: tuple[str, ...], hook: str, present: Callable[[SharpitHandle], bool]
):
    before = _log_handlers()
    app, handle = _started(disabled)
    with TestClient(app) as client:
        client.get("/host")
        assert not present(handle), hook
        if set(LOG_PANELS) <= set(disabled):  # no log panel left: no sharpit log handler anywhere
            assert _log_handlers() == before
    for panel in disabled:  # any one of the panels left enabled is enough to install the hook
        app, handle = _started(tuple(p for p in disabled if p != panel))
        with TestClient(app) as client:
            client.get("/host")
            assert present(handle), (hook, panel)
