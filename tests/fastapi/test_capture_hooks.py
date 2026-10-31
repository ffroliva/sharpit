"""Each capture hook of spec §6.1 is installed only when a panel that needs it is enabled.

Task 3 covers step 3 (the log handler); Tasks 4 and 5 add their hooks to the table.
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


def _log_handlers() -> list[logging.Handler]:
    loggers = [logging.root, *(lg for lg in logging.root.manager.loggerDict.values() if isinstance(lg, logging.Logger))]
    return [h for lg in loggers for h in lg.handlers if isinstance(h, SharpitLogHandler)]


def _log_handler_present(handle: SharpitHandle) -> bool:
    wiring = handle.context.capture.wiring
    own = wiring.log_handler if wiring is not None else None
    return own is not None and own in _log_handlers()


# (disabled panels, hook, probe run while the app is started)
HOOKS: list[tuple[tuple[str, ...], str, Callable[[SharpitHandle], bool]]] = [
    (("log-tail", "exceptions"), "log handler", _log_handler_present),
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
        assert _log_handlers() == before
    for panel in disabled:  # any one of the panels left enabled is enough to install the hook
        app, handle = _started(tuple(p for p in disabled if p != panel))
        with TestClient(app) as client:
            client.get("/host")
            assert present(handle), (hook, panel)
