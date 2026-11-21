"""The Flask observer: ``sharpit_http_observed(app)`` patches the exact app's ``wsgi_app`` (T1, Task 4)."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from fastapi import FastAPI
from sharpit.engine.advisors.http_security import HeaderExpectation, evaluate, normalize_route
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.pytest_plugin.http_security import observe_app
from sharpit.pytest_plugin.http_security_asgi import ObservedASGI
from sharpit.pytest_plugin.http_security_flask import observe_flask, route_of

NODE = "tests/test_items.py::test_list"
FRAME = HeaderExpectation("GET", "/items", "x-frame-options")
SECURE = ("--sharpit", "--sharpit-http-security", "--sharpit-required-response-header", "GET /items=X-Frame-Options")
INNER = ("--sharpit-allow-unknown",)


def _sink(*headers: HeaderExpectation) -> TestSessionSink:
    sink = TestSessionSink("gw0")
    sink.configure_http(headers, ())
    return sink


def _exchanges(sink: TestSessionSink, index: int = 0) -> dict[tuple[str, str, int, tuple[str, ...]], int]:
    return dict(sink.facts.tests[index].http.exchanges)


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    return app


def _flask_app() -> Any:
    flask = pytest.importorskip("flask")
    app = flask.Flask("t1")
    app.calls = []  # type: ignore[attr-defined]

    @app.get("/items")
    def items() -> Any:
        app.calls.append("items")  # type: ignore[attr-defined]
        return {"ok": True}

    @app.get("/items/<int:item_id>")
    def item(item_id: int) -> Any:
        return {"id": item_id}

    @app.get("/slash/")
    def slash() -> str:
        return "slash"

    @app.get("/boom")
    def boom() -> str:
        raise RuntimeError("view failed")

    return app


def test_http_security_flask_fixture_registers_exact_app_and_returns_same_app(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(flask_app="import flask\napp = flask.Flask('x')\n")
    pytester.makepyfile("""
        from flask_app import app

        def test_first(sharpit_http_observed):
            original = type(app).wsgi_app.__get__(app)
            assert sharpit_http_observed(app) is app
            assert "wsgi_app" in vars(app)
            assert app.wsgi_app != original

        def test_second_sees_the_original_again():
            assert "wsgi_app" not in vars(app)
    """)

    result = pytester.runpytest_subprocess(*SECURE, *INNER, "-p", "no:randomly")

    result.assert_outcomes(passed=2)


def test_http_security_observer_attributes_flask_request_to_test_attempt() -> None:
    app = _flask_app()
    sink = _sink(FRAME)
    restore = observe_flask(app, sink.on_http)
    sink.begin_test(NODE)

    response = app.test_client().get("/items", headers={"Authorization": "Bearer canary-token"})
    restore()

    assert response.status_code == 200
    assert _exchanges(sink) == {("GET", "/items", 200, ()): 1}


def test_http_security_shared_flask_app_remains_observable() -> None:
    app = _flask_app()
    sink = _sink(FRAME)

    for node in ("a.py::one", "a.py::two"):
        restore = observe_flask(app, sink.on_http)
        sink.begin_test(node)
        app.test_client().get("/items")
        sink.end_test()
        restore()

    assert [_exchanges(sink, i) for i in (0, 1)] == [{("GET", "/items", 200, ()): 1}] * 2
    assert "wsgi_app" not in vars(app)


def test_http_security_flask_route_match_does_not_execute_view() -> None:
    app = _flask_app()
    sink = _sink(FRAME)
    restore = observe_flask(app, sink.on_http)
    sink.begin_test(NODE)

    plain = _flask_app().test_client().get("/items")
    observed = app.test_client().get("/items")
    restore()

    assert app.calls == ["items"]  # type: ignore[attr-defined]
    assert _exchanges(sink) == {("GET", "/items", 200, ()): 1}
    assert (observed.status_code, observed.data) == (plain.status_code, plain.data)
    assert dict(observed.headers) == dict(plain.headers)


def test_http_security_flask_opaque_wrapper_reports_unknown() -> None:
    app = _flask_app()
    sink = _sink(FRAME)
    restores: list[Any] = []
    sink.begin_test(NODE)

    def opaque(environ: Any, start_response: Any) -> Any:  # a WSGI wrapper the observer cannot see into
        return app(environ, start_response)

    observed = observe_app(opaque, sink.on_http, restores)
    app.test_client().get("/items")

    run = evaluate((FRAME,), (), sink.facts.tests)
    assert observed is opaque
    assert restores == []
    assert run is not None
    assert run.status == "UNKNOWN"
    assert run.reason is not None
    assert "no matching exchange" in run.reason


def test_http_security_flask_restores_wsgi_app_after_exception() -> None:
    app = _flask_app()
    app.config["PROPAGATE_EXCEPTIONS"] = True
    sink = _sink(FRAME)
    restore = observe_flask(app, sink.on_http)
    sink.begin_test(NODE)

    try:
        client = app.test_client()
        client.get("/items")
        with pytest.raises(RuntimeError, match="view failed"):
            client.get("/boom")
    finally:
        restore()

    assert "wsgi_app" not in vars(app)
    assert app.test_client().get("/items").status_code == 200
    assert _exchanges(sink) == {("GET", "/items", 200, ()): 1}


def test_http_security_flask_mounted_script_name_matches_route() -> None:
    app = _flask_app()
    sink = _sink(FRAME)
    restore = observe_flask(app, sink.on_http)
    sink.begin_test(NODE)

    app.test_client().get("/items", environ_overrides={"SCRIPT_NAME": "/prefix"})
    restore()

    assert list(_exchanges(sink)) == [("GET", "/items", 200, ())]


def test_http_security_flask_matcher_outcomes_map_to_route_states() -> None:
    app = _flask_app()
    app.config["SERVER_NAME"] = "app.test"
    sink = _sink(FRAME)
    restore = observe_flask(app, sink.on_http)
    sink.begin_test(NODE)
    client = app.test_client()

    client.get("/nothing-here-secret-canary", base_url="http://app.test")
    client.get("/slash", base_url="http://app.test")  # a trailing-slash redirect
    client.post("/items", base_url="http://app.test")  # method not allowed
    restore()

    facts = sink.facts.tests[0].http
    assert facts.not_found == {"GET": 1}
    assert facts.unobservable == {"GET": 1, "POST": 1}
    assert facts.exchanges == {}
    assert "canary" not in str(facts.to_json())


def test_http_security_flask_matcher_failure_never_reaches_the_host() -> None:
    class Broken:
        class url_map:  # noqa: N801 - a stand-in whose matcher fails
            @staticmethod
            def bind_to_environ(*_args: Any, **_kwargs: Any) -> Any:
                raise ValueError("no matcher")

        config: dict[str, Any] = {}

    assert route_of(Broken, {"PATH_INFO": "/items", "REQUEST_METHOD": "GET"}) == ("unobservable", "")


def test_http_security_flask_observe_twice_patches_once() -> None:
    app = _flask_app()
    sink = _sink(FRAME)
    first = observe_flask(app, sink.on_http)
    patched = vars(app).get("wsgi_app")
    second = observe_flask(app, sink.on_http)
    sink.begin_test(NODE)

    app.test_client().get("/items")
    first()
    second()

    assert vars(app).get("wsgi_app") is None
    assert patched is not None
    assert _exchanges(sink) == {("GET", "/items", 200, ()): 1}


def test_http_security_route_templates_normalize_equally_across_adapters() -> None:
    sink = _sink(HeaderExpectation("GET", "/items/{item_id}", "x-a"))
    flask_app = _flask_app()
    restore = observe_flask(flask_app, sink.on_http)
    asgi = TestClient(ObservedASGI(_app(), sink.on_http))
    sink.begin_test(NODE)

    flask_app.test_client().get("/items/3")
    asgi.get("/items/3")
    restore()

    assert _exchanges(sink) == {("GET", "/items/{item_id}", 200, ()): 2}
    assert normalize_route("/a/<int(min=1):id>/<path:rest>/<name>/{x:int}") == "/a/{id}/{rest}/{name}/{x}"
