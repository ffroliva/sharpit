"""A journal source is insights evidence only while its panel is enabled (BootUI ``InsightsSnapshot.available`` =
``records && visible``; ``JournalSourcePanels``). Each case installs sharpit with the panel off, seeds the journal and
reads the report through the production service."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.service import insights_service
from sharpit.engine.collectors.insights.snapshot import SOURCE_PANELS
from sharpit.engine.panels import PANELS

# source, owning sharpit panel, a kind that requires the source, an event of that source
_HTTP = {"source": "http", "requestId": "r1", "status": 200, "route": "GET /a", "routeTemplate": "/a"}
_EXC = {"source": "exception", "exceptionClass": "x.B", "requestId": "r1"}
_LOG = {"source": "log", "logger": "org.hibernate.x", "level": "WARN", "template": "t", "requestId": "r1"}
CASES = [
    ("http", "http-exchanges", "errors-behind-2xx", _HTTP),
    ("sql", "sql-trace", "repeated-selects", {"source": "sql", "sql": "select ?", "requestId": "r1"}),
    ("exception", "exceptions", "exception-hotspots", _EXC),
    ("log", "log-tail", "framework-warnings-by-route", _LOG),
    ("transaction", "transactions", "transaction-across-remote-call", {"source": "transaction", "requestId": "r1"}),
]  # fmt: skip
IDS = [case[0] for case in CASES]


@pytest.fixture
def handles(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    monkeypatch.setattr(
        snapshot_module, "PRODUCED_SOURCES", frozenset(snapshot_module.PRODUCED_SOURCES | {"transaction"})
    )
    opened: list[Any] = []
    yield opened
    for handle in opened:
        handle.uninstall_capture()


def _report(handles: list[Any], event: dict[str, Any], **panels: bool) -> dict[str, Any]:
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False,
        panels={p: {"enabled": on} for p, on in panels.items()},
    )  # fmt: skip
    handles.append(handle)
    assert handle.context.capture.journal.offer(event)  # the journal records the source whatever the panel says
    return insights_service(handle.context).report()


def _check(report: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(c for c in report["checks"] if c["kind"] == kind)


# BootUI InsightsSnapshot.visible/available (v2.3.0 :418-430); RuntimeInsightsService.missingSource (:1342-1360)
@pytest.mark.parametrize(("source", "panel", "kind", "event"), CASES, ids=IDS)
def test_a_required_source_with_its_panel_disabled_is_not_applicable_naming_the_panel(
    handles: list[Any], source: str, panel: str, kind: str, event: dict[str, Any]
) -> None:
    check = _check(_report(handles, event, **{panel: False}), kind)
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == f"The {panel} panel, whose evidence this reads, is disabled."
    assert snapshot_module.SOURCE_PANELS[source] == (panel,)


def _same_as_default(handles: list[Any], events: list[dict[str, Any]], kind: str) -> None:
    """Every panel explicitly enabled changes nothing: the check and the observations equal the default install's."""
    out: list[dict[str, Any]] = []
    every = {panel.id: {"enabled": True} for panel in PANELS if panel.implemented}
    for panels in ({}, every):
        handle = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, panels=panels)
        handles.append(handle)
        for event in events:
            assert handle.context.capture.journal.offer(event)
        report = insights_service(handle.context).report()
        out.append(
            {"check": _check(report, kind), "observations": [o for o in report["observations"] if o["kind"] == kind]}
        )
    assert json.dumps(out[0], sort_keys=True) == json.dumps(out[1], sort_keys=True)
    assert out[0]["check"]["status"] != "NOT_APPLICABLE"


def test_enabling_every_panel_leaves_an_implemented_kind_unchanged(handles: list[Any]) -> None:
    _same_as_default(
        handles, [_HTTP, {**_HTTP, "requestId": "r2"}, {**_HTTP, "requestId": "r3"}, _EXC], "errors-behind-2xx"
    )


def test_every_source_panel_is_a_real_panel() -> None:
    known = {panel.id for panel in PANELS}
    assert {p for panels in SOURCE_PANELS.values() for p in panels} <= known


# RuntimeInsightsService.missingSource (v2.3.0 :1362-1368): hidden requests leave a kind that examines them nothing
@pytest.mark.parametrize(
    ("kind", "event"), [("ai-usage-by-route", {"source": "ai", "requestId": "r1"}), ("exception-hotspots", _EXC)]
)
def test_a_kind_that_reads_requests_with_the_http_panel_off_is_not_applicable_for_its_unit_of_work_evidence(
    handles: list[Any], kind: str, event: dict[str, Any]
) -> None:
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False, panels={"http-exchanges": {"enabled": False}}
    )
    handles.append(handle)
    assert handle.context.capture.journal.offer(_HTTP)
    assert handle.context.capture.journal.offer(event)
    check = _check(insights_service(handle.context).report(), kind)
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == "The http-exchanges panel is disabled, so its unit-of-work evidence cannot be evaluated."


