"""Install and capture setup for the FastAPI adapter."""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from importlib import import_module
from typing import Any, cast

from starlette.applications import Starlette
from starlette.middleware import Middleware

from sharpit.engine import guard, sqla
from sharpit.engine.activation import active_profiles, decide
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.logtail import LogTailBuffer
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.streams import ChangeStream, StreamSlots
from sharpit.engine.context import SharpitContext
from sharpit.engine.paging import BadRequest
from sharpit.engine.sources import dispatch
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import CaptureWiring
from sharpit.fastapi.introspector import FastApiIntrospector
from sharpit.fastapi.route_registry import register_routes
from sharpit.fastapi.signals import dev_server_signal
from sharpit.settings import SharpitSettings, load_settings, parse_mode

__all__ = ["install", "_configure_capture"]

logger = logging.getLogger("sharpit")
_Lifespan = Callable[[Any], AbstractAsyncContextManager[Any]]


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


def _banner(ctx: SharpitContext, generated: bool) -> str:
    lines = [f"sharpit active at {ctx.settings.path}/ ({ctx.activation.reason})"]
    if generated:
        lines.append(f"sharpit authentication token (generated for this process): {ctx.token}")
    return "\n".join(lines)


def _app_settings(settings: object) -> tuple[object, ...]:
    """One pydantic settings instance or an iterable of them (a lone model is iterable too, so check it first)."""
    if hasattr(type(settings), "model_fields"):
        return (settings,)
    try:
        items = tuple(cast("Iterable[object]", settings))
    except TypeError:
        items = (settings,)
    for item in items:
        if not hasattr(type(item), "model_fields"):
            raise TypeError(
                f"settings must be a pydantic settings instance or an iterable of them, not {type(item).__name__}"
            )
    return items


def _requested(settings: SharpitSettings, profiles: tuple[str, ...]) -> bool:
    """sharpit was asked for (an unusable SHARPIT_ENABLED, or an enabled profile is active) yet ended up inactive."""
    return parse_mode(settings.enabled) is None or any(p in profiles for p in settings.enabled_profiles)


def install(
    app: Any,
    *,
    settings: object = (),
    engines: Sequence[object] = (),
    health_checks: Mapping[str, Callable[[], object]] | None = None,
    **options: Any,
) -> SharpitHandle:
    adapter = cast(Any, import_module("sharpit.fastapi.adapter"))
    GuardMiddleware = adapter.GuardMiddleware
    SharpitHandle = adapter.SharpitHandle
    SharpitMount = adapter.SharpitMount
    _bad_request = adapter._bad_request
    _json_http_error = adapter._json_http_error
    _not_found = adapter._not_found
    caller_module: str | None = sys._getframe(1).f_globals.get("__name__")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    router = app.router
    existing = next((r.sharpit_handle for r in router.routes if isinstance(r, SharpitMount) and r.sharpit_handle), None)
    if existing is not None:
        first = (
            ""
            if existing.activation.enabled
            else f" (that install left sharpit inactive: {existing.activation.reason})"
        )
        logger.warning("sharpit.install() was already called on this app; ignoring this call%s", first)
        return existing
    app_settings = _app_settings(settings)
    sharpit_settings = load_settings(options, os.environ)
    if (sink := dispatch.session_sink()) is not None:
        sink.register_app(app)
    profiles = tuple(active_profiles(sharpit_settings, os.environ))
    activation = decide(sharpit_settings, profiles, dev_server_signal(sys.argv))
    token, generated = guard.resolve_token(sharpit_settings) if activation.enabled else (None, False)
    original: _Lifespan = router.lifespan_context
    ctx = SharpitContext(
        sharpit_settings,
        activation,
        FastApiIntrospector(app, sharpit_settings.path, original),
        token=token,
        profiles=profiles,
        app_settings=app_settings,
        caller_module=caller_module,
        engines=tuple(engines),
        health_checks=dict(health_checks or {}),
    )
    handle = SharpitHandle(sharpit_settings, activation, ctx, original)
    for warning in activation.warnings:  # the overview panel shows them too, but not while sharpit is inactive
        logger.warning("%s", warning)

    if not activation.enabled:
        mount = SharpitMount(sharpit_settings.path, app=_not_found, name="sharpit")
        mount.sharpit_handle = handle
        router.routes.insert(0, mount)
        # asked for but still off is a WARNING (uvicorn drops INFO from unconfigured loggers); an explicit OFF is INFO
        level = logging.WARNING if _requested(sharpit_settings, profiles) else logging.INFO
        logger.log(level, "sharpit inactive: %s", activation.reason)
        return handle

    wiring = _configure_capture(app, ctx, sharpit_settings)

    @asynccontextmanager
    async def lifespan(host_app: Any) -> AsyncGenerator[Any]:  # NOSONAR - asynccontextmanager coroutine
        try:
            async with original(host_app) as state:
                if ctx.startup_time_ms is None:
                    ctx.startup_time_ms = round((time.monotonic() - ctx.installed_at) * 1000)
                wiring.on_startup(ctx)  # after the host's own startup (spec §6.1)
                yield state
        finally:
            wiring.detach(ctx)

    router.lifespan_context = lifespan
    sub_app = Starlette(
        routes=[],
        middleware=[Middleware(GuardMiddleware, ctx=ctx)],
        exception_handlers={404: _json_http_error, 405: _json_http_error, BadRequest: _bad_request},
    )
    register_routes(sub_app, adapter._routes(ctx, app))
    mount = SharpitMount(sharpit_settings.path, app=sub_app, name="sharpit")
    mount.sharpit_handle = handle
    router.routes.insert(0, mount)
    if sharpit_settings.show_banner:
        print(_banner(ctx, generated), file=sys.stderr)
    elif generated:  # nothing else can ever reveal a generated token
        print(f"sharpit authentication token (generated for this process): {token}", file=sys.stderr)
    return handle
