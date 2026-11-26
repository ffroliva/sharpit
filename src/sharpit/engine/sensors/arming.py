"""Arms the sensor lane and its report service on a capture context; the framework adapters call it once."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from sharpit.engine.capture.journal import JournalSink
from sharpit.engine.collectors.sideeffects.service import SideEffectsService
from sharpit.engine.sensors.lane import SensorLane, build_lane

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext


def _no_owner(scope: Mapping[str, Any]) -> str | None:
    del scope
    return None


def arm_sensors(
    ctx: SharpitContext,
    journal: JournalSink,
    *,
    owner: Callable[[Mapping[str, Any]], str | None] = _no_owner,
    exchanges_enabled: Callable[[], bool] = lambda: True,
) -> SensorLane | None:
    """Build the lane for the configured sensors, wire its report service and hooks, and attach it."""
    lane = ctx.capture.sensors = build_lane(
        ctx.settings.agent_sensors,
        journal,
        ctx.masker.mask_path,
        own=(ctx.settings.state_dir,),
        request_values=ctx.settings.agent_security_sinks_request_values,
        context_id=ctx.context_id,
        owner=owner,
    )
    if lane is not None:
        ctx.capture.side_effects = SideEffectsService(
            ctx.capture,
            ctx.masker,
            lambda: ctx.capture.ready_at_ms,
            exchanges_enabled=exchanges_enabled,
        )
        for hook in lane.hooks():
            ctx.capture.hooks.register(hook)
        lane.attach()
    return lane
