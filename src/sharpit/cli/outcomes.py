"""Interpret command-line endpoint responses and confirm policy refusals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from sharpit.cli.client import Client, ClientError, ToolResult, error_message
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.manifest import Manifest, ManifestTool


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


def _classify(status: int, body: Any, token: str | None) -> Outcome:
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
    message = "" if kind is OutcomeKind.SUCCESS else f"Request failed with HTTP {status}"
    if kind is OutcomeKind.SUCCESS:
        return Outcome(kind, "")
    message = error_message(body, token) or message
    return Outcome(kind, message)


def confirm_answered(client: Client, result: ToolResult) -> Outcome:
    """Confirm sharpit before classifying a 403/404/503 as a sharpit response."""
    outcome = _classify(result.status, result.raw_body or result.payload, client.options.token)
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
        return outcome
    if result.status != 404:
        return outcome
    tools = catalog.get("tools", [])
    if isinstance(tools, list) and any(
        isinstance(item, dict) and cast(dict[str, Any], item).get("name") == result.tool_name
        for item in cast(list[Any], tools)
    ):
        return Outcome(OutcomeKind.UNKNOWN_TOOL, error_message(result.raw_body or result.payload) or outcome.message)
    tool = Manifest.bundled().by_name(result.tool_name)
    message = f"This application does not expose '{result.tool_name}'."
    if tool is not None:
        message += _unknown_tool_hint(client, tool)
    return Outcome(OutcomeKind.UNKNOWN_TOOL, message)


def _unknown_tool_hint(client: Client, tool: ManifestTool) -> str:
    try:
        document = client.get("/panels")
        if isinstance(document, dict):
            fields = cast(dict[str, Any], document)
            advertised = fields.get("panels")
            panels: list[Any] = (
                cast(list[Any], advertised) if isinstance(advertised, list) and advertised else list(fields.values())
            )
        elif isinstance(document, list):
            panels = cast(list[Any], document)
        else:
            panels = []
        for raw_panel in panels:
            if not isinstance(raw_panel, dict):
                continue
            panel = cast(dict[str, Any], raw_panel)
            if panel.get("id") != tool.panel:
                continue
            if panel.get("available") is not False:
                break
            reason = panel.get("unavailableReason", "")
            suffix = f": {reason}" if isinstance(reason, str) and reason.strip() else ""
            return f" Its '{tool.panel}' panel is not available in this application{suffix}."
    except Exception:  # noqa: S110 - a failed hint must not replace the original 404.
        pass
    return " The application may be running an older sharpit version."
