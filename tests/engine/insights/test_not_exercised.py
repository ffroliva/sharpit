"""Declared route coverage (BootUI v2.5.0 NotExercisedRoutesTests)."""

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.collectors.insights.not_exercised import of
from sharpit.engine.spi import RouteInfo


def route(path="/uncalled", methods=("GET",), handler="app:endpoint"):
    return RouteInfo(methods, path, handler, None, None, None, None)


def service(journal=None, routes=None, **kwargs):
    return InsightsService(
        journal if journal is not None else RuntimeJournal(),
        [],
        declared_routes=lambda: routes if routes is not None else [route()],
        **kwargs,
    )


# ported: NotExercisedRoutesTests.listsDeclaredApplicationRoutesNoRequestReachedAndLeavesFrameworkRoutesOut
def test_lists_declared_application_routes_no_request_reached_and_leaves_framework_routes_out():
    journal = RuntimeJournal()
    journal.offer({"source": "http", "route": "PUT /ping", "requestId": "r1"})
    journal.offer({"source": "http", "route": "POST /graphql (query Products)", "requestId": "r2"})
    rows = [
        route("/ping", ()),
        route("/legacy", ()),
        route("/graphql", ("POST",)),
        route("/orders/{id:int}", ("DELETE", "GET")),
        route("/docs", handler="fastapi.applications:docs"),
    ]


def test_a_catch_all_websocket_and_opaque_rows_are_never_listed():
    rows = [
        route("/ws", ("WS",)),
        route("/all/{full_path:path}"),
        route("/web/*"),
        route("/api", (), "custom route"),
        route("/static/{path}", (), "app:opaque"),
        route("(any)", ()),
        route("/files/{path}"),
    ]
    assert of(rows, ()) == ["GET /files/{path}"]


def test_a_converter_route_that_was_called_is_not_listed():
    assert of([route("/items/{id:int}")], ["GET /items/{id:int}"]) == []


def test_duplicate_hosts_are_one_label():
    assert of([route(), route()], ()) == ["GET /uncalled"]
    assert service(journal, rows).report()["notExercised"] == [
        "ANY /legacy",
        "DELETE /orders/{id:int}",
        "GET /orders/{id:int}",
    ]
