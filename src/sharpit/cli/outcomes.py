"""Interpret command-line endpoint responses and confirm policy refusals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from sharpit.cli.client import ClientError
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
    message = ""
    if isinstance(body, dict):
        document = cast(dict[str, Any], body)
        error = document.get("error")
        reason = document.get("reason")
        if isinstance(error, str) and error.strip():
            message = error.strip()
        if isinstance(reason, str) and reason.strip():
            message = f"{message}: {reason.strip()}" if message else reason.strip()
    return Outcome(kind, message)


def confirm_answered(client: Any, result: Any) -> Outcome:
    """Confirm sharpit before classifying a 403/404/503 as a sharpit response."""
    outcome = classify(result.status, result.payload)
    token = getattr(getattr(client, "options", None), "token", None)
    if token:
        outcome = Outcome(outcome.kind, outcome.message.replace(token, "[redacted]"))
    if outcome.kind not in (OutcomeKind.REFUSED_BY_POLICY, OutcomeKind.UNKNOWN_TOOL) and result.status != 503:
        return outcome
    try:
        catalog = client.catalog()
    except ClientError:
        raise ClientError("The target did not answer the sharpit CLI catalog; refusal is not confirmed.") from None
    if not isinstance(catalog, dict):
        raise ClientError("The target did not identify itself as sharpit; refusal is not confirmed.")
    document = cast(dict[str, Any], catalog)
    if document.get("serverName") != "sharpit":
        raise ClientError("The target did not identify itself as sharpit; refusal is not confirmed.")
    if result.status == 503:
        if document.get("enabled") is False:
            return Outcome(OutcomeKind.ENDPOINT_DISABLED, "The sharpit command-line endpoint is disabled.")
        return Outcome(OutcomeKind.SERVER_ERROR, "The sharpit endpoint returned HTTP 503.")
    return outcome
