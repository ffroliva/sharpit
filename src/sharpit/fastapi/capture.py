"""Request capture on the host app (spec §6.1, §7.1, §9): a pure ASGI middleware and the wiring that owns the hooks.

Pure ASGI, never ``BaseHTTPMiddleware``: that runs the endpoint in another task (contextvars set downstream are
invisible here) and buffers streaming bodies. Only ``receive`` and ``send`` are wrapped.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from starlette._utils import is_async_callable  # pyright: ignore[reportPrivateUsage]  # Starlette's own dispatch test
from starlette.exceptions import HTTPException
from starlette.routing import Mount, compile_path
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sharpit.engine import sqla
from sharpit.engine.capture import route_path, under
from sharpit.engine.capture.correlation import REQUEST, TEST, RequestInfo, new_request_id
from sharpit.engine.capture.exchanges import exchange_row
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.capture.securitylogs import attach as attach_security_logs
from sharpit.engine.context import application_family
from sharpit.engine.panels import panel_is_implemented
from sharpit.engine.sources import dispatch, sqlite
from sharpit.engine.sqltext import is_database_exception

if TYPE_CHECKING:
    from sharpit.engine.capture.exceptions import ExceptionStore
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit")


def _panel_enabled(ctx: SharpitContext, panel_id: str) -> bool:
    return panel_is_implemented(panel_id) and ctx.settings.panels[panel_id].enabled


CAPTURE_TOO_LATE = "request capture unavailable: install() ran after the app started"
CAPTURE_TOO_LATE_REASON = "Request capture is unavailable: install() ran after the app started"
CAPTURE_PANELS = (
    "http-exchanges",
    "exceptions",
    "sql-trace",
    "activity",
    "security-logs",
)  # any implemented, enabled request-capture panel needs the middleware
LOG_PANELS = ("log-tail", "exceptions")  # either enabled needs the log handler (spec §6.1 step 3)
LOG_TAIL_DETACHED_REASON = (
    "The sharpit log handler is not on the root logger: the app reconfigured logging (dictConfig or "
    "basicConfig(force=True)) after startup, or the app has not started"
)
SEVERAL_WORKERS = (
    "sharpit sees several worker processes: each worker has its own capture buffers and streams, and a generated "
    "authentication token works only in the worker that printed it. Set SHARPIT_AUTHENTICATION_TOKEN for remote access."
)
PROBE_HEADER = b"x-sharpit-probe"
PROBE_EXTENSION = "sharpit.probe"
MAX_MOUNT_DEPTH = 32  # a sub-app mounted inside itself must not loop the walk
# low-footprint registry entries: each name is spelled only here
HOOK_CAPTURE_MIDDLEWARE = "capture-middleware"
HOOK_SECURITY_LOG = "security-log"
HOOK_EXCEPTION_HANDLERS = "exception-handlers"
HOOK_LOG_HANDLER = "log-handler"
HOOK_SQLA_LISTENERS = "sqla-listeners"
HOOK_SQLITE_LISTENERS = "sqlite-listeners"
HOOK_TRACES = "traces"
HOOK_TRANSACTIONS = "transactions"
HOOK_NAMES = frozenset(
    {
        HOOK_CAPTURE_MIDDLEWARE,
        HOOK_SECURITY_LOG,
        HOOK_EXCEPTION_HANDLERS,
        HOOK_LOG_HANDLER,
        HOOK_SQLA_LISTENERS,
        HOOK_SQLITE_LISTENERS,
        HOOK_TRACES,
        HOOK_TRANSACTIONS,
    }
)


def several_workers(environ: Mapping[str, str], argv: Sequence[str]) -> bool:
    """What the process can tell (spec §10): ``WEB_CONCURRENCY`` > 1, or ``--workers N`` / ``-w N`` > 1 in argv
    (uvicorn's spawned workers and gunicorn's forked ones keep the parent's argv)."""
    counts = [environ.get("WEB_CONCURRENCY", "")]
    for i, arg in enumerate(argv):
        if arg in ("--workers", "-w") and i + 1 < len(argv):
            counts.append(argv[i + 1])
        elif arg.startswith("--workers="):
            counts.append(arg.partition("=")[2])
    return any(c.strip().isascii() and c.strip().isdecimal() and int(c) > 1 for c in counts)


def _endpoint_name(endpoint: object) -> str | None:
    if endpoint is None:
        return None
    qualname = getattr(endpoint, "__qualname__", type(endpoint).__name__)
    return f"{getattr(endpoint, '__module__', None) or '?'}:{qualname}"


@functools.lru_cache(maxsize=1024)  # templates come from the host's code, never from a request
def _template_regex(template: str) -> re.Pattern[str]:
    return compile_path(template)[0]


def _mount_of(routes: Iterable[object], path: str) -> tuple[Mount, str] | None:
    """The first ``Mount`` that takes ``path``, the router's own pick (a Mount matches fully), and what it leaves."""
    for route in routes:
        if isinstance(route, Mount) and (match := route.path_regex.match(path)):
            return route, "/" + match["path"]
    return None


def _mount_prefix(routes: Iterable[object], path: str, below: str) -> str | None:
    """The Mounts' own templates from ``path`` down to ``below``, read from the route table: ``root_path`` only has the
    request's values. ``None`` when the table does not lead there (an ASGI wrapper hides the sub-app's routes)."""
    prefix = ""
    for _ in range(MAX_MOUNT_DEPTH):
        if path == below:
            return prefix
        step = _mount_of(routes, path)
        if step is None:
            return None
        mount, path = step
        prefix, routes = prefix + mount.path, mount.routes
    return None


def _route_template(scope: Scope, root_path: str, app: object) -> str | None:
    """The matched route's template behind the templates of its mounts, only when it matches the real path; ``None``
    (the masked path) otherwise: FastAPI 0.16x's ``route.path`` has no ``include_router`` prefix."""
    template = getattr(scope.get("route"), "path", None)
    if not isinstance(template, str):
        return None
    below = route_path(scope)
    try:
        prefix = _mount_prefix(
            getattr(app, "routes", ()), route_path({"path": scope["path"], "root_path": root_path}), below
        )
        return None if prefix is None or _template_regex(template).match(below) is None else prefix + template
    except Exception:  # noqa: BLE001 - a drifted router or a custom route degrades to the masked path; the row stays
        return None


def _wrapped_key(key: object) -> bool:
    """Handlers that see real failures: ``Exception`` classes and 500. HTTP errors and validation errors are
    answers, not failures (FastAPI's classes are found without importing FastAPI)."""
    if isinstance(key, int):
        return key == 500
    if not isinstance(key, type) or issubclass(key, HTTPException):
        return False
    fastapi_errors = sys.modules.get("fastapi.exceptions")
    skipped = [getattr(fastapi_errors, n, None) for n in ("RequestValidationError", "WebSocketRequestValidationError")]
    return not any(isinstance(c, type) and issubclass(key, c) for c in skipped)


def _wrap_handler(original: Callable[..., Any], wiring: CaptureWiring, store: ExceptionStore) -> Callable[..., Any]:
    def record(conn: Any, exc: Exception) -> None:
        if wiring.detached or HOOK_EXCEPTION_HANDLERS in wiring.suspended_hooks:  # the built stack keeps this wrapper
            return
        try:
            if (sink := dispatch.session_sink()) is not None:
                sink.on_exception(exc, "handler", TEST.get())
            info = REQUEST.get()
            if info is not None and info.endpoint is None:
                info.endpoint = _endpoint_name(conn.scope.get("endpoint"))
            store.record(exc, "handler", info, threading.current_thread().name)
        except Exception as failure:  # noqa: BLE001 - the host's handler always runs
            wiring.hook_failed("exception handler", failure)

    if is_async_callable(original):

        async def async_wrapper(conn: Any, exc: Exception) -> Any:
            record(conn, exc)
            return await original(conn, exc)

        wrapper: Callable[..., Any] = async_wrapper
    else:

        def sync_wrapper(conn: Any, exc: Exception) -> Any:
            record(conn, exc)
            return original(conn, exc)

        wrapper = sync_wrapper
    wrapper.__sharpit_original__ = original  # type: ignore[attr-defined]
    return wrapper


class WrappingHandlers(dict[Any, Any]):
    """``app.exception_handlers`` while sharpit is installed: handlers set later (``@app.exception_handler``) are
    wrapped too. Reads return the stored value, so a wrapped handler reads as its wrapper."""

    def __init__(self, handlers: Mapping[Any, Any], wiring: CaptureWiring, store: ExceptionStore) -> None:
        super().__init__()
        self._wiring = wiring
        self._store = store
        for key, handler in handlers.items():
            self[key] = handler

    def __setitem__(self, key: Any, handler: Any) -> None:
        if _wrapped_key(key) and not hasattr(handler, "__sharpit_original__"):
            handler = _wrap_handler(handler, self._wiring, self._store)
        super().__setitem__(key, handler)


def unwrap_exception_handlers(app: Any) -> None:
    handlers = getattr(app, "exception_handlers", None)
    if isinstance(handlers, WrappingHandlers):
        app.exception_handlers = {k: getattr(v, "__sharpit_original__", v) for k, v in handlers.items()}


def _record_logged(store: ExceptionStore, record: logging.LogRecord) -> None:
    """The log source: ``logger.exception(...)`` and any record with ``exc_info``."""
    exc = record.exc_info[1] if record.exc_info else None
    if exc is not None:
        if (sink := dispatch.session_sink()) is not None:
            sink.on_exception(exc, "log", TEST.get())
        override = None if is_database_exception(exc) else record.getMessage()
        store.record(exc, "log", REQUEST.get(), record.threadName, message_override=override)


def sqlite_holder(ctx: SharpitContext) -> str:
    return f"console:{ctx.context_id}"


def _sqlite_traced(ctx: SharpitContext) -> bool:
    return ctx.capture.sql_trace is not None and ctx.settings.sql_trace_sqlite3_enabled


def _nothing() -> None:
    return None


def wiring_of(ctx: SharpitContext) -> CaptureWiring | None:
    """The context's wiring as this adapter's own type (the engine only knows the ``CaptureHooks`` port)."""
    return cast("CaptureWiring | None", ctx.capture.wiring)


class _WiringHook:
    """One installed capture hook as a ``HookRegistry`` entry: suspends and resumes only itself."""

    def __init__(self, name: str, wiring: CaptureWiring) -> None:
        self.name = name
        self.wiring = wiring

    def suspend(self) -> None:
        self.wiring.suspend_hook(self.name)

    def resume(self) -> None:
        self.wiring.resume_hook(self.name)


class CaptureWiring:
    """Owns which capture hooks are attached for one context; every method is idempotent.

    ``detach`` (lifespan shutdown, ``SharpitHandle.uninstall_capture()``) turns the middleware into a pass-through,
    since a built middleware stack cannot shrink; the next lifespan startup attaches again.
    """

    def __init__(self) -> None:
        self.app: Any = None
        self.middleware_added = False
        self.detached = False
        self.started = False  # startup or first request has run its checks
        self.log_handler: SharpitLogHandler | None = None
        self.log_attached: list[logging.Logger] = []  # every logger the handler was added to, removed on detach
        self._warned: set[str] = set()
        # 0.4.0 slots (lane F), inert until their lanes fill them
        self.on_security_event: Callable[[Scope, int], None] | None = None  # B-security-logs: 401/403 exchanges
        self.span_processor: object | None = None  # A-traces: one lazily re-armed SDK span processor
        self._armed: set[int] = set()  # id() of each CaptureState.attachers entry whose remover is in teardowns
        self.suspended_hooks: set[str] = set()  # registry entries suspended by name (low-footprint)
        self._context: SharpitContext | None = None
        self._lane_of: dict[int, str] = {}  # id() of a lane attacher -> its registry name
        self._removers: dict[int, Callable[[], None]] = {}  # id() of an armed lane attacher -> its remover
        self._actions: dict[str, tuple[Callable[[], None], Callable[[], None]]] = {}  # name -> (suspend, resume)

    def _register(self, ctx: SharpitContext, name: str) -> None:
        ctx.capture.hooks.register(_WiringHook(name, self))

    def add_lane(self, ctx: SharpitContext, name: str, attacher: Callable[[], Callable[[], None] | None]) -> None:
        """A lane's attacher (``CaptureState.attachers``) that is its own registry entry ``name``."""
        ctx.capture.attachers.append(attacher)
        self._lane_of[id(attacher)] = name
        self._actions[name] = (lambda: self._disarm_lane(ctx, name), lambda: self._run_attachers(ctx, name))
        self._register(ctx, name)

    def _register_installed(self, ctx: SharpitContext) -> None:
        """One registry entry per hook installed at install time (the middleware and lanes register themselves)."""
        installed = {
            HOOK_SECURITY_LOG: self.on_security_event is not None,
            HOOK_LOG_HANDLER: self.log_handler is not None,
            HOOK_EXCEPTION_HANDLERS: ctx.capture.exceptions is not None,
            HOOK_SQLA_LISTENERS: True,
            HOOK_SQLITE_LISTENERS: _sqlite_traced(ctx),
        }
        for name, present in installed.items():
            if present:
                self._register(ctx, name)

    def attach_at_install(self, app: Any, ctx: SharpitContext) -> None:
        if self.app is not None:
            return
        self.app = app
        self._context = ctx
        self.on_security_event = attach_security_logs(ctx)  # B-security-logs: buffer, context, 401/403 hook
        store = ctx.capture.exceptions
        if any(_panel_enabled(ctx, p) for p in LOG_PANELS):
            self.log_handler = SharpitLogHandler(
                ctx.masker, ctx.capture.log_tail, application=lambda: application_family(ctx)
            )
            if store is not None:
                self.log_handler.on_exc_info = lambda record: _record_logged(store, record)
            self._attach_non_propagating()  # root waits for the end of startup, so the app's basicConfig() works
        self._register_installed(ctx)
        self._add_actions(ctx)
        self._wrap_handlers(ctx)  # step 2 (spec §6.1), before the middleware: a too-late install still wraps
        self._attach_sql(ctx)  # steps 4a/4b: listeners trace outside requests too, so a too-late install still traces
        self._run_attachers(ctx)
        if not any(_panel_enabled(ctx, p) for p in CAPTURE_PANELS):
            return
        try:
            app.add_middleware(CaptureMiddleware, ctx=ctx)
        except RuntimeError:  # Starlette refuses once the middleware stack is built
            logger.warning("%s", CAPTURE_TOO_LATE)
            if ctx.capture.exchanges is not None:
                ctx.capture.exchanges.unavailable_reason = CAPTURE_TOO_LATE_REASON
            if store is not None:
                store.unavailable_reason = CAPTURE_TOO_LATE_REASON
            return
        self.middleware_added = True
        self._register(ctx, HOOK_CAPTURE_MIDDLEWARE)

    def _wrap_handlers(self, ctx: SharpitContext) -> None:
        store = ctx.capture.exceptions
        handlers = getattr(self.app, "exception_handlers", None)
        if HOOK_EXCEPTION_HANDLERS in self.suspended_hooks:
            return
        if store is not None and isinstance(handlers, dict) and not isinstance(handlers, WrappingHandlers):
            self.app.exception_handlers = WrappingHandlers(cast("dict[Any, Any]", handlers), self, store)

    def on_startup(self, ctx: SharpitContext) -> None:
        self._context = ctx
        self.detached = False
        self._wrap_handlers(ctx)  # again after a shutdown restored the plain dict
        self._first_run(ctx)
        self._attach_logging()  # after the host's startup: its basicConfig()/dictConfig() has run
        self._attach_sql(ctx)  # the lifespan may have imported SQLAlchemy, or a shutdown removed the listeners
        self._run_attachers(ctx)  # likewise for the lanes' hooks

    def on_first_request(self, ctx: SharpitContext) -> None:
        self._first_run(ctx)
        self._attach_logging()
        self._attach_sql(ctx)  # no lifespan: the first request is the last chance to find SQLAlchemy imported
        self._run_attachers(ctx)

    def detach(self, ctx: SharpitContext) -> None:
        sqla.remove(ctx)
        sqlite.detach(sqlite_holder(ctx))
        unwrap_exception_handlers(self.app)
        self._detach_logging()
        teardowns = ctx.capture.teardowns
        while teardowns:  # lanes' listener/processor removers (R17): newest first, once each, a failure stops none
            try:
                teardowns.pop()()
            except Exception as exc:  # noqa: BLE001
                self.hook_failed("teardown", exc)
        self._armed.clear()  # the next startup re-runs every attacher
        self._removers.clear()
        self.detached = True

    def suspend_hook(self, name: str) -> None:
        """Detach the one hook ``name`` (or switch it to its pass-through); idempotent, kept across restarts."""
        if name in self.suspended_hooks or self._context is None:
            return
        self.suspended_hooks.add(name)
        self._actions.get(name, (_nothing, _nothing))[0]()

    def resume_hook(self, name: str) -> None:
        """Re-attach the one hook ``name``; while shut down or uninstalled, the next startup attaches it."""
        if name not in self.suspended_hooks or self._context is None:
            return
        self.suspended_hooks.discard(name)
        if not self.detached:
            self._actions.get(name, (_nothing, _nothing))[1]()

    def _add_actions(self, ctx: SharpitContext) -> None:
        """``(suspend, resume)`` for each install-time registry entry, built once (``add_lane`` adds each lane's). The
        middleware and the security hook read ``suspended_hooks`` at their call sites; a lane (de)arms only itself."""
        self._actions |= {
            HOOK_CAPTURE_MIDDLEWARE: (_nothing, _nothing),
            HOOK_SECURITY_LOG: (_nothing, _nothing),
            HOOK_EXCEPTION_HANDLERS: (lambda: unwrap_exception_handlers(self.app), lambda: self._wrap_handlers(ctx)),
            HOOK_LOG_HANDLER: (self._detach_logging, self._attach_logging),
            HOOK_SQLA_LISTENERS: (lambda: self._suspend_sqla(ctx), lambda: self._attach_sqla(ctx)),
            HOOK_SQLITE_LISTENERS: (lambda: self._suspend_sqlite(ctx), lambda: self._attach_sqlite(ctx)),
        }

    def _suspend_sqla(self, ctx: SharpitContext) -> None:
        ctx.capture.suspended_sources.add("sqlalchemy")
        sqla.remove(ctx)
        if self.detached:  # shut down: nothing routes here until the next startup
            return
        if _sqlite_traced(ctx) and HOOK_SQLITE_LISTENERS not in self.suspended_hooks:
            dispatch.add_context(ctx)  # raw sqlite3 still routes here

    def _suspend_sqlite(self, ctx: SharpitContext) -> None:
        ctx.capture.suspended_sources.add("sqlite3")  # connections opened before stay patched: stop routing them
        sqlite.detach(sqlite_holder(ctx))
        if HOOK_SQLA_LISTENERS in self.suspended_hooks:
            dispatch.remove_context(ctx)

    def _disarm_lane(self, ctx: SharpitContext, name: str) -> None:
        for attacher in ctx.capture.attachers:
            if self._lane_of.get(id(attacher)) == name:
                self._disarm(ctx, attacher)

    def _disarm(self, ctx: SharpitContext, attacher: object) -> None:
        self._armed.discard(id(attacher))
        remover = self._removers.pop(id(attacher), None)
        if remover is None:
            return
        with contextlib.suppress(ValueError):
            ctx.capture.teardowns.remove(remover)
        try:
            remover()
        except Exception as exc:  # noqa: BLE001
            self.hook_failed("teardown", exc)

    def _run_attachers(self, ctx: SharpitContext, lane: str | None = None) -> None:
        """Run each lane attacher (or only ``lane``'s) not yet armed nor suspended; a remover arms it, ``None`` leaves
        it for the next chance."""
        for attacher in ctx.capture.attachers:
            name = self._lane_of.get(id(attacher))
            if id(attacher) in self._armed or name in self.suspended_hooks or (lane is not None and name != lane):
                continue
            try:
                remover = attacher()
            except Exception as exc:  # noqa: BLE001 - the host's startup never fails on sharpit
                self.hook_failed("attacher", exc)
                continue
            if remover is not None:
                self._armed.add(id(attacher))
                self._removers[id(attacher)] = remover
                ctx.capture.teardowns.append(remover)

    def _attach_sql(self, ctx: SharpitContext) -> None:
        """Step 4a (engine discovery) when a database panel is enabled, 4b (statements) when tracing is on."""
        self._attach_sqla(ctx)
        self._attach_sqlite(ctx)

    def _attach_sqla(self, ctx: SharpitContext) -> None:
        if HOOK_SQLA_LISTENERS in self.suspended_hooks:
            return
        ctx.capture.suspended_sources.discard("sqlalchemy")
        try:
            discovery = any(_panel_enabled(ctx, p) for p in sqla.DISCOVERY_PANELS)
            sqla.add(ctx, statements=ctx.capture.sql_trace is not None, discovery=discovery)
        except Exception as exc:  # noqa: BLE001 - the host's startup never fails on sharpit
            self.hook_failed("sql listeners", exc)

    def _attach_sqlite(self, ctx: SharpitContext) -> None:
        if not _sqlite_traced(ctx) or HOOK_SQLITE_LISTENERS in self.suspended_hooks:
            return
        ctx.capture.suspended_sources.discard("sqlite3")
        try:
            dispatch.add_context(ctx)  # raw sqlite3 needs no SQLAlchemy: route its statements here too
            sqlite.attach(sqlite_holder(ctx))
        except Exception as exc:  # noqa: BLE001 - the host's startup never fails on sharpit
            self.hook_failed("sql listeners", exc)

    def log_handler_on_root(self) -> bool:
        return self.log_handler is not None and self.log_handler in logging.root.handlers

    def _detach_logging(self) -> None:
        if self.log_handler is not None:
            for attached in self.log_attached:
                attached.removeHandler(self.log_handler)
        self.log_attached.clear()

    def _attach(self, target: logging.Logger) -> None:
        assert self.log_handler is not None  # noqa: S101 - narrows the type; set before any attach
        if self.log_handler not in target.handlers:
            target.addHandler(self.log_handler)
        if target not in self.log_attached:
            self.log_attached.append(target)

    def _attach_non_propagating(self) -> None:
        """Loggers that never reach root but print somewhere (uvicorn's ``uvicorn`` and ``uvicorn.access``)."""
        for name, candidate in list(logging.root.manager.loggerDict.items()):
            own = name == "sharpit" or name.startswith("sharpit.")
            if isinstance(candidate, logging.Logger) and not candidate.propagate and candidate.handlers and not own:
                self._attach(candidate)

    def _attach_logging(self) -> None:
        if self.log_handler is not None and HOOK_LOG_HANDLER not in self.suspended_hooks:
            self._attach(logging.root)
            self._attach_non_propagating()  # again: uvicorn's dictConfig after install() dropped the handler

    def _first_run(self, ctx: SharpitContext) -> None:
        if self.started:
            return
        self.started = True
        if ctx.capture.loop is None:
            with contextlib.suppress(RuntimeError):  # no running loop: a later startup or request fills it
                ctx.capture.loop = asyncio.get_running_loop()
        if several_workers(os.environ, sys.argv):  # once: started is never reset
            logger.warning("%s", SEVERAL_WORKERS)
        stack = getattr(self.app, "user_middleware", None) or ()
        if self.middleware_added and stack and stack[0].cls is not CaptureMiddleware:
            outer = getattr(stack[0].cls, "__name__", repr(stack[0].cls))
            logger.warning(
                "sharpit request capture misses requests that %s answers itself: it was added after "
                "sharpit.install(app). Call sharpit.install(app) last, after every add_middleware().",
                outer,
            )

    def hook_failed(self, hook: str, exc: BaseException) -> None:
        """One warning per hook name; the exception text is not logged (it may carry request data)."""
        if hook not in self._warned:
            self._warned.add(hook)
            logger.warning("sharpit capture hook %s failed (%s); capture continues", hook, type(exc).__name__)


class CaptureMiddleware:
    def __init__(self, app: ASGIApp, ctx: SharpitContext) -> None:
        self.app = app
        self.ctx = ctx

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        wiring = wiring_of(self.ctx)
        if (
            scope["type"] != "http"
            or wiring is None
            or wiring.detached
            or HOOK_CAPTURE_MIDDLEWARE in wiring.suspended_hooks
        ):
            await self.app(scope, receive, send)
            return
        buffer = self.ctx.capture.exchanges
        try:
            if not wiring.started:
                wiring.on_first_request(self.ctx)
            if under(route_path(scope), self.ctx.settings.path):  # sharpit's own traffic: counted, never captured
                if buffer is not None:
                    buffer.count_hidden_self()
                await self.app(scope, receive, send)
                return
            extensions: dict[str, Any] = scope.get("extensions") or {}
            if not extensions.get(PROBE_EXTENSION) and any(
                k == PROBE_HEADER for k, _ in scope["headers"]
            ):  # only sharpit's probe may carry the header (spec §7.11)
                scope = {**scope, "headers": [h for h in scope["headers"] if h[0] != PROBE_HEADER]}
            started_epoch_ns = time.time_ns()
            root_path = scope.get("root_path", "")
            info = RequestInfo(
                new_request_id(),
                self.ctx.context_id,
                scope["method"],
                self.ctx.masker.mask_path(scope["path"]),
                None,
                time.perf_counter_ns(),
                None,
                scope=scope,
            )
        except Exception as exc:  # noqa: BLE001 - a capture failure never changes the host's response
            wiring.hook_failed("request start", exc)
            await self.app(scope, receive, send)
            return
        sqla.note_request_captured()

        status: int | None = None
        response_headers: list[tuple[bytes, bytes]] = []
        size = 0
        end_ns: int | None = None
        disconnected = False

        async def capture_receive() -> Message:
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
            return message

        async def capture_send(message: Message) -> None:
            nonlocal status, response_headers, size, end_ns
            try:
                kind = message["type"]
                if kind == "http.response.start":
                    status = message["status"]
                    response_headers = list(message.get("headers", ()))
                elif kind == "http.response.body":
                    size += len(message.get("body", b""))
                    if not message.get("more_body", False):
                        end_ns = time.perf_counter_ns()
            except Exception as exc:  # noqa: BLE001
                wiring.hook_failed("response", exc)
            await send(message)  # every chunk goes out as it comes: nothing is buffered

        token = REQUEST.set(info)
        failed = cancelled = False
        raised: Exception | None = None
        try:
            await self.app(scope, capture_receive, capture_send)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            failed, raised = True, exc
            if (sink := dispatch.session_sink()) is not None:
                sink.on_escaped(exc)
            raise
        finally:
            sent = cast("int | None", status)  # set by capture_send; pyright cannot see the closure
            security = None if HOOK_SECURITY_LOG in wiring.suspended_hooks else wiring.on_security_event
            if sent in (401, 403) and security is not None:  # before reset: REQUEST names it (R12)
                try:
                    security(scope, sent)
                except Exception as exc:  # noqa: BLE001
                    wiring.hook_failed("security event", exc)
            REQUEST.reset(token)
            try:
                finished = end_ns or time.perf_counter_ns()
                info.finished_ns = finished
                info.endpoint = _endpoint_name(scope.get("endpoint"))
                store = self.ctx.capture.exceptions
                if store is not None:
                    if raised is not None:
                        store.record(raised, "request", info, threading.current_thread().name)
                    store.forget_request(info.id)
                if buffer is not None:
                    if status is not None:  # the status that went out is the status; anything after is an error
                        recorded, error = status, failed or cancelled or disconnected
                    elif failed:  # ServerErrorMiddleware sends the 500 after us
                        recorded, error = 500, True
                    elif disconnected or cancelled:  # nginx's "client closed request"
                        recorded, error = 499, False
                    else:  # returned without a response: the server answers 500
                        recorded, error = 500, True
                    buffer.add(
                        exchange_row(
                            self.ctx.masker,
                            request_id=info.id,
                            started_epoch_ns=started_epoch_ns,
                            method=info.method,
                            path=scope["path"],
                            query_string=scope.get("query_string", b""),
                            status=recorded,
                            duration_ms=(finished - info.started_ns) // 1_000_000,
                            size=size,
                            client=scope.get("client"),
                            user=scope.get("user"),
                            request_headers=scope["headers"],
                            response_headers=response_headers,
                            error=error,
                            endpoint=info.endpoint,
                            finished_epoch_ns=started_epoch_ns + finished - info.started_ns,
                            route=_route_template(scope, root_path, wiring.app),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                wiring.hook_failed("request end", exc)
