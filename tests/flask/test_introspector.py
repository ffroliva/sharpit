"""Behavioral contract for the Flask route adapter."""

from __future__ import annotations

import importlib
from importlib.metadata import version
from typing import Any

from werkzeug.routing import BaseConverter, Map
from werkzeug.routing import Rule as WerkzeugRule

from flask import Flask
from sharpit.engine.spi import AppInfo, RouteInfo
from sharpit.flask import FlaskIntrospector


def _introspector(app: Flask) -> FlaskIntrospector:
    return FlaskIntrospector(app)


def test_app_metadata_uses_flask_distribution_version() -> None:
    app = Flask("example", static_folder=None)
    app.config["DEBUG"] = True

    introspector = _introspector(app)

    assert introspector.app_info() == AppInfo("example", "Flask", version("flask"), None)


def test_empty_flask_app_has_no_routes() -> None:
    introspector = _introspector(Flask("empty", static_folder=None))

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

    assert introspector.routes() == [
        RouteInfo(
            ("GET", "HEAD", "OPTIONS"),
            "/items/{item_id}",
            f"{first.__module__}:{first.__qualname__}",
            None,
            None,
            None,
            "first",
        ),
        RouteInfo(
            ("OPTIONS", "POST"), "/second", f"{second.__module__}:{second.__qualname__}", None, None, None, "second"
        ),
    ]
    assert calls == []


def test_converters_render_as_route_parameters_and_preserve_slashes() -> None:
    app = Flask("converters", static_folder=None, subdomain_matching=True)

    def endpoint(**_values: object) -> str:
        return "ok"

    class CustomConverter(BaseConverter):
        regex = r"[a-z]+"

    app.url_map.converters["custom"] = CustomConverter
    app.add_url_rule("/path/<path:rest>", view_func=endpoint, endpoint="path")
    app.add_url_rule("/uuid/<uuid:record>", view_func=endpoint, endpoint="uuid")
    app.add_url_rule("/any/<any(red,blue):color>", view_func=endpoint, endpoint="any")
    app.add_url_rule("/custom/<custom:slug>/", view_func=endpoint, endpoint="custom", strict_slashes=False)
    app.add_url_rule("/tenant", view_func=endpoint, endpoint="tenant", subdomain="api")

    routes = _introspector(app).routes()

    assert [route.path for route in routes] == [
        "/path/{rest}",
        "/uuid/{record}",
        "/any/{color}",
        "/custom/{slug}/",
        "/tenant",
    ]
    assert routes[3].host is None
    assert routes[4].host is None


def test_static_and_duplicate_blueprint_routes_are_kept() -> None:
    app = Flask("blueprints")
    first = importlib.import_module(__name__)
    from flask import Blueprint

    one = Blueprint("one", first.__name__)
    two = Blueprint("two", first.__name__)

    @one.get("/same")
    def one_view() -> str:
        return "one"

    @two.get("/same")
    def two_view() -> str:
        return "two"

    app.register_blueprint(one, url_prefix="/one")
    app.register_blueprint(two, url_prefix="/two")

    routes = _introspector(app).routes()
    endpoints = [route.name for route in routes]

    assert endpoints == ["static", "one.one_view", "two.two_view"]
    assert [route.path for route in routes] == ["/static/{filename}", "/one/same", "/two/same"]


def test_malformed_url_map_is_unreadable() -> None:
    app = Flask("broken", static_folder=None)
    app.url_map = object()  # type: ignore[assignment]

    assert _introspector(app).routes() is None


def test_route_introspection_has_no_side_effects(no_side_effects: Any) -> None:
    app = Flask("safe", static_folder=None)

    def endpoint() -> str:
        return "ok"

    app.add_url_rule("/", view_func=endpoint)
    introspector = _introspector(app)

    introspector.app_info()
    introspector.routes()
    introspector.providers()
    no_side_effects.verify()


def test_routes_and_app_metadata_do_not_read_dynamic_flask_attributes() -> None:
    class RecordingFlask(Flask):
        accesses: list[str] = []

        def __getattribute__(self, name: str) -> object:
            if name != "accesses":
                object.__getattribute__(self, "accesses").append(name)
            return object.__getattribute__(self, name)

    app = RecordingFlask("safe-static", static_folder=None)
    RecordingFlask.accesses.clear()

    introspector = _introspector(app)
    introspector.routes()
    introspector.app_info()

    assert RecordingFlask.accesses == []


def test_routes_do_not_evaluate_rule_properties() -> None:
    accesses: list[str] = []

    class Rule(WerkzeugRule):
        def __init__(self) -> None:
            super().__init__("/unsafe", endpoint="unsafe")

        @property
        def methods(self) -> set[str]:
            accesses.append("methods")
            return {"GET"}

        @methods.setter
        def methods(self, value: set[str] | None) -> None:
            object.__setattr__(self, "_methods", value)

    app = Flask("unsafe-rule", static_folder=None)
    app.url_map = Map([Rule()])
    app.view_functions["unsafe"] = lambda: "unsafe"

    _introspector(app).routes()

    assert accesses == []


def test_callable_view_with_explicit_endpoint_is_kept_without_calling_it() -> None:
    class CallableView:
        calls = 0

        def __call__(self) -> str:
            CallableView.calls += 1
            return "called"

    app = Flask("callable-view", static_folder=None)
    app.add_url_rule("/callable", endpoint="callable", view_func=CallableView())

    routes = _introspector(app).routes()

    assert [route.path for route in routes or []] == ["/callable"]
    assert CallableView.calls == 0
