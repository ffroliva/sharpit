"""A journal source is insights evidence only while its panel is enabled (BootUI ``InsightsSnapshot.available`` =
``records && visible``; ``JournalSourcePanels``). Each case installs sharpit with the panel off, seeds the journal and
reads the report through the production service."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.service import insights_service

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


@pytest.mark.parametrize(("source", "panel", "kind", "event"), CASES, ids=IDS)
def test_a_required_source_with_its_panel_enabled_is_evaluated(
    handles: list[Any], source: str, panel: str, kind: str, event: dict[str, Any]
) -> None:
    check = _check(_report(handles, event, **{panel: True}), kind)
    assert check["status"] != "NOT_APPLICABLE" or "disabled" not in str(check["reason"]), source


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
