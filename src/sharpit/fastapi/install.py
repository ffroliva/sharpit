"""Install and capture setup for the FastAPI adapter."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from starlette.applications import Starlette
from starlette.middleware import Middleware

from sharpit.engine import guard, sqla
from sharpit.engine.activation import active_profiles, decide
from sharpit.engine.capture import route_path
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.logtail import LogTailBuffer
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.streams import ChangeStream, StreamSlots
from sharpit.engine.capture.transactions import TransactionRecorder
from sharpit.engine.capture.transactions import attach as attach_transactions
from sharpit.engine.context import SharpitContext, application_family
from sharpit.engine.lowfootprint import LowFootprintService
from sharpit.engine.paging import BadRequest
from sharpit.engine.sources import dispatch
from sharpit.engine.sqltext import load_key
from sharpit.fastapi.adapter import SharpitHandle
from sharpit.fastapi.capture import HOOK_TRANSACTIONS, CaptureWiring
from sharpit.fastapi.introspector import FastApiIntrospector
from sharpit.fastapi.signals import dev_server_signal
from sharpit.settings import SharpitSettings, load_settings, parse_mode

__all__ = ["install", "_configure_capture"]

logger = logging.getLogger("sharpit")
_Lifespan = Callable[[Any], AbstractAsyncContextManager[Any]]
_clock = time.monotonic


class IdleTracker:
    def __init__(
        self,
        hooks: Any,
        timeout: float,
        held: Callable[[], bool],
        clock: Callable[[], float] | None = None,
        lock: Any | None = None,
    ) -> None:
        self.hooks, self.timeout, self.held = hooks, timeout, held
        self.clock = clock or time.monotonic
        self.last_active = self.clock()
        self.auto_suspended = False
        self.lock = lock or threading.Lock()

    def mark_active(self) -> None:
        with self.lock:
            self.last_active = self.clock()
            if self.auto_suspended and not self.held():
                self.hooks.resume()
                self.auto_suspended = False

    def check(self) -> None:
        with self.lock:
            if self.clock() - self.last_active >= self.timeout and not self.auto_suspended and not self.held():
                self.hooks.suspend()
                self.hooks.discard()
                self.auto_suspended = True

    def close(self) -> None:
        with self.lock:
            if self.auto_suspended and not self.held():
                self.hooks.resume()
            self.auto_suspended = False


def _configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring:
    capture = ctx.capture
    wiring = capture.wiring = CaptureWiring()
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
            application=lambda: application_family(ctx),
        )
    capture.engine_registry = sqla.EngineRegistry(ctx.masker)
    for engine in ctx.engines:
        capture.engine_registry.add(engine)
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
    if panels["transactions"].enabled and settings.transactions_enabled:
        recorder = capture.transactions = TransactionRecorder(
            ctx.masker,
            max_entries=settings.transactions_max_entries,
            slow_threshold_ms=settings.transactions_slow_transaction_threshold_millis,
            hold_threshold_ms=settings.transactions_connection_hold_threshold_millis,
            recording=settings.transactions_recording,
            application=lambda: application_family(ctx),
        )
        wiring.add_lane(ctx, HOOK_TRANSACTIONS, lambda: attach_transactions(ctx), recorder.clear)
    if panels["activity"].enabled:
        capture.activity_changes = ChangeStream()
        for source in (capture.exchanges, capture.exceptions, capture.sql_trace):
            if source is not None:
                source.changes.forward_to(capture.activity_changes)
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


def _models(models: object) -> tuple[object, ...]:  # NOSONAR - one element per supplied model: length follows input
    """``install(models=...)`` as a tuple; a lone class (``models=Base``) or other non-iterable is one element.

    The elements are never inspected (A-data reads them; spec §10.2, council R3/R15).
    """
    if models is None:
        return ()
    kind = type(models).__name__
    if isinstance(models, str | bytes | Mapping):  # iterable, but never a list of models
        raise TypeError(f"models must be a model class or an iterable of models, not {kind}")
    if isinstance(models, type) or not isinstance(models, Iterable):
        return (models,)
    return tuple(cast("Iterable[object]", models))


def _requested(settings: SharpitSettings, profiles: tuple[str, ...]) -> bool:
    """sharpit was asked for (an unusable SHARPIT_ENABLED, or an enabled profile is active) yet ended up inactive."""
    return parse_mode(settings.enabled) is None or any(p in profiles for p in settings.enabled_profiles)


def _existing_handle(router: Any, mount_type: type) -> Any:
    """An earlier install's handle on this router, with its warning logged; ``None`` on a first install."""
    existing = next((r.sharpit_handle for r in router.routes if isinstance(r, mount_type) and r.sharpit_handle), None)
    if existing is not None:
        first = (
            ""
            if existing.activation.enabled
            else f" (that install left sharpit inactive: {existing.activation.reason})"
        )
        logger.warning("sharpit.install() was already called on this app; ignoring this call%s", first)
    return existing


def _identity_key(settings: SharpitSettings) -> bytes | None:
    """The configured identity key, or the state directory's, created when missing."""
    if settings.identity_key:
        return settings.identity_key.encode("utf-8")
    return load_key(Path(settings.state_dir), create=True)


def _lifespan_phase(ctx: SharpitContext, phase: str | None) -> None:
    """Label SQL Trace statements outside a request with the lifespan phase sharpit observes (ruling (h))."""
    if (recorder := ctx.capture.sql_trace) is not None:
        recorder.lifespan_phase = phase


