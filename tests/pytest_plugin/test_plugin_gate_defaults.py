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


def test_autodetect_ignores_test_module_apps(pytester: pytest.Pytester) -> None:
    package = pytester.path / "src" / "realpkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/items')\ndef items():\n    return []\n"
    )
    pytester.makepyfile(
        test_project="""
        import pathlib
        import sys
        sys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))
        from starlette.applications import Starlette
        import realpkg.main

        stub = Starlette()

        def test_uses_real_app():
            assert realpkg.main.app is not stub
        """
    )

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-report=report.json", "-q")

    assert "sharpit: using app realpkg.main:app (pass --sharpit-app to choose)" in result.stdout.str()


def test_autodetect_names_app_by_shortest_module_across_workers(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        short="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/items')
        def items():
            return []
        """,
        longer_reexport="""
        from short import app
        """,
        test_order="""
        import importlib
        import os

        def test_import_order_differs_per_worker():
            first, second = ('longer_reexport', 'short')
            if os.environ.get('PYTEST_XDIST_WORKER', 'gw0') != 'gw0':
                first, second = second, first
            importlib.import_module(first)
            assert importlib.import_module(second).app is not None
        """,
    )

    result = pytester.runpytest_subprocess("-n", "2", "--dist=each", "--sharpit", "--sharpit-report=report.json", "-q")

    assert "sharpit: using app short:app (pass --sharpit-app to choose)" in result.stdout.str()
    assert _rest_run(pytester)["status"] == "PASSED"
