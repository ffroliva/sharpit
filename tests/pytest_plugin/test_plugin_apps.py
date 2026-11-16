from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from fastapi import FastAPI
from sharpit import pytest_plugin
from sharpit.engine.testsession.sink import report_masker
from sharpit.fastapi.introspector import inspectable
from sharpit.pytest_plugin import apps


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

    result = pytester.runpytest(
        "--sharpit", "--sharpit-app=app:app", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    run = _rest_run(pytester)
    assert run["status"] != "UNKNOWN"
    assert run["apps"][0]["app"] == "app:app"
    assert "detectedFrom" not in run["apps"][0]["evidence"]  # named by the option, not found through imports
    assert "detected from" not in result.stdout.str()


def test_explicit_flask_app_with_unreadable_map_is_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        app="""
        from flask import Flask
        app = Flask('broken', static_folder=None)
        app.url_map = object()
        """
    )
    pytester.makepyfile("def test_empty(): pass")

    pytester.runpytest(
        "--sharpit", "--sharpit-app=app:app", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    run = _rest_run(pytester)
    assert run["status"] == "UNKNOWN"
    assert run["reason"] == "application routes cannot be inspected (Flask URL map)"


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


# --- --sharpit-app: an app whose routes cannot be inspected is unknown, never an empty pass (issue #75) -------------

_EXPECTED = "; expected an app, a router or a zero-argument factory"
_UNINSPECTABLE = f"application routes cannot be inspected (wsgiapp.Wsgi){_EXPECTED}"
_WSGI_APP = """
class Wsgi:  # shaped like a WSGI app: callable, two required arguments, no route list
    def __call__(self, environ, start_response):
        return []

app = Wsgi()

def create_app():
    return Wsgi()
"""


def _run_with_app(pytester: pytest.Pytester, spec: str, *extra: str) -> pytest.RunResult:
    pytester.makepyfile("def test_empty(): pass")
    return pytester.runpytest("--sharpit", f"--sharpit-app={spec}", "--sharpit-report=report.json", "-q", *extra)


def test_sharpit_app_instance_without_a_route_list_is_uninspectable(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(wsgiapp=_WSGI_APP)

    _run_with_app(pytester, "wsgiapp:app", "--sharpit-allow-unknown")

    run = _rest_run(pytester)
    assert run["status"] == "UNKNOWN"
    assert run["reason"] == _UNINSPECTABLE


def test_sharpit_app_factory_of_an_uninspectable_app_is_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(wsgiapp=_WSGI_APP)

    _run_with_app(pytester, "wsgiapp:create_app", "--sharpit-allow-unknown")

    run = _rest_run(pytester)
    assert run["status"] == "UNKNOWN"
    assert run["reason"] == _UNINSPECTABLE


def test_sharpit_app_uninspectable_app_fails_the_run_by_default(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(wsgiapp=_WSGI_APP)

    result = _run_with_app(pytester, "wsgiapp:create_app")

    assert result.ret == 1


def test_sharpit_app_uninspectable_app_is_tolerated_with_allow_unknown(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(wsgiapp=_WSGI_APP)

    result = _run_with_app(pytester, "wsgiapp:create_app", "--sharpit-allow-unknown")

    assert result.ret == 0


def test_sharpit_app_router_is_assessed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        routermod="""
        from fastapi import APIRouter
        router = APIRouter()
        @router.get('/owners')
        def owners(): return []
        """
    )

    _run_with_app(pytester, "routermod:router", "--sharpit-allow-unknown")

    run = _rest_run(pytester)
    assert run["status"] in ("PASSED", "FAILED")
    assert run["apps"][0]["app"] == "routermod:router"
    assert run["apps"][0]["evidence"]["usable"] is True


def test_sharpit_app_empty_fastapi_app_is_a_confirmed_empty_pass(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        emptyapp="""
        from fastapi import FastAPI
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        """
    )

    _run_with_app(pytester, "emptyapp:app")

    assert _rest_run(pytester)["status"] == "PASSED"


def test_sharpit_app_factory_of_a_fastapi_app_is_assessed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        factorymod="""
        from fastapi import FastAPI
        def create_app():
            app = FastAPI()
            @app.get('/owners')
            def owners(): return []
            return app
        """
    )

    _run_with_app(pytester, "factorymod:create_app", "--sharpit-allow-unknown")

    run = _rest_run(pytester)
    assert run["status"] in ("PASSED", "FAILED")
    assert run["apps"][0]["evidence"]["usable"] is True


def test_sharpit_app_factory_that_raises_keeps_the_load_error(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        brokenmod="""
        def create_app():
            raise RuntimeError("no database")
        """
    )

    _run_with_app(pytester, "brokenmod:create_app", "--sharpit-allow-unknown")

    run = _rest_run(pytester)
    assert run["status"] == "UNKNOWN"
    assert run["reason"] == "application could not load (RuntimeError)"


class _Recorder:
    """Accepts any call, zero arguments included, and counts it."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args: object) -> str:
        self.calls += 1
        return "called"


def _fake_module(monkeypatch: pytest.MonkeyPatch, **attrs: object) -> None:
    module = ModuleType("loadapp_fake")
    vars(module).update(attrs)
    monkeypatch.setitem(sys.modules, "loadapp_fake", module)


def test_load_app_never_calls_an_inspectable_object(monkeypatch: pytest.MonkeyPatch) -> None:
    container = _Recorder()
    vars(container)["routes"] = []
    _fake_module(monkeypatch, target=container)

    _, loaded = apps.load_app("loadapp_fake:target")

    assert container.calls == 0
    assert loaded is container


def test_load_app_never_calls_a_callable_with_an_unavailable_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    opaque = _Recorder()
    vars(opaque)["__signature__"] = "unavailable"  # inspect.signature raises TypeError on it
    _fake_module(monkeypatch, target=opaque)

    _, loaded = apps.load_app("loadapp_fake:target")

    assert opaque.calls == 0
    assert loaded is opaque


def test_load_app_returns_a_callable_that_needs_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    def needs_arguments(environ: object, start_response: object) -> list[bytes]:
        return []

    _fake_module(monkeypatch, target=needs_arguments)

    try:
        loaded: object = apps.load_app("loadapp_fake:target")[1]
    except TypeError:  # the loader tried to call it with no arguments
        loaded = None

    assert loaded is needs_arguments


def test_load_app_calls_a_factory_whose_arguments_are_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()

    def create_app(debug: bool = False, **settings: object) -> FastAPI:
        return app

    _fake_module(monkeypatch, target=create_app)

    assert apps.load_app("loadapp_fake:target")[1] is app


def test_load_app_never_calls_an_object_with_a_router_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy = _Recorder()  # not inspectable (no route list of its own), yet it carries a router like an app does
    vars(proxy)["router"] = None
    _fake_module(monkeypatch, target=proxy)

    _, loaded = apps.load_app("loadapp_fake:target")

    assert proxy.calls == 0
    assert loaded is proxy


def test_inspectable_is_false_for_a_class_that_holds_a_route_list() -> None:
    class Holder:
        routes: list[object] = []  # noqa: RUF012 - the class attribute is the point

    assert inspectable(Holder) is False


class _TaggingMasker:
    def mask_text(self, text: str) -> str:
        return f"masked<{text}>"

    def mask_path(self, text: str) -> str:
        return text


def _uninspectable_reason(target: object) -> str:
    state = SimpleNamespace(
        options=SimpleNamespace(advisors=True, app="fake_app:app", fail_on="HIGH"),
        sink=SimpleNamespace(app_snapshots=list, facts=SimpleNamespace(advisor_runs=[]), masker=_TaggingMasker()),
        dismissed=[],
    )

    apps._configured_models(state, lambda spec: (spec, target))

    runs = state.sink.facts.advisor_runs
    return str(runs[0].reason) if runs else ""  # no run: the app was taken as inspectable


def test_uninspectable_reason_passes_the_report_masker() -> None:
    reason = _uninspectable_reason(object())

    assert reason == f"masked<application routes cannot be inspected (builtins.object){_EXPECTED}>"


def test_uninspectable_reason_never_formats_a_host_module_object() -> None:
    class Loud:
        calls = 0

        def __str__(self) -> str:
            Loud.calls += 1
            return "loud"

    class Host:
        pass

    Host.__module__ = Loud()  # type: ignore[assignment]

    reason = _uninspectable_reason(Host())

    assert Loud.calls == 0
    assert "(?." in reason


@pytest.mark.skipif(sys.version_info < (3, 14), reason="deferred annotations (PEP 649) exist from Python 3.14")
def test_load_app_calls_a_factory_annotated_with_a_type_checking_only_name(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    namespace: dict[str, object] = {"made": app}
    source = "def create_app(settings: Settings | None = None):\n    return made\n"
    # dont_inherit: this file's `from __future__ import annotations` would turn the annotation into a string
    exec(compile(source, "hostmod.py", "exec", dont_inherit=True), namespace)  # noqa: S102 - a host module on 3.14
    _fake_module(monkeypatch, target=namespace["create_app"])

    try:
        loaded: object = apps.load_app("loadapp_fake:target")[1]
    except NameError:  # the loader evaluated the annotation instead of only binding arguments
        loaded = None

    assert loaded is app
