"""Behavioral contract for the Flask route adapter."""

from __future__ import annotations

import importlib
from importlib.metadata import version
from typing import Any

from flask import Flask
from sharpit.engine.spi import AppInfo, RouteInfo


def _introspector(app: Flask) -> Any:
    try:
        module = importlib.import_module("sharpit.flask.introspector")
    except ModuleNotFoundError:
        return None
    adapter = getattr(module, "FlaskIntrospector", None)
    return adapter(app) if adapter is not None else None


def test_app_metadata_uses_flask_distribution_version() -> None:
    app = Flask("example", static_folder=None)
    app.config["DEBUG"] = True

    introspector = _introspector(app)

    assert introspector is not None
    assert introspector.app_info() == AppInfo("example", "Flask", version("flask"), None)


def test_empty_flask_app_has_no_routes() -> None:
    introspector = _introspector(Flask("empty", static_folder=None))

    assert introspector is not None
    assert introspector.routes() == []


def test_routes_keep_registration_order_and_endpoint_without_calling_views() -> None:
    app = Flask("routes", static_folder=None)
    calls: list[str] = []

    def first(item_id: int) -> str:
        calls.append("first")
        return str(item_id)

    def second() -> str:
        calls.append("second")
        return "second"

    app.add_url_rule("/items/<int:item_id>", view_func=first)
    app.add_url_rule("/second", view_func=second, methods=["POST"])

    introspector = _introspector(app)

    assert introspector is not None
    assert introspector.routes() == [
        RouteInfo(
            ("GET", "HEAD", "OPTIONS"),
            "/items/{item_id}",
            f"{first.__module__}.{first.__qualname__}",
            None,
            None,
            None,
            "first",
        ),
        RouteInfo(
            ("OPTIONS", "POST"), "/second", f"{second.__module__}.{second.__qualname__}", None, None, None, "second"
        ),
    ]
    assert calls == []
