"""Exception capture and route-handler wrapping for the FastAPI adapter."""

from __future__ import annotations

import functools
import logging
import re
import sys
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from starlette._utils import is_async_callable  # pyright: ignore[reportPrivateUsage]  # Starlette's own dispatch test
from starlette.exceptions import HTTPException
from starlette.routing import Mount, compile_path
from starlette.types import Scope

from sharpit.engine.capture import route_path
from sharpit.engine.capture.correlation import REQUEST, TEST
from sharpit.engine.sources import dispatch
from sharpit.engine.sqltext import is_database_exception

if TYPE_CHECKING:
    from sharpit.engine.capture.correlation import RequestInfo
    from sharpit.engine.capture.exceptions import ExceptionStore
    from sharpit.engine.context import SharpitContext
    from sharpit.fastapi.capture import CaptureWiring

HOOK_EXCEPTION_HANDLERS = "exception-handlers"
MAX_MOUNT_DEPTH = 32  # a sub-app mounted inside itself must not loop the walk


def endpoint_name(endpoint: object) -> str | None:
    if endpoint is None:
        return None
    qualname = getattr(endpoint, "__qualname__", type(endpoint).__name__)
    return f"{getattr(endpoint, '__module__', None) or '?'}:{qualname}"


def validation_error(exc: BaseException) -> bool:
    cls = getattr(sys.modules.get("fastapi.exceptions"), "RequestValidationError", None)  # no import: Pydantic 1 safe
    return isinstance(cls, type) and isinstance(exc, cls)


def record_exception(
    store: ExceptionStore,
    exc: Exception,
    source: str,
    info: RequestInfo | None,
    thread: str | None,
    ctx: SharpitContext | None,
    host_app: object,
) -> None:
    if not validation_error(exc):
        store.record(exc, source, info, thread)
        return
    _record_binding_exception(store, exc, source, info, thread, ctx, host_app)


def _record_binding_exception(
    store: ExceptionStore,
    exc: Exception,
    source: str,
    info: RequestInfo | None,
    thread: str | None,
    ctx: SharpitContext | None,
    host_app: object,
) -> None:
    try:
        from sharpit.fastapi.binding_diagnostics import route_for_scope, validation_details
    except ImportError:  # Pydantic 1 hosts: no binding diagnostics, the exception is still recorded
        store.record(exc, source, info, thread)
        return

    full = ctx is not None and ctx.settings.expose_values.value == "FULL"
    template = (
        route_template(info.scope, str(info.scope.get("root_path", "")), host_app)
        if info is not None and info.scope is not None
        else None
    )
    record_info = info
    if template is not None and info is not None and not full:
        record_info = replace(info, path=template)
    route = route_for_scope(info.scope if info is not None else None, host_app)
    message, diagnostics, truncated = validation_details(exc, route, full)
    store.record(
        exc,
        source,
        record_info,
        thread,
        message_override=message,
        message_override_always=True,
        binding_diagnostics=diagnostics,
        binding_diagnostics_truncated=truncated,
    )


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


def route_template(scope: Scope, root_path: str, app: object) -> str | None:
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
    skipped = [getattr(fastapi_errors, "WebSocketRequestValidationError", None)]
    return not any(isinstance(c, type) and issubclass(key, c) for c in skipped)


def _wrap_handler(original: Callable[..., Any], wiring: CaptureWiring, store: ExceptionStore) -> Callable[..., Any]:
    def record(conn: Any, exc: Exception) -> None:
        if wiring.detached or HOOK_EXCEPTION_HANDLERS in wiring.suspended_hooks:  # the built stack keeps this wrapper
            return
        try:
            validation = validation_error(exc)
            if (sink := dispatch.session_sink()) is not None and not validation:
                sink.on_exception(exc, "handler", TEST.get())
            info = REQUEST.get()
            if info is not None and info.endpoint is None:
                info.endpoint = endpoint_name(conn.scope.get("endpoint"))
            record_exception(
                store,
                exc,
                "handler",
                info,
                threading.current_thread().name,
                wiring._context,  # pyright: ignore[reportPrivateUsage]
                wiring.app,  # pyright: ignore[reportPrivateUsage]
            )
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


def record_logged(store: ExceptionStore, record: logging.LogRecord, ctx: SharpitContext | None = None) -> None:
    """The log source: ``logger.exception(...)`` and any record with ``exc_info``."""
    exc = record.exc_info[1] if record.exc_info else None
    if not isinstance(exc, Exception):
        return
    sink = dispatch.session_sink()
    validation = validation_error(exc)
    if sink is not None and not validation:
        sink.on_exception(exc, "log", TEST.get())
    if validation:
        _record_logged_validation(store, record, exc, ctx)
        return
    override = None if is_database_exception(exc) else record.getMessage()
    store.record(exc, "log", REQUEST.get(), record.threadName, message_override=override)


def _record_logged_validation(
    store: ExceptionStore, record: logging.LogRecord, exc: Exception, ctx: SharpitContext | None
) -> None:
    wiring = cast("CaptureWiring | None", ctx.capture.wiring) if ctx is not None else None
    record_exception(store, exc, "log", REQUEST.get(), record.threadName, ctx, wiring.app if wiring else None)
