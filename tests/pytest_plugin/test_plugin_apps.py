from __future__ import annotations

import json

import pytest


def _rest_run(pytester: pytest.Pytester) -> dict[str, object]:
    data = json.loads((pytester.path / "report.json").read_text())
    return next(run for run in data["advisors"] if run["advisor"] == "rest-api")


def test_include_router_after_install_seen(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from fastapi import APIRouter, FastAPI
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        install(app, show_banner=False)
        router = APIRouter()
        @router.get('/late')
        def late(): return {'ok': True}
        app.include_router(router)
        def test_snapshot(): pass
        """
    )

    pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    run = _rest_run(pytester)
    assert run["status"] != "UNKNOWN"


def test_inactive_install_still_snapshotted_only_with_plugin(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        @app.get('/ready')
        def ready(): return {'ok': True}
        handle = install(app, show_banner=False)
        assert handle.activation.enabled is False
        def test_snapshot(): pass
        """
    )

    pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    run = _rest_run(pytester)
    assert run["status"] != "UNKNOWN"


def test_installed_app_zero_routes_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        install(app, show_banner=False)
        def test_snapshot(): pass
        """
    )

    pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    run = _rest_run(pytester)
    assert run["status"] == "UNKNOWN"
    assert run["reason"] == "no routes seen after install"


def test_sharpit_app_option(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        app="""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get('/owners')
        def owners(): return []
        """
    )
    pytester.makepyfile("def test_empty(): pass")

    pytester.runpytest(
        "--sharpit", "--sharpit-app=app:app", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    run = _rest_run(pytester)
    assert run["status"] != "UNKNOWN"
    assert run["apps"][0]["app"] == "app:app"


def test_single_process_assesses_routes_added_after_the_last_test(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        """
        import pytest
        from fastapi import FastAPI
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        install(app, show_banner=False)
        def handler(): return 1
        @pytest.hookimpl(tryfirst=True)
        def pytest_sessionfinish(session):
            app.add_api_route('/items', handler, methods=['GET', 'POST'])
        """
    )
    pytester.makepyfile("def test_snapshot(): pass")

    pytester.runpytest("--sharpit", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q")

    data = json.loads((pytester.path / "report.json").read_text())
    assert any(finding["advisor"] == "rest-api" for finding in data["findings"])
