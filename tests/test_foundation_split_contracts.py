from __future__ import annotations

from types import SimpleNamespace

from starlette.applications import Starlette
from starlette.routing import Route

from sharpit.engine.tool_registry import catalogue
from sharpit.engine.tools import TOOLS, Tool
from sharpit.fastapi.route_registry import register_routes
from sharpit.pytest_plugin.options import PluginOptions, resolve
from sharpit.pytest_plugin.session import resolve_options


def test_route_registration_preserves_order() -> None:
    first = Route("/first", lambda request: None)
    second = Route("/second", lambda request: None)
    app = Starlette()

    register_routes(app, (first, second))

    assert app.routes == [first, second]


def test_tool_catalogue_matches_registered_tools() -> None:
    catalog = catalogue()

    assert [tool.name for tool in catalog] == [tool.name for tool in TOOLS]


def test_plugin_session_options_match_resolver() -> None:
    config = SimpleNamespace(
        option=SimpleNamespace(
            sharpit=None,
            sharpit_report=None,
            sharpit_junit=None,
            sharpit_max_queries=None,
            sharpit_fail_on=None,
            sharpit_allow_unknown=None,
            sharpit_app=None,
            sharpit_advisors=None,
            sharpit_max_unattributed=None,
        ),
        getini=lambda name: {
            "sharpit": True,
            "sharpit_report": "pytest-session.json",
            "sharpit_junit": "pytest-session.xml",
            "sharpit_max_queries": 4,
            "sharpit_fail_on": "LOW",
            "sharpit_allow_unknown": True,
            "sharpit_app": "app:app",
            "sharpit_advisors": False,
            "sharpit_max_unattributed": 2,
        }[name],
    )

    expected: PluginOptions = resolve(config)
    actual = resolve_options(config)

    assert actual == expected
