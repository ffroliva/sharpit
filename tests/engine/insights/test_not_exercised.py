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
            reason = (
                "The http source dropped completion events, so declared routes absent "
                "from its counts cannot be classified as not exercised."
            )
        else:
            if action == "clear":
                journal.offer({"source": "http", "route": "GET /uncalled"})
            journal.discard()
            reason = (
                "The recording was cleared during this run, so declared routes absent "
                "from the remaining counts cannot be classified as not exercised."
            )
        report = service(journal).report()
        assert report["notExercised"] == []
        assert reason in report["limitations"]
        assert "clears" not in journal.status()


# ported: NotExercisedRoutesTests.theReportCountsEvictedRequestsThroughTheRunsAggregates
def test_an_evicted_event_lists_no_route():
    for source in ("http", "sql"):
        journal = RuntimeJournal(max_events=1)
        journal.offer({"source": source, "route": "GET /called"})
        journal.offer({"source": source, "route": "GET /other"})
        report = service(journal).report()
        assert report["notExercised"] == []
        assert (
            "The journal evicted events during this run, so declared routes cannot "
            "be classified as not exercised: this journal keeps no run-wide route counts."
        ) in report["limitations"]


def test_a_low_footprint_suspend_during_the_run_lists_no_route():
    journal = RuntimeJournal()
    journal.suspend()
    for resumed in (False, True):
        if resumed:
            journal.resume()
        report = service(journal).report()
        assert report["notExercised"] == []
        assert (
            "HTTP recording was suspended during this run, so declared routes cannot be classified as not exercised."
            in report["limitations"]
        )


# ported: NotExercisedRoutesTests.aRouteInventoryThatCannotBeReadIsSaidRatherThanListingNoRoute
def test_a_route_inventory_that_cannot_be_read_is_said_rather_than_listing_no_route():
    def boom():
        raise RuntimeError("private failure detail")

    for supplier in (lambda: None, boom):
        report = InsightsService(RuntimeJournal(), [], declared_routes=supplier).report()
        assert report["notExercised"] == []
        assert report["limitations"] == [
            (
                "The application's declared routes could not be read, so the routes no "
                "request reached are not listed: that does not mean every route was exercised."
            )
        ]
    assert service(routes=[]).report()["limitations"] == []
    assert InsightsService(RuntimeJournal(), []).report()["limitations"] == []


def test_inventory_is_read_only_for_the_report():
    calls = []

    def declared():
        calls.append(1)
        return [route()]

    subject = InsightsService(RuntimeJournal(), [], declared_routes=declared)
    subject.insight("unknown")
    assert calls == []
    subject.report()
    assert calls == [1]


def test_the_list_caps_at_100_and_counts_the_rest():
    report = service(routes=[route(f"/route/{i:03}") for i in range(101)]).report()
    assert len(report["notExercised"]) == 100
    assert report["notExercisedOmitted"] == 1
    assert report["notExercised"][0] == "GET /route/000"
    assert agent_list(report, None, None, Steps({}))["notExercisedOmitted"] == 93
    assert len(agent_list(report, None, None, Steps({}))["notExercised"]) == 8


def test_reading_the_report_with_declared_routes_has_no_side_effects(no_side_effects):
    journal = RuntimeJournal()
    before = journal.status()
    report = service(journal).report()
    assert report["notExercised"] == ["GET /uncalled"]
    assert journal.status() == before
    assert no_side_effects.violations == []


def test_metadata_only_exposure_lists_no_route_and_says_why():
    from sharpit.engine.masking import Exposure, Masker

    for recorded in (False, True):
        journal = RuntimeJournal(masker=Masker(Exposure.METADATA_ONLY, True))
        if recorded:
            journal.offer({"source": "http", "route": "GET /uncalled", "requestId": "r1"})
        report = service(journal).report()
        assert report["notExercised"] == []
        assert (
            "Request ids are withheld at METADATA_ONLY exposure, so declared routes "
            "cannot be classified as not exercised (SHARPIT_EXPOSE_VALUES)."
        ) in report["limitations"]


def test_a_called_secret_looking_route_is_listed_with_a_masking_limitation():
    secret_route = "/hooks/AKIAIOSFODNN7EXAMPLE"
    journal = RuntimeJournal()
    journal.offer({"source": "http", "route": f"GET {secret_route}", "requestId": "r1"})
    assert journal.records("http")[0]["route"] == "******"
    report = service(journal, [route(secret_route)]).report()
    assert report["notExercised"] == [f"GET {secret_route}"]
    assert (
        "Some captured route labels were masked, so routes listed as not exercised may have been reached."
        in report["limitations"]
    )


def test_an_unmatched_404_does_not_exercise_a_declared_route():
    journal = RuntimeJournal()
    journal.offer({"source": "http", "route": "GET /uncalled", "requestId": "r1", "status": 404, "routeTemplate": None})
    assert service(journal).report()["notExercised"] == ["GET /uncalled"]
