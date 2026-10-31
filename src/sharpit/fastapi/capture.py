"""Request capture on the host app (spec §6.1, §7.1, §9): a pure ASGI middleware and the wiring that owns the hooks.

Pure ASGI, never ``BaseHTTPMiddleware``: that runs the endpoint in another task (contextvars set downstream are
invisible here) and buffers streaming bodies. Only ``receive`` and ``send`` are wrapped.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sharpit.engine.capture import route_path, under
from sharpit.engine.capture.correlation import REQUEST, RequestInfo, new_request_id
from sharpit.engine.capture.exchanges import exchange_row
from sharpit.engine.capture.logtail import SharpitLogHandler

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit")

CAPTURE_TOO_LATE = "request capture unavailable: install() ran after the app started"
CAPTURE_TOO_LATE_REASON = "Request capture is unavailable: install() ran after the app started"
CAPTURE_PANELS = ("http-exchanges", "exceptions", "sql-trace", "activity")  # any of them enabled needs the middleware
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

    def attach_at_install(self, app: Any, ctx: SharpitContext) -> None:
        if self.app is not None:
            return
        self.app = app
        if any(ctx.settings.panels[p].enabled for p in LOG_PANELS):
            self.log_handler = SharpitLogHandler(ctx.masker, ctx.capture.log_tail)
            self._attach_non_propagating()  # root waits for the end of startup, so the app's basicConfig() works
        if not any(ctx.settings.panels[p].enabled for p in CAPTURE_PANELS):
            return
        try:
            app.add_middleware(CaptureMiddleware, ctx=ctx)
        except RuntimeError:  # Starlette refuses once the middleware stack is built
            logger.warning("%s", CAPTURE_TOO_LATE)
            if ctx.capture.exchanges is not None:
                ctx.capture.exchanges.unavailable_reason = CAPTURE_TOO_LATE_REASON
            return
        self.middleware_added = True
        # Tasks 4-5: exception-handler wrapping and SQL listeners attach here

    def on_startup(self, ctx: SharpitContext) -> None:
        self.detached = False
        self._first_run(ctx)
        self._attach_logging()  # after the host's startup: its basicConfig()/dictConfig() has run
        # Tasks 4-5: SQL listener retry

    def on_first_request(self, ctx: SharpitContext) -> None:
        self._first_run(ctx)
        self._attach_logging()

    def detach(self, ctx: SharpitContext) -> None:
        del ctx  # Tasks 4-5 remove the exception-handler wrappers and SQL listeners they attached
        if self.log_handler is not None:
            for attached in self.log_attached:
                attached.removeHandler(self.log_handler)
        self.log_attached.clear()
        self.detached = True

    def log_handler_on_root(self) -> bool:
        return self.log_handler is not None and self.log_handler in logging.root.handlers

    def _attach(self, target: logging.Logger) -> None:
        assert self.log_handler is not None
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
        if self.log_handler is not None:
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
        wiring = self.ctx.capture.wiring
        if scope["type"] != "http" or wiring is None or wiring.detached:
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
            info = RequestInfo(
                new_request_id(),
                self.ctx.context_id,
                scope["method"],
                self.ctx.masker.mask_path(scope["path"]),
                None,
                time.perf_counter_ns(),
                None,
            )
        except Exception as exc:  # noqa: BLE001 - a capture failure never changes the host's response
            wiring.hook_failed("request start", exc)
            await self.app(scope, receive, send)
            return

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
        try:
            await self.app(scope, capture_receive, capture_send)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            failed = True
            raise
        finally:
            REQUEST.reset(token)
            try:
                finished = end_ns or time.perf_counter_ns()
                info.finished_ns = finished
                info.endpoint = _endpoint_name(scope.get("endpoint"))
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
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                wiring.hook_failed("request end", exc)
