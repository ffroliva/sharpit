"""BootUI-compatible low-footprint status and CLI action tools."""

from __future__ import annotations

import gc
from typing import Any, cast

from sharpit.engine.lowfootprint import LowFootprintService

_NONE: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def _service(call: Any) -> LowFootprintService:
    return call.ctx.lazy("low-footprint", lambda: LowFootprintService(call.ctx.capture.hooks))


def _status(call: Any, _args: dict[str, Any]) -> dict[str, Any]:
    service = _service(call)
    return _status_after(service.status(), call)


def _status_after(state: dict[str, object], call: Any) -> dict[str, Any]:
    service = _service(call)
    raw_failures = cast(list[str], state["failures"])
    failures: list[str] = []
    for failure in raw_failures:
        name, _, detail = failure.partition(": ")
        failures.append(call.ctx.masker.mask_text(f"Could not pause {name}: {detail}"))
    hooks = cast(list[str], state["hooks"])
    return {
        "active": cast(bool, state["enabled"]),
        "sinceEpochMillis": service.since_epoch_millis,
        "agentAttached": False,
        "components": [
            {
                "id": name,
                "label": name,
                "suspended": not any(failure.partition(":")[0] == name for failure in raw_failures),
                "failure": next(
                    (
                        call.ctx.masker.mask_text(failure.partition(": ")[2])
                        for failure in raw_failures
                        if failure.startswith(name + ":")
                    ),
                    None,
                ),
            }
            for name in hooks
        ]
        if state["enabled"]
        else [],
        "warnings": failures,
        "offload": None,
    }


def _ack(action: str, status: dict[str, Any]) -> dict[str, Any]:
    failed = [component for component in status["components"] if not component["suspended"]]
    return {
        "action": action,
        "active": status["active"],
        "sinceEpochMillis": status["sinceEpochMillis"],
        "agentAttached": status["agentAttached"],
        "warnings": status["warnings"],
        "failedComponents": failed,
        "offload": None,
    }


def _enable(call: Any, _args: dict[str, Any]) -> dict[str, Any]:
    state, changed = _service(call).suspend_with_transition()
    if changed:
        gc.collect()
    return _ack("enabled", _status_after(state, call))


def _disable(call: Any, _args: dict[str, Any]) -> dict[str, Any]:
    return _ack("disabled", _status_after(_service(call).resume(), call))


def tool_definitions(tool_type: Any) -> tuple[Any, ...]:
    return (
        tool_type(
            "get_low_footprint",
            "Read low-footprint mode without changing recording: active, sinceEpochMillis, agentAttached, components "
            "with suspension outcomes, and warnings. The Java agent is not paused.",
            _NONE,
            "live-memory",
            False,
            _status,
        ),
        tool_type(
            "enable_low_footprint",
            "Enable low-footprint mode: pause sharpit recording, irreversibly discard buffered diagnostics, and "
            "request GC (which may not reclaim every buffer). Ask for approval first. Idempotent: enabling again does "
            "not clear or request GC again. Returns a compact acknowledgement with offload totals and failures; "
            "get_low_footprint lists component outcomes. The Java agent keeps running.",
            _NONE,
            "live-memory",
            True,
            _enable,
        ),
        tool_type(
            "disable_low_footprint",
            "Disable low-footprint mode and release its recording hold. Cleared data cannot be recovered; individually "
            "paused recorders stay paused. Ask for approval first. Idempotent. Returns a compact acknowledgement with "
            "state and warnings; get_low_footprint lists component outcomes.",
            _NONE,
            "live-memory",
            True,
            _disable,
        ),
    )


COMMANDS = {
    "get_low_footprint": "low-footprint status",
    "enable_low_footprint": "low-footprint enable",
    "disable_low_footprint": "low-footprint disable",
}