@asynccontextmanager
async def _lifespan(
    host_app: Any,
    *,
    original: _Lifespan,
    ctx: SharpitContext,
    wiring: CaptureWiring,
    settings: SharpitSettings,
    idle_tracker: IdleTracker | None,
) -> AsyncGenerator[Any]:
    timer: threading.Thread | None = None
    stop = threading.Event()
    try:
        startup_started_at = time.monotonic()
        _lifespan_phase(ctx, "STARTUP")
        async with original(host_app) as state:
            _lifespan_phase(ctx, None)
            if ctx.startup_time_ms is None:
                ctx.startup_time_ms = round((time.monotonic() - ctx.installed_at) * 1000)
                ctx.startup.record("asgi.lifespan.startup", round((time.monotonic() - startup_started_at) * 1000))
            wiring.on_startup(ctx)  # after the host's own startup (spec §6.1)
            if idle_tracker is not None:
                idle_tracker.mark_active()

                def monitor_idle() -> None:
                    interval = max(0.05, min(settings.free_on_idle_timeout, 1.0))
                    while not stop.wait(interval):
                        idle_tracker.check()

                timer = threading.Thread(target=monitor_idle, name="sharpit-free-on-idle", daemon=True)
                timer.start()
            try:
                yield state
            finally:
                _lifespan_phase(ctx, "SHUTDOWN")  # the host's shutdown runs as the ``async with`` exits
    finally:
        _lifespan_phase(ctx, None)
        if timer is not None:
            stop.set()
            timer.join()
        if idle_tracker is not None:
            idle_tracker.close()
        wiring.detach(ctx)


def install(
    app: Any,
    *,
    settings: object = (),
    engines: Sequence[object] = (),
    health_checks: Mapping[str, Callable[[], object]] | None = None,
    models: Iterable[object] | type | None = None,
    **options: Any,
) -> SharpitHandle:
    adapter = cast(Any, import_module("sharpit.fastapi.adapter"))
    guard_middleware = adapter.GuardMiddleware
    sharpit_handle_type = adapter.SharpitHandle
    sharpit_mount_type = adapter.SharpitMount
    _bad_request = adapter._bad_request
    _json_http_error = adapter._json_http_error
    _not_found = adapter._not_found
    caller_module: str | None = sys._getframe(1).f_globals.get("__name__")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    router = app.router
    if (existing := _existing_handle(router, sharpit_mount_type)) is not None:
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
        models=_models(models),
    )
    handle = sharpit_handle_type(sharpit_settings, activation, ctx, original)
    idle_tracker: IdleTracker | None = None
    for warning in activation.warnings:  # the overview panel shows them too, but not while sharpit is inactive
        logger.warning("%s", warning)

    if not activation.enabled:
        mount = sharpit_mount_type(sharpit_settings.path, app=_not_found, name="sharpit")
        mount.sharpit_handle = handle
        router.routes.insert(0, mount)
        # asked for but still off is a WARNING (uvicorn drops INFO from unconfigured loggers); an explicit OFF is INFO
        level = logging.WARNING if _requested(sharpit_settings, profiles) else logging.INFO
        logger.log(level, "sharpit inactive: %s", activation.reason)
        return handle

    ctx.masker.identity_key = _identity_key(sharpit_settings)
    if ctx.masker.identity_key is None:
        logger.warning("SQLite statement identities are unavailable because sharpit could not load a state key")

    wiring = _configure_capture(app, ctx, sharpit_settings)

    middleware = [Middleware(guard_middleware, ctx=ctx)]
    if sharpit_settings.free_on_idle_enabled:
        low_footprint = ctx.lazy("low-footprint", lambda: LowFootprintService(ctx.capture.hooks))
        idle_tracker = IdleTracker(
            ctx.capture.hooks,
            sharpit_settings.free_on_idle_timeout,
            lambda: low_footprint.enabled,
            lock=low_footprint._lock,  # pyright: ignore[reportPrivateUsage]
        )
        middleware.append(_activity_middleware(ctx, idle_tracker))
    router.lifespan_context = partial(
        _lifespan,
        original=original,
        ctx=ctx,
        wiring=wiring,
        settings=sharpit_settings,
        idle_tracker=idle_tracker,
    )
    sub_app = Starlette(
        routes=adapter._routes(ctx, app),
        middleware=middleware,
        exception_handlers={404: _json_http_error, 405: _json_http_error, BadRequest: _bad_request},
    )
    mount = sharpit_mount_type(sharpit_settings.path, app=sub_app, name="sharpit")
    mount.sharpit_handle = handle
    router.routes.insert(0, mount)
    if sharpit_settings.show_banner:
        print(_banner(ctx, generated), file=sys.stderr)
    elif generated:  # nothing else can ever reveal a generated token
        print(f"sharpit authentication token (generated for this process): {token}", file=sys.stderr)
    return handle


def _activity_middleware(ctx: SharpitContext, tracker: IdleTracker) -> Middleware:
    """Resume automatically suspended hooks after the guard accepts a sharpit API request."""

    class ActivityMiddleware:
        def __init__(self, app: Any, ctx: SharpitContext, tracker: IdleTracker) -> None:
            self.app = app
            self.ctx = ctx
            self.tracker = tracker
            self.api_prefix = ctx.settings.api_path[len(ctx.settings.path) :]

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            path = route_path(scope)
            if path == self.api_prefix or path.startswith(self.api_prefix + "/"):
                self.tracker.mark_active()
            await self.app(scope, receive, send)

    return Middleware(ActivityMiddleware, ctx=ctx, tracker=tracker)
