"""Flask app selection through the already-loaded module table."""

from __future__ import annotations

import builtins
import sys
from types import ModuleType
from typing import Any


def test_autodetect_finds_flask_without_importing_it(monkeypatch: Any) -> None:
    from sharpit.pytest_plugin.apps import autodetect_apps

    flask_app_module = ModuleType("flask.app")
    flask_type = type("Flask", (), {"__module__": "flask.app"})
    flask_app_module.Flask = flask_type  # type: ignore[attr-defined]
    host_module = ModuleType("flask_autodetect_host")
    host_module.app = flask_type()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "flask.app", flask_app_module)
    monkeypatch.setitem(sys.modules, "flask_autodetect_host", host_module)

    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        assert not name.startswith("flask")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    detected = dict(autodetect_apps())

    assert detected.get("flask_autodetect_host:app") is host_module.app


def test_autodetect_requires_a_unique_flask_app(monkeypatch: Any) -> None:
    from sharpit.pytest_plugin.apps import autodetect_apps, select_app

    flask_app_module = ModuleType("flask.app")
    flask_type = type("Flask", (), {"__module__": "flask.app"})
    flask_app_module.Flask = flask_type  # type: ignore[attr-defined]
    host_module = ModuleType("ambiguous_flask_host")
    host_module.one = flask_type()  # type: ignore[attr-defined]
    host_module.two = flask_type()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "flask.app", flask_app_module)
    monkeypatch.setitem(sys.modules, "ambiguous_flask_host", host_module)

    detected = autodetect_apps()

    assert len(detected) == 2
    assert select_app(detected) is None


def test_explicit_loader_keeps_flask_instances_and_calls_factories(monkeypatch: Any) -> None:
    from flask import Flask
    from sharpit.pytest_plugin.apps import load_app

    app = Flask("explicit", static_folder=None)
    module = ModuleType("explicit_flask_host")
    module.app = app  # type: ignore[attr-defined]
    module.create_app = lambda: app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "explicit_flask_host", module)

    try:
        loaded = load_app("explicit_flask_host:app")[1]
    except Exception:
        loaded = None

    assert loaded is app
    assert load_app("explicit_flask_host:create_app")[1] is app


def test_model_of_exposes_flask_routes_to_the_advisor() -> None:
    from flask import Flask
    from sharpit.pytest_plugin.apps import model_of

    app = Flask("model", static_folder=None)

    def ready() -> str:
        return "ready"

    app.add_url_rule("/ready", view_func=ready)
    try:
        model = model_of(app)
    except Exception:
        model = None

    assert model is not None
    assert [route.path for route in model.routes] == ["/ready"]


def test_malformed_autodetected_flask_map_is_unknown(pytester: Any) -> None:
    import json

    pytester.makepyfile(
        appmod="""
        from flask import Flask
        app = Flask('broken', static_folder=None)
        app.url_map = object()
        """
    )
    pytester.makepyfile("import appmod\ndef test_empty(): pass")

    pytester.runpytest(
        "--sharpit",
        "--sharpit-require-app",
        "--sharpit-allow-unknown",
        "--sharpit-report=report.json",
        "-q",
    )

    report = json.loads((pytester.path / "report.json").read_text())
    run = next(item for item in report["advisors"] if item["advisor"] == "rest-api")

    assert run["status"] == "UNKNOWN"
    assert run["reason"] == "application routes cannot be inspected (Flask URL map)"
