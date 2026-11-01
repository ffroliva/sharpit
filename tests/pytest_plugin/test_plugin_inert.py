from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def test_plugin_import_no_side_effects(tmp_path: Path) -> None:
    package_root = Path(__file__).resolve().parents[2] / "src"
    script = textwrap.dedent(
        """
        import json, logging, os, sqlite3, sys
        assert not any(name == "sharpit" or name.startswith("sharpit.") for name in sys.modules)
        before = {
            "connect": id(sqlite3.connect),
            "handlers": [id(handler) for handler in logging.root.handlers],
            "files": sorted(os.listdir(".")),
        }
        import sharpit.pytest_plugin
        after = {
            "connect": id(sqlite3.connect),
            "handlers": [id(handler) for handler in logging.root.handlers],
            "files": sorted(os.listdir(".")),
        }
        print(json.dumps([before, after]))
        """
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(package_root)!r});\n{script}"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    before, after = json.loads(result.stdout)
    assert after == before


def test_plain_run_untouched(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import logging
        import sqlite3
        from pathlib import Path
        from sharpit.engine.sqla import before_cursor_execute

        def test_plain():
            assert sqlite3.connect is sqlite3.dbapi2.connect
            assert not any(type(handler).__name__ == '_ExceptionHandler' for handler in logging.root.handlers)
            try:  # the no-sqlalchemy CI job runs this too
                from sqlalchemy import event
                from sqlalchemy.engine import Engine
            except ImportError:
                pass
            else:
                assert not event.contains(Engine, 'before_cursor_execute', before_cursor_execute)
            assert not Path('sharpit-report.json').exists()
        """
    )

    result = pytester.runpytest("-p", "no:cacheprovider", "-q")

    assert result.ret == 0


def test_inprocess_session_clears_global_state(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_inner(): pass")

    result = pytester.runpytest_inprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    from sharpit import pytest_plugin

    assert pytest_plugin._active_state is None


def test_nothing_assessed_unknown_fails_unless_allowed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")

    result = pytester.runpytest("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    assert '"status": "unknown"' in (pytester.path / "report.json").read_text()


def test_no_application_unknown_has_no_synthetic_app(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_empty(): pass")
    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")
    assert result.ret == 1, f"stdout: {result.stdout.str()}\nstderr: {result.stderr.str()}"
    data = json.loads((pytester.path / "report.json").read_text())
    assert (
        "advisor 'rest-api' could not assess: no application: pass --sharpit-app or call sharpit.install in the tests"
        in data["statusReasons"]
    )
    assert data["advisors"][0]["apps"] == []


def test_dismissal_store_built_once_per_session(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    from sharpit import pytest_plugin

    calls = 0
    original = pytest_plugin.DismissalStore

    def counted_store(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pytest_plugin, "DismissalStore", counted_store)
    pytester.makepyfile("def test_one(): pass\ndef test_two(): pass")
    result = pytester.runpytest_inprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    assert calls == 1


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
