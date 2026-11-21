"""The opt-in HTTP security observer: options, expectation parsing and the ``sharpit_http_observed`` fixture."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Mount
from starlette.testclient import TestClient

from fastapi import FastAPI, WebSocket
from sharpit.engine.advisors.http_security import HeaderExpectation, StatusExpectation, evaluate
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.pytest_plugin.http_security_asgi import ObservedASGI

HEADER = "--sharpit-required-response-header"
STATUS = "--sharpit-expected-status"


def _options(pytester: pytest.Pytester, *args: str) -> Any:
    """The resolved options, or None when pytest refuses the arguments (so a missing option is an assertion red)."""
    from sharpit.pytest_plugin.options import resolve

    try:
        return resolve(pytester.parseconfig(*args))
    except pytest.UsageError:
        return None


def _field(options: Any, name: str) -> Any:
    return getattr(options, name, None)


def _refused(pytester: pytest.Pytester, *args: str) -> str:
    result = pytester.runpytest(*args)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    return result.stderr.str()


def test_http_security_observer_disabled_by_default(pytester: pytest.Pytester) -> None:
    options = _options(pytester, "--sharpit")

    assert _field(options, "http_security_enabled") is False


def test_http_security_option_and_ini_expectations_resolve(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        sharpit_http_security = true
        sharpit_required_response_headers =
            GET /items=X-Content-Type-Options
        sharpit_expected_statuses =
            GET /items=200,304
    """)

    options = _options(pytester, "--sharpit")

    assert _field(options, "http_security_enabled") is True
    assert _field(options, "http_required_headers") == (("GET", "/items", "x-content-type-options"),)
    assert _field(options, "http_expected_statuses") == (("GET", "/items", (200, 304)),)


