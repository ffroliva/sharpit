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
        catalog = self._catalog
        if (
            not isinstance(catalog, dict)
            or catalog.get("serverName") != "sharpit"
            or not isinstance(catalog.get("enabled"), bool)
            or not isinstance(catalog.get("tools"), list)
            or (not catalog["enabled"] and catalog["tools"])
        ):
            raise ClientError("Response is not a sharpit catalog")
        return self._catalog


def result(status: int, payload=None) -> ToolResult:
    return ToolResult("security_scan", status, "", payload)


def test_foreign_403_is_an_error_not_a_refusal():
    # ported: CliContext.confirmBootUiAnswered
    client = FakeClient(catalog={"serverName": "other"})
    answer = result(403, {"error": "forbidden"})

    with pytest.raises(ClientError, match="not a sharpit policy refusal"):
        confirm_answered(client, answer)


def test_503_is_disabled_only_when_sharpit_catalog_says_disabled():
    # ported: ToolOutcome.fromStatus
    disabled = confirm_answered(
        FakeClient(catalog={"serverName": "sharpit", "enabled": False, "tools": []}), result(503)
    )
    outage = confirm_answered(FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []}), result(503))

    assert disabled.exit_code == ExitCodes.REFUSED
    assert disabled.kind is OutcomeKind.ENDPOINT_DISABLED
    assert outage.exit_code == ExitCodes.ERROR


def test_catalog_outage_does_not_confirm_a_503_refusal():
    # ported: CliContext.confirmBootUiAnswered
    client, answer = FakeClient(error=ClientError("unreachable")), result(503)
    with pytest.raises(ClientError, match="503"):
        confirm_answered(client, answer)


def test_read_only_panel_refusal_preserves_reason_without_token():
    # ported: BootUiClientTests.aToolIsReportedRefusedWhenItsPanelIsOffOrTheActionIsReadOnly
    reason = "This panel is read-only. secret-token"
    outcome = confirm_answered(
        FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []}),
        result(403, {"error": "sharpit panel access denied", "reason": reason}),
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
    outcome = confirm_answered(FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []}), result(404))

    assert outcome.kind is OutcomeKind.UNKNOWN_TOOL
    assert outcome.exit_code == ExitCodes.ERROR


def test_refusal_message_redacts_token_in_server_body():
    # ported: BootUiClientTests.aToolIsReportedRefusedWhenItsPanelIsOffOrTheActionIsReadOnly
    outcome = confirm_answered(
        FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []}),
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


@pytest.mark.parametrize("catalog", [None, {}, {"status": "UP"}])
def test_invalid_catalog_is_not_trusted(catalog):
    # ported: BootUiClientTests.rejectsDocumentsThatAreNotBootUiCatalogs
    client, answer = FakeClient(catalog=catalog), result(403, {"error": "denied"})
    with pytest.raises(ClientError, match="not a sharpit catalog"):
        confirm_answered(client, answer)


def test_disabled_catalog_must_have_no_tools():
    # ported: BootUiCliTests.anInconsistentDisabledCatalogCannotTurnAnOutageIntoAPolicySkip
    client = FakeClient(catalog={"serverName": "sharpit", "enabled": False, "tools": [{"name": "x"}]})
    answer = result(503)
    with pytest.raises(ClientError, match="not a sharpit catalog"):
        confirm_answered(client, answer)


def test_confirmed_503_keeps_server_error_text_and_status():
    # ported: BootUiCliTests.anUnrelatedUnavailableServerIsAnErrorNotAConfigurationSkip
    outcome = confirm_answered(
        FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []}),
        result(503, {"error": "database down"}),
    )
    assert "database down" in outcome.message
    assert "503" in outcome.message


def test_catalog_error_keeps_original_http_status_and_catalog_message():
    # ported: BootUiCliTests.anUnrelatedUnavailableServerIsAnErrorNotAConfigurationSkip
    client = FakeClient(error=ClientError("catalog says unavailable"))
    answer = result(503, {"error": "database down"})
    with pytest.raises(ClientError, match="503") as exc:
        confirm_answered(client, answer)
    assert "catalog says unavailable" in str(exc.value)


def test_real_read_only_refusal_shape():
    # ported: BootUiCliTests.aReadOnlyPanelStillRefusesAnActionWithThePolicyExitCode
    outcome = confirm_answered(
        FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []}),
        result(403, {"error": "Panel 'security' is read-only (sharpit.panels.security.read-only=true)"}),
    )
    assert outcome.exit_code == ExitCodes.REFUSED
    assert "read-only" in outcome.message


@pytest.mark.parametrize("status", [400, 401, 409, 429, 500, 504, 200])
def test_non_refusal_does_not_fetch_catalog(status):
    # ported: CliContext.confirmBootUiAnswered
    client = FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []})
    confirm_answered(client, result(status, {"error": "failure"}))
    assert client.catalog_calls == 0


@pytest.mark.parametrize("status", [403, 404, 503])
def test_refusal_confirmation_fetches_catalog_once(status):
    # ported: CliContext.confirmBootUiAnswered
    client = FakeClient(catalog={"serverName": "sharpit", "enabled": True, "tools": []})
    confirm_answered(client, result(status, {"error": "failure"}))
    assert client.catalog_calls == 1


def test_classify_redacts_echoed_token_and_uses_message_field():
    # derived: classification redacts server echoes using the client's token
    client = FakeClient()
    outcome = confirm_answered(client, result(500, {"message": "secret-token echoed"}))
    assert "secret-token" not in outcome.message
    assert "[redacted]" in outcome.message


def test_empty_error_body_falls_back_to_status():
    # ported: ToolResult.errorMessage
    assert classify(500, {}).message == "Request failed with HTTP 500"
