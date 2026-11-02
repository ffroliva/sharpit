from __future__ import annotations

import json

import pytest


def _rest_run(pytester: pytest.Pytester) -> dict[str, object]:
    data = json.loads((pytester.path / "report.json").read_text())
    return next(run for run in data["advisors"] if run["advisor"] == "rest-api")


def test_spike_f3_clean_suite_reaches_green(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import sqlite3

        def test_clean_query():
            conn = sqlite3.connect(':memory:')
            conn.execute('SELECT 1').fetchone()
        """
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 0
    stdout = result.stdout.str()
    assert "sharpit: no application found; rest-api skipped (pass --sharpit-app module:attr)" in stdout
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "pass"
    run = _rest_run(pytester)
    assert run["status"] == "SKIPPED"
    reason = str(run["reason"] or "")
    assert "--sharpit-app module:attr" in reason

    pytester.makepyfile(
        test_blind="""
        import sys, types
        sys.modules['asyncpg'] = types.ModuleType('asyncpg')
        def test_blind_driver():
            pass
        """
    )
    blind = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q", "test_blind.py")
    assert blind.ret == 1
    blind_data = json.loads((pytester.path / "report.json").read_text())
    assert blind_data["status"] == "unknown"


def test_autodetect_single_prints_choice(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/items')
        def items():
            return []
        """,
        test_single="""
        import appmod

        def test_uses_app():
            assert appmod.app is not None
        """,
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    stdout = result.stdout.str()
    assert "sharpit: using app appmod:app (pass --sharpit-app to choose)" in stdout
    assert result.ret == 0
    run = _rest_run(pytester)
    assert run["status"] == "PASSED"
    apps = run["apps"]
    assert isinstance(apps, list)
    assert apps[0]["app"] == "appmod:app"


def test_autodetect_ambiguous_uses_none(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        first_app="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/first')
        def first():
            return []
        """,
        second_app="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/second')
        def second():
            return []
        """,
        test_ambiguous="""
        import first_app
        import second_app

        def test_both_loaded():
            assert first_app.app is not second_app.app
        """,
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    stdout = result.stdout.str()
    assert "sharpit: several apps found (first_app:app, second_app:app); pass --sharpit-app module:attr" in stdout
    assert result.ret == 0
    run = _rest_run(pytester)
    assert run["status"] == "SKIPPED"
    assert run["apps"] == []


def test_autodetect_ambiguous_across_workers_uses_none(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        first_app="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/first')
        def first():
            return []
        """,
        second_app="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/second')
        def second():
            return []
        """,
        test_workers="""
        import importlib
        import os

        def test_worker_specific_app():
            worker = os.environ.get('PYTEST_XDIST_WORKER', 'gw0')
            mod = importlib.import_module('first_app' if worker == 'gw0' else 'second_app')
            assert mod.app is not None
        """,
    )

    result = pytester.runpytest_subprocess("-n", "2", "--dist=each", "--sharpit", "--sharpit-report=report.json", "-q")

    stdout = result.stdout.str()
    assert "sharpit: several apps found (first_app:app, second_app:app); pass --sharpit-app module:attr" in stdout
    assert result.ret == 0
    run = _rest_run(pytester)
    assert run["status"] == "SKIPPED"
    assert run["apps"] == []


def test_autodetect_never_imports(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        unimported_app="""
        from pathlib import Path
        Path('imported_boom.txt').write_text('imported')
        raise RuntimeError('unimported module must never be imported')
        """,
        loaded_app="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/ok')
        def ok():
            return {'ok': True}

        def __getattr__(name: str):
            raise RuntimeError(f'PEP 562 __getattr__ must never run: {name}')
        """,
        test_no_import="""
        import sys
        from types import ModuleType
        import loaded_app

        class CustomModule(ModuleType):
            def __getattribute__(self, name: str):
                if name != '__dict__':
                    raise RuntimeError('custom module subclass must be skipped')
                return super().__getattribute__(name)

        custom_mod = CustomModule('custom_mod_subclass')
        vars(custom_mod)['extra_app'] = loaded_app.FastAPI()
        sys.modules['custom_mod_subclass'] = custom_mod

        def test_loaded():
            assert loaded_app.app is not None
        """,
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q", "test_no_import.py")

    stdout = result.stdout.str()
    assert "sharpit: using app loaded_app:app (pass --sharpit-app to choose)" in stdout
    assert result.ret == 0
    assert not (pytester.path / "imported_boom.txt").exists()


_CLEAN_SUITE = """
import sqlite3

def test_clean_query():
    sqlite3.connect(':memory:').execute('SELECT 1').fetchone()
"""


def test_require_app_no_app_is_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(_CLEAN_SUITE)

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-require-app", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
    assert _rest_run(pytester)["status"] == "UNKNOWN"
    assert "rest-api skipped" not in result.stdout.str()


def test_require_app_ini_true_is_unknown(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        sharpit_require_app = true
    """)
    pytester.makepyfile(_CLEAN_SUITE)

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    assert _rest_run(pytester)["status"] == "UNKNOWN"


def test_worst_status_order() -> None:
    from sharpit.engine.testsession.outcome import _worst

    assert _worst(["PASSED", "SKIPPED"]) == "SKIPPED"
    assert _worst(["SKIPPED", "UNKNOWN"]) == "UNKNOWN"
    assert _worst(["UNKNOWN", "FAILED", "SKIPPED", "PASSED"]) == "FAILED"
    assert _worst(["PASSED"]) == "PASSED"


def test_explicit_app_ignores_autodetect_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    from sharpit.pytest_plugin.apps import select_app

    chosen_app, other_app = object(), object()
    mod = ModuleType("explicit_choice_mod")
    mod.app = chosen_app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "explicit_choice_mod", mod)

    selected = select_app("explicit_choice_mod:app", [("other_mod:app", other_app)])

    assert selected is not None
    assert selected[0] == "explicit_choice_mod:app"
    assert selected[1] is chosen_app


def test_autodetected_app_without_routes_is_skipped(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        appmod="""
        from fastapi import FastAPI
        app = FastAPI()
        """,
        test_bare="""
        import appmod

        def test_uses_app():
            assert appmod.app is not None
        """,
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")
    run = _rest_run(pytester)
    required = pytester.runpytest_subprocess("--sharpit", "--sharpit-require-app", "--sharpit-report=report.json", "-q")

    assert result.ret == 0
    assert run["status"] == "SKIPPED"
    assert "no routes seen after install" not in str(run["reason"])
    assert "appmod:app" in str(run["reason"])
    assert required.ret == 1
