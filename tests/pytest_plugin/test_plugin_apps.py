from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from sharpit import pytest_plugin


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


def test_plugin_loader_facade_remains_monkeypatchable(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.get("/ready")(lambda: {"ready": True})
    state = SimpleNamespace(
        options=SimpleNamespace(advisors=True, app="fake_app:app", fail_on="HIGH"),
        sink=SimpleNamespace(app_snapshots=lambda: [], facts=SimpleNamespace(advisor_runs=[])),
        dismissed=[],
    )
    monkeypatch.setattr(pytest_plugin, "_load_app", lambda spec: (spec, app))

    pytest_plugin._run_advisors(state)

    assert state.sink.facts.advisor_runs[0].status != "UNKNOWN"


def test_autodetect_accepts_fastapi_and_starlette_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    from starlette.applications import Starlette

    from fastapi import APIRouter, FastAPI
    from sharpit.fastapi.adapter import install
    from sharpit.pytest_plugin.apps import autodetect_apps

    class SubFastAPI(FastAPI):
        pass

    class Lookalike:
        router = object()
        routes: list[object] = []

    main_app = SubFastAPI()
    mounted_child = FastAPI()
    main_app.mount("/child", mounted_child)
    install(main_app, enabled="ON", show_banner=False)
    starlette_app = Starlette()

    mod = ModuleType("sample_autodetect_mod")
    mod.main_app = main_app  # type: ignore[attr-defined]
    mod.alias_app = main_app  # type: ignore[attr-defined]
    mod.mounted_child = mounted_child  # type: ignore[attr-defined]
    mod.starlette_app = starlette_app  # type: ignore[attr-defined]
    mod.router = APIRouter()  # type: ignore[attr-defined]
    mod.lookalike = Lookalike()  # type: ignore[attr-defined]
    mod.FastAPI = FastAPI  # type: ignore[attr-defined]
    mod.SubFastAPI = SubFastAPI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sample_autodetect_mod", mod)

    detected = dict(autodetect_apps())

    assert "sample_autodetect_mod:main_app" in detected
    assert detected["sample_autodetect_mod:main_app"] is main_app
    assert "sample_autodetect_mod:starlette_app" in detected
    assert detected["sample_autodetect_mod:starlette_app"] is starlette_app
    assert "sample_autodetect_mod:alias_app" not in detected
    assert "sample_autodetect_mod:mounted_child" not in detected
    assert "sample_autodetect_mod:router" not in detected
    assert "sample_autodetect_mod:lookalike" not in detected
    assert "sample_autodetect_mod:FastAPI" not in detected
    assert "sample_autodetect_mod:SubFastAPI" not in detected
