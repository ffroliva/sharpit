"""Interpret command-line endpoint responses and confirm policy refusals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from sharpit.cli.client import Client, ClientError, ToolResult, nonblank, redact, sharpit_text
from sharpit.cli.exit_codes import ExitCodes


class OutcomeKind(Enum):
    SUCCESS = "success"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN_TOOL = "unknown_tool"
    REFUSED_BY_POLICY = "refused_by_policy"
    BUSY = "busy"
    TIMED_OUT = "timed_out"
    ENDPOINT_DISABLED = "endpoint_disabled"
    UNAUTHENTICATED = "unauthenticated"
    SERVER_ERROR = "server_error"


@dataclass(frozen=True, slots=True)
class Outcome:
    kind: OutcomeKind
    message: str

    @property
    def exit_code(self) -> int:
        if self.kind is OutcomeKind.SUCCESS:
            return ExitCodes.SUCCESS
        if self.kind in (OutcomeKind.REFUSED_BY_POLICY, OutcomeKind.ENDPOINT_DISABLED):
            return ExitCodes.REFUSED
        return ExitCodes.ERROR


def classify(status: int, body: Any) -> Outcome:
    """Port of ``ToolOutcome.fromStatus``; a 503 is never a refusal by status alone."""
    kind = (
        OutcomeKind.SUCCESS
        if 200 <= status < 300
        else {
            400: OutcomeKind.INVALID_REQUEST,
            401: OutcomeKind.UNAUTHENTICATED,
            403: OutcomeKind.REFUSED_BY_POLICY,
            404: OutcomeKind.UNKNOWN_TOOL,
            409: OutcomeKind.BUSY,
            429: OutcomeKind.BUSY,
            504: OutcomeKind.TIMED_OUT,
        }.get(status, OutcomeKind.SERVER_ERROR)
    )
    message = "" if 200 <= status < 300 else f"Request failed with HTTP {status}"
    if status >= 200 and status < 300:
        return Outcome(kind, "")
    if isinstance(body, dict):
        document = cast("dict[str, Any]", body)
        error = nonblank(document.get("error"))
        specific = nonblank(document.get("reason")) or nonblank(document.get("message"))
        message = error or specific or message
        if error and specific and error != specific:
            message = f"{error}: {specific}"
    message = sharpit_text(message)
    return Outcome(kind, message)


def confirm_answered(client: Client, result: ToolResult) -> Outcome:
    """Confirm sharpit before classifying a 403/404/503 as a sharpit response."""
    outcome = classify(result.status, result.payload)
    outcome = Outcome(outcome.kind, redact(outcome.message, client.options.token))
    if outcome.kind not in (OutcomeKind.REFUSED_BY_POLICY, OutcomeKind.UNKNOWN_TOOL) and result.status != 503:
        return outcome
    try:
        catalog = client.catalog()
    except ClientError as error:
        context = (
            "Cannot confirm sharpit command-line endpoint state after HTTP 503. "
            if result.status == 503
            else "This is not a sharpit policy refusal. "
        )
        raise ClientError(context + str(error)) from None
    if result.status == 503:
        if catalog["enabled"] is False:
            return Outcome(OutcomeKind.ENDPOINT_DISABLED, outcome.message)
        return Outcome(outcome.kind, f"{outcome.message} (HTTP 503)")
    return outcome
