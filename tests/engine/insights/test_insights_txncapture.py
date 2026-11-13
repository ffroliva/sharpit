"""Transaction capture state in the insights (owner ruling 2026-11-12: stricter than BootUI 2.3.0, whose insights do
not react to ``bootui.transactions.enabled=false``). Modelled on ``RuntimeInsightsService.sqlCapture`` (:975-1008)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.insights.finding import Evaluation
from sharpit.engine.collectors.insights.registry import KINDS
from sharpit.engine.collectors.insights.service import InsightsService, insights_service
from sharpit.engine.collectors.insights.txncapture import for_context

LOCAL = ("127.0.0.1", 50000)
OFF = "Transaction capture is disabled (SHARPIT_TRANSACTIONS_ENABLED=false), so no transaction is recorded."
CAVEAT = OFF + " Its transaction evidence is not counted."
REQUIRED = "needs-transaction"  # a kind that reads transaction (every real one is a stub until its lane lands)
OPTIONAL = "errors-behind-2xx"  # reads transaction optionally
_HTTP = {"source": "http", "requestId": "r1", "status": 200, "route": "GET /a", "routeTemplate": "/a"}
_EXC = {"source": "exception", "exceptionClass": "x.B", "requestId": "r1"}
_TXN = {"source": "transaction", "requestId": "r1"}


@dataclass(frozen=True)
class NeedsTransaction:
    kind: str = REQUIRED
    title: str = "Needs transaction"
    minimum_tier: str = "REQUEST_ID"
    reads: frozenset[str] = frozenset({"transaction"})
    optional_reads: frozenset[str] = frozenset()
    evaluate: object = field(default=lambda _snapshot: Evaluation(1, []))


def _seed(handle: Any) -> None:
    ctx = handle.context

    def panel_enabled(panel_id: str) -> bool:
        panel = ctx.settings.panels.get(panel_id)
        return panel is None or panel.enabled

    ctx.lazy(
        "runtime-insights",
        lambda: InsightsService(
            ctx.capture.journal, [NeedsTransaction(), *KINDS], 8000, panel_enabled, None, lambda: for_context(ctx)
        ),
    )


@pytest.fixture
def handles() -> Iterator[list[Any]]:
    opened: list[Any] = []
    yield opened
    for handle in opened:
        handle.uninstall_capture()


def _open(handles: list[Any], **options: Any) -> Any:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    handles.append(handle)
    _seed(handle)
    for event in (_HTTP, _EXC, _TXN):
        assert handle.context.capture.journal.offer(event)
    return app, handle


def _check(handles: list[Any], kind: str, **options: Any) -> dict[str, Any]:
    _, handle = _open(handles, **options)
    report = insights_service(handle.context).report()
    return next(c for c in report["checks"] if c["kind"] == kind)


def test_a_required_transaction_check_with_the_flag_off_is_unavailable(handles: list[Any]) -> None:
    check = _check(handles, REQUIRED, transactions_enabled=False)
    assert check["status"] == "UNAVAILABLE"
    assert check["reason"] == OFF


def test_an_optional_transaction_read_with_the_flag_off_carries_the_caveat(handles: list[Any]) -> None:
    check = _check(handles, OPTIONAL, transactions_enabled=False)
    assert check["status"] != "UNAVAILABLE"
    assert CAVEAT in str(check["reason"])


def test_the_panel_off_is_named_before_the_flag(handles: list[Any]) -> None:
    off = {"transactions_enabled": False, "panels": {"transactions": {"enabled": False}}}
    required = _check(handles, REQUIRED, **off)
    assert required["status"] == "NOT_APPLICABLE"
    assert required["reason"] == "The transactions panel, whose evidence this reads, is disabled."
    optional = _check(handles, OPTIONAL, **off)
    assert "The transactions panel is disabled, so its evidence is not counted." in str(optional["reason"])
    assert "SHARPIT_TRANSACTIONS_ENABLED" not in str(optional["reason"])


def test_the_flag_on_mentions_no_capture_state(handles: list[Any]) -> None:
    for kind in (REQUIRED, OPTIONAL):
        check = _check(handles, kind)
        assert "SHARPIT_TRANSACTIONS_ENABLED" not in str(check["reason"])
        assert check["status"] != "UNAVAILABLE"


def test_the_flag_on_report_is_byte_identical_to_a_service_without_the_supplier(handles: list[Any]) -> None:
    _, handle = _open(handles)
    ctx = handle.context
    with_supplier = insights_service(ctx).report()

    bare = InsightsService(ctx.capture.journal, [NeedsTransaction(), *KINDS], 8000, None).report()
    assert json.dumps(with_supplier, sort_keys=True) == json.dumps(bare, sort_keys=True)


def test_the_route_reports_the_flag_off_check(handles: list[Any]) -> None:
    app, _ = _open(handles, transactions_enabled=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)
    checks = client.get("/sharpit/api/runtime-insights").json()["checks"]
    check = next(c for c in checks if c["kind"] == REQUIRED)
    assert check["status"] == "UNAVAILABLE"
    assert check["reason"] == OFF
