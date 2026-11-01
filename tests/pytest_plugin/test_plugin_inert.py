from __future__ import annotations

import importlib

import pytest


def test_plugin_import_no_side_effects(no_side_effects: object) -> None:
    importlib.import_module("sharpit.pytest_plugin")


def test_plain_run_untouched(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import logging
        import sqlite3
        from pathlib import Path
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        from sharpit.engine.sqla import before_cursor_execute

        def test_plain():
            assert sqlite3.connect is sqlite3.dbapi2.connect
            assert not any(type(handler).__name__ == '_ExceptionHandler' for handler in logging.root.handlers)
            assert not event.contains(Engine, 'before_cursor_execute', before_cursor_execute)
            assert not Path('sharpit-report.json').exists()
        """
    )

    result = pytester.runpytest("-p", "no:cacheprovider", "-q")

    assert result.ret == 0


def test_nothing_assessed_unknown_fails_unless_allowed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")

    result = pytester.runpytest("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    assert '"status": "unknown"' in (pytester.path / "report.json").read_text()


def test_allow_unknown_exits_zero(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")

    result = pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    assert result.ret == 0
    assert '"status": "unknown"' in (pytester.path / "report.json").read_text()


@pytest.mark.parametrize(
    ("variable", "value", "reason"),
    [
        ("APP_ENV", "production", "active profile 'production'"),
        ("SHARPIT_ENABLED", "OFF", "SHARPIT_ENABLED=OFF"),
        ("SHARPIT_ENABLED", "not-a-mode", "invalid SHARPIT_ENABLED"),
    ],
)
def test_activation_refuses_unsafe_configuration(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, variable: str, value: str, reason: str
) -> None:
    pytester.makepyfile("def test_empty(): pass")
    monkeypatch.setenv(variable, value)

    result = pytester.runpytest("--sharpit", "-q")

    assert result.ret == 4
    assert reason in result.stderr.str()


def test_enabled_on_overrides_disabled_profile_with_warning(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makepyfile("def test_empty(): pass")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SHARPIT_ENABLED", "ON")

    result = pytester.runpytest("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q")

    assert result.ret == 0
    assert "forces it on" in result.stdout.str()
