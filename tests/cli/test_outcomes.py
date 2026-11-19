"""CLI outcome and refusal confirmation tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sharpit.cli.client import ClientError, ToolResult
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.outcomes import OutcomeKind, classify, confirm_answered


class FakeClient:
    def __init__(self, catalog=None, error=None, token="secret-token"):
        self._catalog = catalog
        self._error = error
        self.options = SimpleNamespace(token=token)
        self.catalog_calls = 0

    def catalog(self):
        self.catalog_calls += 1
        if self._error:
            raise self._error
        return self._catalog


def result(status: int, payload=None) -> ToolResult:
    return ToolResult("security_scan", status, "", payload)


def test_foreign_403_is_an_error_not_a_refusal():
    # ported: CliContext.confirmBootUiAnswered
    client = FakeClient(catalog={"serverName": "other"})

    with pytest.raises(ClientError, match="not confirmed"):
        confirm_answered(client, result(403, {"error": "forbidden"}))


def test_503_is_disabled_only_when_sharpit_catalog_says_disabled():
    # ported: ToolOutcome.fromStatus
    disabled = confirm_answered(FakeClient(catalog={"serverName": "sharpit", "enabled": False}), result(503))
    outage = confirm_answered(FakeClient(catalog={"serverName": "sharpit", "enabled": True}), result(503))

    assert disabled.exit_code == ExitCodes.REFUSED
    assert disabled.kind is OutcomeKind.ENDPOINT_DISABLED
    assert outage.exit_code == ExitCodes.ERROR


def test_catalog_outage_does_not_confirm_a_503_refusal():
    # ported: CliContext.confirmBootUiAnswered
    with pytest.raises(ClientError, match="not confirmed"):
        confirm_answered(FakeClient(error=ClientError("unreachable")), result(503))


def test_read_only_panel_refusal_preserves_reason_without_token():
    # ported: BootUiClientTests.aToolIsReportedRefusedWhenItsPanelIsOffOrTheActionIsReadOnly
    reason = "This panel is read-only. secret-token"
    outcome = confirm_answered(
        FakeClient(catalog={"serverName": "sharpit", "enabled": True}),
        result(403, {"error": "sharpit panel access denied", "panel": "security", "reason": reason}),
    )

    assert outcome.exit_code == ExitCodes.REFUSED
    assert "sharpit panel access denied" in outcome.message
    assert reason.removesuffix(" secret-token") in outcome.message
    assert "secret-token" not in outcome.message
    assert "[redacted]" in outcome.message


@pytest.mark.parametrize(
    ("status", "kind", "exit_code"),
    [
        (200, OutcomeKind.SUCCESS, ExitCodes.SUCCESS),
        (400, OutcomeKind.INVALID_REQUEST, ExitCodes.ERROR),
        (401, OutcomeKind.UNAUTHENTICATED, ExitCodes.ERROR),
        (403, OutcomeKind.REFUSED_BY_POLICY, ExitCodes.REFUSED),
        (404, OutcomeKind.UNKNOWN_TOOL, ExitCodes.ERROR),
        (409, OutcomeKind.BUSY, ExitCodes.ERROR),
        (429, OutcomeKind.BUSY, ExitCodes.ERROR),
        (500, OutcomeKind.SERVER_ERROR, ExitCodes.ERROR),
        (503, OutcomeKind.SERVER_ERROR, ExitCodes.ERROR),
        (504, OutcomeKind.TIMED_OUT, ExitCodes.ERROR),
    ],
)
def test_http_status_maps_to_bootui_outcome(status, kind, exit_code):
    # ported: ToolOutcome.fromStatus
    outcome = classify(status, {})

    assert outcome.kind is kind
    assert outcome.exit_code == exit_code


def test_unknown_404_is_confirmed_only_by_sharpit_catalog():
    # ported: CliContext.confirmBootUiAnswered
    outcome = confirm_answered(FakeClient(catalog={"serverName": "sharpit", "enabled": True}), result(404))

    assert outcome.kind is OutcomeKind.UNKNOWN_TOOL
    assert outcome.exit_code == ExitCodes.ERROR


def test_refusal_message_redacts_token_in_server_body():
    # ported: BootUiClientTests.aToolIsReportedRefusedWhenItsPanelIsOffOrTheActionIsReadOnly
    outcome = confirm_answered(
        FakeClient(catalog={"serverName": "sharpit", "enabled": True}),
        result(
            403,
            {
                "error": "sharpit panel access denied",
                "panel": "security",
                "reason": "secret-token must not be printed",
            },
        ),
    )

    assert "secret-token" not in outcome.message
