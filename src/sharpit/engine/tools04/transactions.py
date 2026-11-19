from __future__ import annotations

from typing import Any

from sharpit.engine.capture.transactions import TransactionRecorder, context_report
from sharpit.engine.lowfootprint import LowFootprintService
from sharpit.engine.tools import Tool, low_footprint_resume_error

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def _clear(ctx: Any) -> dict[str, Any]:
    recorder = ctx.capture.transactions
    if isinstance(recorder, TransactionRecorder):
        recorder.clear()
    return {"cleared": True}


def _recording(ctx: Any, enabled: bool) -> dict[str, Any]:
    service = ctx.peek("low-footprint")
    if enabled and isinstance(service, LowFootprintService) and service.enabled:
        raise low_footprint_resume_error("resume_transaction_recording")
    recorder = ctx.capture.transactions
    if isinstance(recorder, TransactionRecorder):
        recorder.set_recording(enabled)
    return {"recording": bool(recorder and isinstance(recorder, TransactionRecorder) and recorder.recording)}


TOOLS = (
    Tool(
        "get_transactions",
        "Return the current bounded transaction snapshot captured from SQLAlchemy connection events. "
        "propagation describes observed boundaries: NEW (physical begin without a known parent), REQUIRES_NEW "
        "(child physical begin), NESTED (savepoint), or UNKNOWN (begin failed or ownership unverified), not "
        "declared annotation values. A joining method adds no boundary. Use it to verify which local operations "
        "actually ran in a transaction. SQLAlchemy records physical begin/commit/rollback callbacks, not a complete "
        "method propagation hierarchy. SQL statement and connection counts cover work correlated to the transaction's "
        "SQLAlchemy connection, not work performed on another thread. totalCaptured counts transactions recorded "
        "since startup and is not reset by clear; stats and entries cover the retained window only. When capture is "
        "paused, capturing is false and does not mean the application was quiet.",
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
