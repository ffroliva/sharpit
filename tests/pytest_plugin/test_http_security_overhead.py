"""HTTP security observer overhead budget (T1): one observed exchange, ASGI and WSGI, against the bare app.

"off" is the app called the same way without the observer, so the overhead is what the production wrappers add: the
response-start watcher, the route template (cached after the first request), the configured-header intersection and the
sink's locked record. Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a
failure: docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from tests.overhead import check_budget, paired

from sharpit.engine.advisors.http_security import HeaderExpectation
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.pytest_plugin.http_security_asgi import ObservedASGI
from sharpit.pytest_plugin.http_security_flask import observe_flask

ASGI_BUDGET_NS = 30_000
WSGI_BUDGET_NS = 150_000
ROUNDS, PER_ROUND = 60, 200
NODE = "tests/test_items.py::test_list"
EXPECTED = HeaderExpectation("GET", "/items/{item_id}", "x-frame-options")


async def _items(request: Any) -> JSONResponse:
    return JSONResponse({"id": request.path_params["item_id"]}, headers={"X-Frame-Options": "DENY"})


def _sink() -> TestSessionSink:
    sink = TestSessionSink("gw0")
    sink.configure_http((EXPECTED,), ())
    sink.begin_test(NODE)
    return sink


def _scope() -> dict[str, Any]:
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/items/7",
        "raw_path": b"/items/7",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"authorization", b"Bearer secret")],
        "client": ("127.0.0.1", 5000),
        "server": ("testserver", 80),
    }


async def _receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _discard(message: dict[str, Any]) -> None:
    del message


async def _calls(app: Callable[..., Any], count: int) -> None:
    for _ in range(count):
        await app(_scope(), _receive, _discard)


def test_http_security_observer_overhead_within_budget() -> None:
    sink = _sink()
    bare = Starlette(routes=[Route("/items/{item_id}", _items)])
    observed = ObservedASGI(bare, sink.on_http)

    def round_of(app: Callable[..., Any]) -> float:
        started = time.perf_counter_ns()
        asyncio.run(_calls(app, PER_ROUND))
        return (time.perf_counter_ns() - started) / PER_ROUND

    round_of(observed)  # the first request resolves and caches the route template
    result = paired(lambda: round_of(bare), lambda: round_of(observed), ROUNDS)

    assert sink.current_test is not None
    http = sink.current_test.http  # Starlette 0.44 leaves the route out of the scope: "unobservable", not "matched"
    assert sum(http.exchanges.values()) + sum(http.unobservable.values()) == (ROUNDS + 1) * PER_ROUND
    check_budget("HTTP security observer per observed ASGI exchange", result, ASGI_BUDGET_NS, "µs", 1000)


def test_http_security_observer_flask_overhead_within_budget() -> None:
    flask = pytest.importorskip("flask")
    from werkzeug.test import EnvironBuilder

    sink = _sink()
    app = flask.Flask("overhead")
    app.add_url_rule("/items/<int:item_id>", "item", lambda item_id: ("ok", 200, {"X-Frame-Options": "DENY"}))
    builder = EnvironBuilder("/items/7", headers={"Authorization": "Bearer secret"})
    original = app.wsgi_app

    def start_response(status: str, headers: list[tuple[str, str]], *rest: Any) -> None:
        del status, headers, rest

    def round_of(target: Callable[..., Any]) -> float:
        started = time.perf_counter_ns()
        for _ in range(PER_ROUND):
            target(builder.get_environ(), start_response)
        return (time.perf_counter_ns() - started) / PER_ROUND

    restore = observe_flask(app, sink.on_http)
    try:
        patched = app.wsgi_app
        round_of(patched)  # the first request builds the URL adapter's caches
        result = paired(lambda: round_of(original), lambda: round_of(patched), ROUNDS)
    finally:
        restore()

    assert sink.current_test is not None
    assert sum(sink.current_test.http.exchanges.values()) == (ROUNDS + 1) * PER_ROUND
    check_budget("HTTP security observer per observed WSGI exchange", result, WSGI_BUDGET_NS, "µs", 1000)
