from __future__ import annotations

from fastapi import FastAPI
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.fastapi.capture import CaptureWiring
from sharpit.fastapi.install import _configure_capture
from sharpit.fastapi.introspector import FastApiIntrospector
from sharpit.settings import load_settings


def test_configure_capture_attaches_wiring() -> None:
    app = FastAPI()
    settings = load_settings({"enabled": "ON"}, {})
    ctx = SharpitContext(settings, ActivationStatus(True, True, "enabled in test", ()), FastApiIntrospector(app))

    wiring = _configure_capture(app, ctx, settings)

    assert isinstance(wiring, CaptureWiring)


def test_configure_capture_stores_wiring_on_context() -> None:
    app = FastAPI()
    settings = load_settings({"enabled": "ON"}, {})
    ctx = SharpitContext(settings, ActivationStatus(True, True, "enabled in test", ()), FastApiIntrospector(app))

    _configure_capture(app, ctx, settings)

    assert ctx.capture.wiring is not None


def test_configure_capture_stores_returned_wiring() -> None:
    app = FastAPI()
    settings = load_settings({"enabled": "ON"}, {})
    ctx = SharpitContext(settings, ActivationStatus(True, True, "enabled in test", ()), FastApiIntrospector(app))

    wiring = _configure_capture(app, ctx, settings)

    assert ctx.capture.wiring is wiring