@pytest.mark.parametrize(
    ("option", "value", "shape"),
    [
        (HEADER, "GET /items", "METHOD ROUTE=HEADER"),
        (HEADER, "GET /items=", "METHOD ROUTE=HEADER"),
        (HEADER, "GET =X-A", "METHOD ROUTE=HEADER"),
        (HEADER, " /items=X-A", "METHOD ROUTE=HEADER"),
        (STATUS, "GET /items=ok", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=99", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=600", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=200,", "METHOD ROUTE=STATUS"),
        (STATUS, "GET /items=", "METHOD ROUTE=STATUS"),
    ],
)
def test_http_security_invalid_expectation_is_rejected(
    pytester: pytest.Pytester, option: str, value: str, shape: str
) -> None:
    stderr = _refused(pytester, "--sharpit", "--sharpit-http-security", option, value)

    assert f"expected {shape}" in stderr


def test_http_security_expected_status_set_accepts_any_listed_status(pytester: pytest.Pytester) -> None:
    options = _options(
        pytester, "--sharpit", "--sharpit-http-security", STATUS, "GET /a=404,200", STATUS, "GET /a=200,500"
    )

    assert _field(options, "http_expected_statuses") == (("GET", "/a", (200, 404, 500)),)


def test_http_security_method_is_case_normalized(pytester: pytest.Pytester) -> None:
    options = _options(pytester, "--sharpit", "--sharpit-http-security", HEADER, "get /a=X-A", STATUS, "pOsT /b=201")

    assert _field(options, "http_required_headers") == (("GET", "/a", "x-a"),)
    assert _field(options, "http_expected_statuses") == (("POST", "/b", (201,)),)


def test_http_security_expectations_require_enabled_observer(pytester: pytest.Pytester) -> None:
    stderr = _refused(pytester, "--sharpit", HEADER, "GET /a=X-A")

    assert "--sharpit-http-security" in stderr
    assert "unrecognized arguments" not in stderr


def test_http_security_observer_requires_sharpit(pytester: pytest.Pytester) -> None:
    stderr = _refused(pytester, "--sharpit-http-security")

    assert "requires --sharpit" in stderr


def test_http_security_cli_expectations_replace_ini(pytester: pytest.Pytester) -> None:
    pytester.makeini("""
        [pytest]
        sharpit_required_response_headers =
            GET /ini=X-Ini
        sharpit_expected_statuses =
            GET /ini=200
    """)

    options = _options(pytester, "--sharpit", "--sharpit-http-security", HEADER, "GET /cli=X-Cli")

    assert _field(options, "http_required_headers") == (("GET", "/cli", "x-cli"),)
    assert _field(options, "http_expected_statuses") == (("GET", "/ini", (200,)),)


def test_http_security_expectation_parsing_edge_cases(pytester: pytest.Pytester) -> None:
    options = _options(
        pytester,
        "--sharpit",
        "--sharpit-http-security",
        HEADER,
        "  get   /a=b,c = X-A  ",
        HEADER,
        "GET /a=b,c=x-a",
        HEADER,
        "GET /a=b,c=X-B",
        STATUS,
        "GET /a=b,c=200",
    )

    assert _field(options, "http_required_headers") == (("GET", "/a=b,c", "x-a"), ("GET", "/a=b,c", "x-b"))
    assert _field(options, "http_expected_statuses") == (("GET", "/a=b,c", (200,)),)


def test_http_security_fixture_is_listed_by_pytest_fixtures(pytester: pytest.Pytester) -> None:
    result = pytester.runpytest("--fixtures")

    assert "sharpit_http_observed" in result.stdout.str()


def test_http_security_fixture_off_state_is_identity(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        def test_identity(sharpit_http_observed):
            app = object()
            assert sharpit_http_observed(app) is app
    """)

    result = pytester.runpytest("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown")

    result.assert_outcomes(passed=1)


# --- Task 3: FastAPI and Starlette ASGI observation -------------------------------------------------------------

NODE = "tests/test_items.py::test_list"
FRAME = HeaderExpectation("GET", "/items", "x-frame-options")
SECURE = ("--sharpit", "--sharpit-http-security", HEADER, "GET /items=X-Frame-Options")
INNER = "--sharpit-no-advisors", "--sharpit-allow-unknown"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/items")
    def items() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    return app


def _sink(*headers: HeaderExpectation, statuses: tuple[StatusExpectation, ...] = ()) -> TestSessionSink:
    sink = TestSessionSink("gw0")
    sink.configure_http(headers, statuses)
    return sink


def _exchanges(sink: TestSessionSink, index: int = 0) -> dict[tuple[str, str, int, tuple[str, ...]], int]:
    return dict(sink.facts.tests[index].http.exchanges)


def test_http_security_observer_attributes_fastapi_request_to_test_attempt() -> None:
    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(_app(), sink.on_http))
    sink.begin_test(NODE)

    response = client.get("/items", headers={"Authorization": "Bearer canary-token"})

    assert response.status_code == 200
    assert _exchanges(sink) == {("GET", "/items", 200, ()): 1}


def test_http_security_portal_thread_request_is_attributed() -> None:
    app = _app()
    threads: list[int] = []

    @app.get("/who")
    def who() -> dict[str, bool]:
        threads.append(threading.get_ident())
        return {}

    sink = _sink(HeaderExpectation("GET", "/who", "x-a"))
    client = TestClient(ObservedASGI(app, sink.on_http))
    sink.begin_test(NODE)

    client.get("/who")

    assert threads
    assert threads[0] != threading.get_ident()
    assert list(_exchanges(sink)) == [("GET", "/who", 200, ())]


def test_http_security_observer_preserves_host_middleware_response() -> None:
    app = _app()

    class Stamp(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            response = await call_next(request)
            response.headers["X-Frame-Options"] = "DENY"
            return response

    app.add_middleware(Stamp)
    sink = _sink(FRAME)
    sink.begin_test(NODE)

    plain = TestClient(app).get("/items")
    observed = TestClient(ObservedASGI(app, sink.on_http)).get("/items")

    assert (observed.status_code, observed.content) == (plain.status_code, plain.content)
    assert dict(observed.headers) == dict(plain.headers)
    assert _exchanges(sink) == {("GET", "/items", 200, ("x-frame-options",)): 1}


def test_http_security_observer_excludes_sharpit_mount(restore_logging: None) -> None:
    import sharpit

    app = _app()
    sharpit.install(app, enabled="ON", show_banner=False)
    sink = _sink(FRAME, HeaderExpectation("GET", "/sharpit/api/info", "x-a"))
    client = TestClient(ObservedASGI(app, sink.on_http))
    sink.begin_test(NODE)

    client.get("/sharpit/api/info")
    client.get("/items")

    assert list(_exchanges(sink)) == [("GET", "/items", 200, ())]
    assert sink.facts.tests[0].http.unobservable == {}


def test_http_security_lifespan_and_websocket_pass_through() -> None:
    app = _app()
    events: list[str] = []

    @app.on_event("startup")
    def started() -> None:
        events.append("startup")

    @app.websocket("/ws")
    async def socket(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_text("hi")
        await ws.close()

    sink = _sink(FRAME)
    sink.begin_test(NODE)

    with TestClient(ObservedASGI(app, sink.on_http)) as client:
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_text() == "hi"
        client.get("/items")

    assert events == ["startup"]
    assert list(_exchanges(sink)) == [("GET", "/items", 200, ())]


def test_http_security_mounted_route_template_is_composed() -> None:
    inner = _app()
    outer = FastAPI()
    outer.mount("/api/v1", inner)
    child = FastAPI()
    child.add_api_route("/items/{item_id}", lambda item_id: {"id": item_id}, methods=["GET"])
    outer.router.routes.append(Mount("/tenants/{tenant}", app=child))
    sink = _sink(
        HeaderExpectation("GET", "/api/v1/items", "x-a"),
        HeaderExpectation("GET", "/tenants/{tenant}/items/{item_id}", "x-a"),
    )
    client = TestClient(ObservedASGI(outer, sink.on_http))
    sink.begin_test(NODE)

    client.get("/api/v1/items")
    client.get("/tenants/acme-secret/items/7")

    assert sorted(key[1] for key in _exchanges(sink)) == ["/api/v1/items", "/tenants/{tenant}/items/{item_id}"]


def test_http_security_missing_scope_route_is_unobservable_not_raw_path() -> None:
    async def opaque(scope: Any, receive: Any, send: Any) -> None:
        status = 404 if scope["path"].endswith("/gone") else 200
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(opaque, sink.on_http))
    sink.begin_test(NODE)

    client.get("/items?token=canary-secret")
    client.get("/secret-canary-path/gone")

    facts = sink.facts.tests[0].http
    assert facts.unobservable == {"GET": 1}
    assert facts.not_found == {"GET": 1}
    assert "canary" not in str(facts.to_json())


def test_http_security_observer_handles_request_outside_test_attempt() -> None:
    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(_app(), sink.on_http))

    assert client.get("/items").status_code == 200

    assert sink.facts.tests == []
    assert list(sink.facts.http_unassociated.exchanges) == [("GET", "/items", 200, ())]


def test_http_security_request_after_window_is_unassociated() -> None:
    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(_app(), sink.on_http))
    sink.begin_test(NODE)
    sink.end_test()

    client.get("/items")

    assert _exchanges(sink) == {}
    assert list(sink.facts.http_unassociated.exchanges) == [("GET", "/items", 200, ())]


def test_http_security_exchange_without_response_is_not_a_pass() -> None:
    async def broken(scope: Any, receive: Any, send: Any) -> None:
        raise RuntimeError("boom before any response")

    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(broken, sink.on_http), raise_server_exceptions=False)
    sink.begin_test(NODE)

    client.get("/items")

    assert _exchanges(sink) == {}
    assert sink.facts.tests[0].http.unobservable == {}
    assert evaluate((FRAME,), (), sink.facts.tests) is not None
    assert evaluate((FRAME,), (), sink.facts.tests).status == "UNKNOWN"  # type: ignore[union-attr]


def test_http_security_shared_wrapper_attributes_multiple_test_attempts() -> None:
    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(_app(), sink.on_http))

    for node in ("a.py::one", "a.py::two"):
        sink.begin_test(node)
        client.get("/items")
        sink.end_test()

    assert [_exchanges(sink, i) for i in (0, 1)] == [{("GET", "/items", 200, ()): 1}] * 2


def test_http_security_multiple_apps_observe_only_registered_app() -> None:
    sink = _sink(FRAME)
    watched, other = _app(), _app()
    watched_client = TestClient(ObservedASGI(watched, sink.on_http))
    other_client = TestClient(other)
    sink.begin_test(NODE)

    other_client.get("/items")
    other_client.get("/items")
    watched_client.get("/items")

    assert _exchanges(sink) == {("GET", "/items", 200, ()): 1}


def test_http_security_started_app_remains_observable() -> None:
    app = _app()
    sink = _sink(FRAME)
    sink.begin_test(NODE)
    with TestClient(app) as started:
        stack = app.middleware_stack
        started.get("/items")
        with TestClient(ObservedASGI(app, sink.on_http)) as client:
            client.get("/items")
        assert app.middleware_stack is stack

    assert _exchanges(sink) == {("GET", "/items", 200, ()): 1}


def test_http_security_asgi_wrapper_delegates_app_attributes() -> None:
    app = _app()
    wrapper = ObservedASGI(app, _sink(FRAME).on_http)

    assert wrapper.__wrapped__ is app
    assert wrapper.state is app.state  # type: ignore[attr-defined]
    assert wrapper.router is app.router  # type: ignore[attr-defined]
    assert wrapper.dependency_overrides is app.dependency_overrides  # type: ignore[attr-defined]


def test_http_security_rerun_only_deciding_attempt_counts() -> None:
    app = _app()
    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(app, sink.on_http))
    sink.begin_test(NODE)
    client.get("/items")
    sink.end_test()
    sink.begin_test(NODE)  # a rerun: the second attempt decides
    client.get("/items", headers={"x": "y"})
    sink.end_test()

    assert [t.key.attempt for t in sink.facts.tests] == [1, 2]
    assert evaluate((FRAME,), (), sink.facts.tests).findings != ()  # type: ignore[union-attr]
    assert len(evaluate((FRAME,), (), sink.facts.tests).findings) == 1  # type: ignore[union-attr]


def test_http_security_observer_unknown_when_app_or_route_unobservable() -> None:
    async def opaque(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sink = _sink(FRAME)
    client = TestClient(ObservedASGI(opaque, sink.on_http))
    sink.begin_test(NODE)
    client.get("/items")

    run = evaluate((FRAME,), (), sink.facts.tests)

    assert run is not None
    assert run.status == "UNKNOWN"
    assert run.reason is not None
    assert "evidence incomplete" in run.reason


_WIRING_APP = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/items")
def items():
    return {"ok": True}
"""


def test_http_security_fixture_factory_returns_observer(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=_WIRING_APP)
    pytester.makepyfile("""
        from app import app

        def test_wrapped(sharpit_http_observed):
            observed = sharpit_http_observed(app)
            assert observed is not app
            assert observed.__wrapped__ is app
            assert sharpit_http_observed(app) is observed
    """)

    result = pytester.runpytest_subprocess(*SECURE, *INNER)

    result.assert_outcomes(passed=1)


def test_http_security_fixture_off_returns_same_app(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=_WIRING_APP)
    pytester.makepyfile("""
        from app import app

        def test_identity(sharpit_http_observed):
            assert sharpit_http_observed(app) is app
    """)

    result = pytester.runpytest_subprocess("--sharpit", *INNER)

    result.assert_outcomes(passed=1)


_FACTS = """
def facts(request):
    from sharpit import pytest_plugin

    state = pytest_plugin._state(request.config)
    return dict(state.sink.current_test.http.exchanges)
"""


def test_http_security_function_fixture_traffic_belongs_to_attempt(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(app=_WIRING_APP, observed_facts=_FACTS)
    pytester.makepyfile("""
        import pytest
        from fastapi.testclient import TestClient

        from app import app
        from observed_facts import facts

        @pytest.fixture
        def client(sharpit_http_observed, request):
            client = TestClient(sharpit_http_observed(app))
            client.get("/items")
            yield client
            client.get("/items")
            assert facts(request) == {("GET", "/items", 200, ()): 3}

        def test_traffic(client, request):
            client.get("/items")
            assert facts(request) == {("GET", "/items", 200, ()): 2}
    """)

    result = pytester.runpytest_subprocess(*SECURE, *INNER)

    result.assert_outcomes(passed=1)
