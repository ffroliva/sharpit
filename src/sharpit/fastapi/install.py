"""Capture setup performed while installing sharpit on a host application."""

from __future__ import annotations

from typing import Any

from sharpit.engine import sqla
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.logtail import LogTailBuffer
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.streams import ChangeStream, StreamSlots
from sharpit.engine.context import SharpitContext
from sharpit.fastapi.capture import CaptureWiring
from sharpit.settings import SharpitSettings


def _configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring:
    capture = ctx.capture
    capture.stream_slots = StreamSlots()
    if settings.panels["log-tail"].enabled:
        capture.log_tail = LogTailBuffer(settings.log_tail_max_lines, settings.log_tail_max_bytes)
    panels = settings.panels
    if panels["http-exchanges"].enabled or panels["activity"].enabled:  # activity's REQUEST rows (spec §7.4)
        capture.exchanges = HttpExchangeBuffer(settings.http_exchanges_max_exchanges)
    if panels["exceptions"].enabled:
        capture.exceptions = ExceptionStore(
            settings.exceptions_max_groups,
            settings.exceptions_max_occurrences_per_group,
            settings.exceptions_max_stack_frames,
            ctx.masker,
        )
    capture.engine_registry = sqla.EngineRegistry(ctx.masker)
    if panels["sql-trace"].enabled and settings.sql_trace_enabled:
        capture.sql_trace = SqlTraceRecorder(
            ctx.masker,
            max_entries=settings.sql_trace_max_entries,
            slow_query_threshold_millis=settings.sql_trace_slow_query_threshold_millis,
            max_sql_length=settings.sql_trace_max_sql_length,
            max_parameter_length=settings.sql_trace_max_parameter_length,
            n_plus_one_threshold=settings.sql_trace_n_plus_one_threshold,
            capture_call_site=settings.sql_trace_capture_call_site,
            recording=settings.sql_trace_recording,
        )
    if panels["activity"].enabled:
        capture.activity_changes = ChangeStream()
        for source in (capture.exchanges, capture.exceptions, capture.sql_trace):
            if source is not None:
                source.changes.forward_to(capture.activity_changes)
    wiring = capture.wiring = CaptureWiring()
    wiring.attach_at_install(app, ctx)
    return wiring
