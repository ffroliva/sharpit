"""Declared route coverage (BootUI v2.5.0 NotExercisedRoutesTests)."""

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.agent_view import Steps, agent_list
from sharpit.engine.collectors.insights.not_exercised import of
from sharpit.engine.collectors.insights.service import InsightsService
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

    assert service(journal, rows).report()["notExercised"] == [
        "ANY /legacy",
        "DELETE /orders/{id:int}",
        "GET /orders/{id:int}",
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


# ported: NotExercisedRoutesTests.noRouteIsListedAsNotExercisedWhileHttpExchangesIsHiddenOrHttpIsNotRecorded
def test_no_route_is_listed_while_http_is_not_recorded():
    report = service(RuntimeJournal(sources=["sql"])).report()
    assert report["notExercised"] == []
    assert report["limitations"] == [
        "The runtime journal does not record the http source (SHARPIT_RUNTIME_JOURNAL_SOURCES), "
        "so the routes no request reached are not listed."
    ]


# ported: NotExercisedRoutesTests.noRouteIsListedAsNotExercisedWhileHttpExchangesIsHiddenOrHttpIsNotRecorded
def test_no_route_is_listed_while_http_is_hidden():
    report = service(panel_enabled=lambda panel: panel != "http-exchanges").report()
    assert report["notExercised"] == []
    assert report["limitations"] == [
        "The http-exchanges panel is disabled, so the routes no request reached are not listed."
    ]
    assert agent_list(report, None, None, Steps({}))["notExercised"] == []


# ported: NotExercisedRoutesTests.droppedHttpOrAClearCannotProveDeclaredRoutesWereNotExercised
def test_dropped_http_or_a_clear_cannot_prove_declared_routes_were_not_exercised():
    for action in ("drop", "clear", "empty-clear"):
        journal = RuntimeJournal(max_bytes=200)
        if action == "drop":
            journal.offer({"source": "http", "route": "x" * 1000})
            reason = "The http source dropped completion events, so declared routes absent from its counts cannot be classified as not exercised."
        else:
            if action == "clear":
                journal.offer({"source": "http", "route": "GET /uncalled"})
            journal.discard()
            reason = "The recording was cleared during this run, so declared routes absent from the remaining counts cannot be classified as not exercised."
        report = service(journal).report()
        assert report["notExercised"] == []
        assert reason in report["limitations"]
        assert "clears" not in journal.status()
