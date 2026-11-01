from __future__ import annotations

from functools import partial

from starlette.testclient import TestClient as _TestClient

import sharpit.fastapi.adapter as adapter
import sharpit.fastapi.install as install_module
import sharpit.fastapi.routes as routes
import sharpit.pytest_plugin as plugin
import sharpit.pytest_plugin.options as options
import sharpit.pytest_plugin.session as session
from fastapi import FastAPI
from sharpit.fastapi.capture import CaptureWiring

TestClient = partial(_TestClient, client=("127.0.0.1", 50000), base_url="http://localhost")


def test_capture_setup_populates_installed_context() -> None:
    handle = adapter.install(FastAPI(), enabled="ON", show_banner=False)

    assert isinstance(handle.context.capture.wiring, CaptureWiring)


def test_install_facade_reexports_install_module_implementation() -> None:
    assert adapter.install is install_module.install


def test_adapter_install_uses_route_builder_module(monkeypatch) -> None:
    original = routes.build_routes
    called: list[bool] = []

    def observe(ctx, host_app):
        called.append(True)
        return original(ctx, host_app)

    monkeypatch.setattr(routes, "build_routes", observe)
    app = FastAPI()
    adapter.install(app, enabled="ON", show_banner=False)

    assert called == [True]


def test_unimplemented_route_builder_matches_installed_panel_surface() -> None:
    app = FastAPI()
    adapter.install(app, enabled="ON", show_banner=False)
    response = TestClient(app).get("/sharpit/api/panels")

    assert response.status_code == 200


def test_option_registration_is_owned_by_options_module() -> None:
    assert plugin.pytest_addoption is options.pytest_addoption


def test_gate_hook_is_owned_by_session_module() -> None:
    assert plugin.pytest_runtest_makereport is session.pytest_runtest_makereport
