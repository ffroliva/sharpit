from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from sharpit import pytest_plugin
from sharpit.engine.testsession.sink import report_masker


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
        sink=SimpleNamespace(app_snapshots=lambda: [], facts=SimpleNamespace(advisor_runs=[]), masker=report_masker()),
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


def test_autodetect_skips_installed_and_stdlib_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import sysconfig
    from pathlib import Path
    from types import ModuleType

    from fastapi import FastAPI
    from sharpit.pytest_plugin.apps import autodetect_apps

    for name, root in (("fake_dist_app_mod", "purelib"), ("fake_stdlib_app_mod", "stdlib")):
        mod = ModuleType(name)
        mod.__file__ = str(Path(sysconfig.get_paths()[root]) / f"{name}.py")
        mod.app = FastAPI()  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, mod)

    detected = dict(autodetect_apps())

    assert "fake_dist_app_mod:app" not in detected
    assert "fake_stdlib_app_mod:app" not in detected


def test_autodetect_drops_wrapped_host_and_subclassed_mounts(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    from starlette.middleware.gzip import GZipMiddleware
    from starlette.routing import Mount

    from fastapi import FastAPI
    from sharpit.pytest_plugin.apps import autodetect_apps

    class PrefixMount(Mount):
        pass

    main, gz_child, host_child, sub_child = FastAPI(), FastAPI(), FastAPI(), FastAPI()
    main.mount("/gz", GZipMiddleware(gz_child))
    main.host("api.example.com", host_child)
    main.router.routes.append(PrefixMount("/sub", app=sub_child))
    mod = ModuleType("mounted_children_mod")
    for name, app in (("main", main), ("gz_child", gz_child), ("host_child", host_child), ("sub_child", sub_child)):
        setattr(mod, name, app)
    monkeypatch.setitem(sys.modules, "mounted_children_mod", mod)

    detected = dict(autodetect_apps())

    assert "mounted_children_mod:main" in detected
    assert "mounted_children_mod:gz_child" not in detected
    assert "mounted_children_mod:host_child" not in detected
    assert "mounted_children_mod:sub_child" not in detected


def test_reconcile_keeps_a_skipped_run_that_is_not_a_placeholder() -> None:
    from types import SimpleNamespace

    from sharpit.engine.advisors.findings import AdvisorRun
    from sharpit.pytest_plugin.apps import reconcile_workers

    # another lane's SKIPPED run whose reason happens to read like an autodetect message
    run = AdvisorRun("rest-api", "SKIPPED", (), {}, "several apps found (x); rule errored", None)
    part = SimpleNamespace(advisor_runs=[run])

    reconcile_workers([part], ["pkg:app"], False)

    assert run in part.advisor_runs


def test_autodetect_matches_framework_classes_by_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    from sharpit.pytest_plugin.apps import autodetect_apps

    Fake = type("Starlette", (), {"__module__": "starlette.applications"})
    Fake.__qualname__ = "Starlette"
    mod = ModuleType("named_like_starlette_mod")
    mod.app = Fake()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "named_like_starlette_mod", mod)

    assert "named_like_starlette_mod:app" not in dict(autodetect_apps())


def test_autodetect_is_empty_without_starlette_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    from fastapi import FastAPI
    from sharpit.pytest_plugin.apps import autodetect_apps

    mod = ModuleType("no_framework_loaded_mod")
    mod.app = FastAPI()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "no_framework_loaded_mod", mod)
    monkeypatch.delitem(sys.modules, "starlette.applications")
    monkeypatch.delitem(sys.modules, "fastapi.applications")

    assert autodetect_apps() == ()


def test_autodetect_names_app_by_shortest_module(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType

    from fastapi import FastAPI
    from sharpit.pytest_plugin.apps import autodetect_apps

    app = FastAPI()
    for name in ("a_longer_reexport_mod", "short_mod"):  # the re-exporting module is loaded first
        mod = ModuleType(name)
        mod.app = app  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, mod)

    detected = dict(autodetect_apps())

    assert "short_mod:app" in detected
    assert "a_longer_reexport_mod:app" not in detected


def test_partial_app_assessment_exits_zero_with_warning(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        from starlette.applications import Starlette
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        sub = Starlette()
        app.mount("/mcp/messages", sub)
        @app.get("/items")
        def items(): return []
        install(app, show_banner=False)
        def test_snapshot():
            import sqlite3
            sqlite3.connect(":memory:").execute("SELECT 1").fetchone()
        """
    )

    result = pytester.runpytest("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 0
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "pass"
    assert not any(finding["severity"] == "high" for finding in data["findings"])
    assert "no SQL statement was executed" not in data["warnings"]
    run = next(r for r in data["advisors"] if r["advisor"] == "rest-api")
    assert run["status"] == "PARTIAL"
    assert "Mounted application at /mcp/messages has no inspectable routes." in data["warnings"]
    result.stdout.fnmatch_lines(["*warning: Mounted application at /mcp/messages has no inspectable routes.*"])


def test_partial_app_assessment_with_high_finding_fails(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        from starlette.applications import Starlette
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        sub = Starlette()
        app.mount("/mcp/messages", sub)
        @app.get("/items")
        def items1(): return []
        @app.get("/items")
        def items2(): return []
        install(app, show_banner=False)
        def test_snapshot(): pass
        """
    )

    result = pytester.runpytest("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "fail"
    run = next(r for r in data["advisors"] if r["advisor"] == "rest-api")
    assert run["status"] == "FAILED"


def test_lost_capture_still_exits_one(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from fastapi import FastAPI
        from sharpit.fastapi.adapter import install
        app = FastAPI()
        install(app, show_banner=False)
        def test_snapshot(): pass
        """
    )

    result = pytester.runpytest("--sharpit", "--sharpit-report=report.json", "-q")

    assert result.ret == 1
    data = json.loads((pytester.path / "report.json").read_text())
    assert data["status"] == "unknown"
