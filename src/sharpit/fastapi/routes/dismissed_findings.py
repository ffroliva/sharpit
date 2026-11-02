"""``{api}/dismissed-findings`` (port of BootUI 2.2.0 ``DismissedFindingsController``).

The guard covers the mutations with the global read-only policy (``_GLOBAL_WRITE_SUBJECTS``); once the body's
``ruleId`` is parsed, the owning advisor panel's gate applies too (sharpit deviation, as ``/dismissed-rules``). The
body is read as capped bytes and parsed here, so a malformed body is answered with one fixed message that never quotes
it (the note is user text). Deliberately no MCP tool or CLI command.
"""

from __future__ import annotations

import json
from importlib import import_module
from typing import Any, cast

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from sharpit.engine import guard, tools
from sharpit.engine.advisors.dismissals import Findings
from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.context import SharpitContext
from sharpit.fastapi.http import error, json_response

BODY_CAP = 65_536  # bytes: a rule id, an identity and a 200-character note fit many times over
INVALID_BODY = "Request body must be a JSON object with string fields ruleId, identity and an optional note."


def _fields(raw: bytes, *, with_note: bool) -> tuple[str, str, str | None] | None:
    """``(ruleId, identity, note)`` of a valid body, else None (BootUI ``parse``/``text``)."""
    try:
        body: object = json.loads(raw) if raw.strip() else None
    except (ValueError, RecursionError):
        return None
    if not isinstance(body, dict):
        return None
    fields = cast("dict[str, object]", body)
    rule_id, identity = fields.get("ruleId"), fields.get("identity")
    note = fields.get("note") if with_note else None
    if not isinstance(rule_id, str) or not isinstance(identity, str) or not isinstance(note, str | None):
        return None
    return rule_id, identity, note


def build_routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]
    adapter = cast(Any, import_module("sharpit.fastapi.adapter"))  # resolved per call: tests patch _read_capped

    def listed(_request: Request) -> Response:
        return json_response(tools.dismissal_store(ctx).list_findings().to_dto())

    async def changed(request: Request) -> Response:
        content_type = request.headers.get("content-type", "")
        if content_type.partition(";")[0].strip().lower() != "application/json":
            return error(415, "Unsupported Media Type")
        raw = await adapter._read_capped(request, BODY_CAP)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        fields = _fields(raw, with_note=request.method == "POST")
        if fields is None:
            return error(400, INVALID_BODY)
        rule_id, identity, note = fields
        denial = guard.owning_panel_access(rule_id, settings, "dismissed-findings")
        if denial is not None:
            return json_response(denial.body, denial.status)
        store = tools.dismissal_store(ctx)

        def apply() -> Findings:
            if request.method == "POST":
                return store.dismiss_finding(rule_id, identity, note)
            return store.restore_finding(rule_id, identity)

        try:
            findings = await run_in_threadpool(apply)
        except AdvisorViolationError as exc:  # BootUI AdvisorViolationExceptionHandler; messages never quote input
            return error(exc.status, exc.message)
        return json_response(findings.to_dto())

    return [
        Route(f"{api}/dismissed-findings", listed, methods=["GET"]),
        Route(f"{api}/dismissed-findings", changed, methods=["POST", "DELETE"]),
    ]
