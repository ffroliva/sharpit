from __future__ import annotations

from typing import Any

from sharpit.engine.capture.transactions import TransactionRecorder, context_report
from sharpit.engine.lowfootprint import LowFootprintService
from sharpit.engine.tools import Tool, ToolCallError

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def _clear(ctx: Any) -> dict[str, Any]:
    recorder = ctx.capture.transactions
    if isinstance(recorder, TransactionRecorder):
        recorder.clear()
    return {"cleared": True}


def _recording(ctx: Any, enabled: bool) -> dict[str, Any]:
    service = ctx.peek("low-footprint")
    if enabled and isinstance(service, LowFootprintService) and service.enabled:
        raise ToolCallError("Low-footprint mode is active; disable it before resuming recording", 409)
    recorder = ctx.capture.transactions
    if isinstance(recorder, TransactionRecorder):
        recorder.set_recording(enabled)
    return {"recording": bool(recorder and isinstance(recorder, TransactionRecorder) and recorder.recording)}


TOOLS = (
    Tool(
        "get_transactions",
        "Return the newest bounded transaction snapshot captured from SQLAlchemy connection events. "
        "This reads only local cached data.",
        _NONE,
        "transactions",
        False,
        lambda call, _args: context_report(call.ctx),
    ),
    Tool(
        "clear_transactions",
        "Clear the retained local transaction entries without changing whether recording is enabled.",
        _NONE,
        "transactions",
        True,
        lambda call, _args: _clear(call.ctx),
    ),
    Tool(
        "pause_transaction_recording",
        "Pause local transaction recording; existing entries remain available until cleared.",
        _NONE,
        "transactions",
        True,
        lambda call, _args: _recording(call.ctx, False),
    ),
    Tool(
        "resume_transaction_recording",
        "Resume local transaction recording for new SQLAlchemy connection events.",
        _NONE,
        "transactions",
        True,
        lambda call, _args: _recording(call.ctx, True),
    ),
)

COMMANDS = {
    "get_transactions": "transactions",
    "clear_transactions": "transactions clear",
    "pause_transaction_recording": "transactions pause",
    "resume_transaction_recording": "transactions resume",
}
