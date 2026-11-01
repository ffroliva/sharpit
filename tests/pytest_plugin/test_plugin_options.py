from __future__ import annotations

import json
from typing import Any

import pytest

pytest_plugins = ["pytester"]


def test_cli_wins_over_ini(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        sharpit = true
        sharpit_fail_on = MEDIUM
        sharpit_max_queries = 9
    """)
    pytester.makepyfile("def test_ok(): pass")

    result = pytester.runpytest(
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-fail-on=LOW",
        "--sharpit-max-queries=3",
        "--sharpit-report=report.json",
        "-q",
    )

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["gates"]["failOnSeverity"] == "LOW"
    assert data["gates"]["maxQueriesPerTest"] == 3


def test_options_resolve_defaults_and_ini(tmp_path) -> None:
    from sharpit.pytest_plugin.options import resolve

    class Config:
        option = type(
            "Options",
            (),
            {
                "sharpit": None,
                "sharpit_report": None,
                "sharpit_junit": None,
                "sharpit_max_queries": None,
                "sharpit_fail_on": None,
                "sharpit_allow_unknown": None,
                "sharpit_app": None,
                "sharpit_advisors": None,
                "sharpit_max_unattributed": None,
            },
        )()

        def getini(self, name):
            return {
                "sharpit": True,
                "sharpit_report": "out.json",
                "sharpit_junit": "out.xml",
                "sharpit_max_queries": 7,
                "sharpit_fail_on": "MEDIUM",
                "sharpit_allow_unknown": True,
                "sharpit_app": "app:app",
                "sharpit_advisors": False,
                "sharpit_max_unattributed": 20,
            }[name]

    options = resolve(Config())

    assert options.enabled is True
    assert options.report == tmp_path / "out.json" or options.report.name == "out.json"
    assert options.junit is not None
    assert options.max_queries == 7
    assert options.fail_on == "MEDIUM"
    assert options.allow_unknown is True
    assert options.app == "app:app"
    assert options.advisors is False
    assert options.max_unattributed == 20


def test_ini_types_exist_in_the_oldest_supported_pytest() -> None:
    # regression: type="int"/"float" are pytest 8.4+; pytest 8.0-8.3 assert at plugin load and crash every run
    from sharpit.pytest_plugin import pytest_addoption

    pytest_8_0_types = {None, "string", "paths", "pathlist", "args", "linelist", "bool"}
    types: dict[str, Any] = {}

    class Parser:
        def getgroup(self, name: str) -> Parser:
            return self

        def addoption(self, *args: Any, **kwargs: Any) -> None:
            pass

        def addini(self, name: str, help: str, type: Any = None, default: Any = None) -> None:  # noqa: A002
            types[name] = type

    pytest_addoption(Parser())
    assert {name: kind for name, kind in types.items() if kind not in pytest_8_0_types} == {}