@pytest.mark.parametrize("email_on", [True, False])
def test_mail_is_in_the_coverage_only_while_the_email_panel_is_enabled(handles: list[Any], email_on: bool) -> None:
    report = _report(handles, {"source": "mail", "requestId": "r1"}, email=email_on)
    assert ("mail" in [row["source"] for row in report["coverage"]]) is email_on


def test_an_optional_source_with_its_panel_disabled_is_a_caveat_naming_the_panel(handles: list[Any]) -> None:
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False, panels={"transactions": {"enabled": False}}
    )
    handles.append(handle)
    assert handle.context.capture.journal.offer(_HTTP)
    assert handle.context.capture.journal.offer(_EXC)
    check = _check(insights_service(handle.context).report(), "errors-behind-2xx")  # transaction is optional
    assert "The transactions panel is disabled, so its evidence is not counted." in str(check["reason"])


def test_errors_behind_2xx_with_log_tail_off_names_the_panel_for_the_log_evidence(handles: list[Any]) -> None:
    http = CASES[0][3]
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False,
        panels={"log-tail": {"enabled": False}, "exceptions": {"enabled": True}},
    )  # fmt: skip
    handles.append(handle)
    journal = handle.context.capture.journal
    assert journal.offer(http)
    assert journal.offer({"source": "log", "logger": "orders", "level": "ERROR", "template": "t", "requestId": "r1"})
    check = _check(insights_service(handle.context).report(), "errors-behind-2xx")
    assert "The log-tail panel is disabled, so its evidence is not counted." in str(check["reason"])


# A disabled capture flag leaves its panel unavailable (BootUI: the panel's beans are not created,
# BootUiAutoConfiguration :888-899), and InsightsSnapshot.visible needs the panel available AND enabled.
SQL_OFF = "SQL capture is disabled (SHARPIT_SQL_TRACE_ENABLED=false), so no statement is recorded."
TX_OFF = "Transactions are disabled via SHARPIT_TRANSACTIONS_ENABLED=false"
_SQL = {"source": "sql", "sql": "select ?", "requestId": "r1"}
_TX = {"source": "transaction", "requestId": "r1"}


def _flag_report(handles: list[Any], events: list[dict[str, Any]], **flags: bool) -> dict[str, Any]:
    handle = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, **flags)
    handles.append(handle)
    for event in events:
        assert handle.context.capture.journal.offer(event)
    return insights_service(handle.context).report()


@pytest.mark.parametrize(
    ("flag", "panel", "kind", "event", "why"),
    [
        ("sql_trace_enabled", "sql-trace", "safe-method-dml", _SQL, SQL_OFF),
        ("transactions_enabled", "transactions", "transaction-across-remote-call", _TX, TX_OFF),
    ],
    ids=["sql", "transaction"],
)
def test_a_required_source_whose_capture_flag_is_off_is_not_applicable_naming_the_flag(
    handles: list[Any], flag: str, panel: str, kind: str, event: dict[str, Any], why: str
) -> None:
    check = _check(_flag_report(handles, [event], **{flag: False}), kind)
    assert check["status"] == "NOT_APPLICABLE"
    assert (
        check["reason"] == f"The {panel} panel, whose evidence this reads, is not available in this application: {why}"
    )


@pytest.mark.parametrize(
    ("flag", "panel", "kind", "events", "why"),
    [
        ("sql_trace_enabled", "sql-trace", "route-time-breakdown", [_HTTP, _SQL], SQL_OFF),
        ("transactions_enabled", "transactions", "errors-behind-2xx", [_HTTP, _EXC], TX_OFF),
    ],
    ids=["sql", "transaction"],
)
def test_an_optional_source_whose_capture_flag_is_off_is_a_caveat_naming_the_flag(
    handles: list[Any], flag: str, panel: str, kind: str, events: list[dict[str, Any]], why: str
) -> None:
    check = _check(_flag_report(handles, events, **{flag: False}), kind)
    assert f"The {panel} panel is not available in this application, so its evidence is not counted: {why}" in str(
        check["reason"]
    )


@pytest.mark.parametrize("flag", ["sql_trace_enabled", "transactions_enabled"])
def test_capture_flags_on_add_no_unavailable_panel_text(handles: list[Any], flag: str) -> None:
    report = _flag_report(handles, [_HTTP, _SQL, _TX], **{flag: True})
    assert "not available in this application" not in json.dumps(report["checks"])
