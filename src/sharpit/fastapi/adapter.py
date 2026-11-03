"""``install()``: mount the sharpit sub-app first in the host router, behind its own guard middleware."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from functools import partial
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Match, Mount
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sharpit.engine import guard, sqla, tools
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture import activity, route_path
from sharpit.engine.capture.logtail import log_events
from sharpit.engine.collectors import alembic
from sharpit.engine.context import SharpitContext
from sharpit.engine.headers import security_headers
from sharpit.engine.paging import parse_int_param
from sharpit.fastapi.capture import LOG_TAIL_DETACHED_REASON, wiring_of
from sharpit.fastapi.http import error, json_response
from sharpit.settings import SharpitSettings

__all__ = [
    "GuardMiddleware",
    "SharpitContext",
    "SharpitHandle",
    "SharpitMount",
    "install",
    "_routes",
    "_bad_request",
    "_json_http_error",
    "_not_found",
    "_ASSETS",
    "_SMALL_BODY_CAP",
    "_STATIC",
    "_TRUSTED_KEY",
    "_json_or_none",
    "_page",
    "_read_capped",
    "_toggle_value",
    "available_reasons",
    "log_events",
]

logger = logging.getLogger("sharpit")

_STATIC = Path(__file__).resolve().parent.parent / "ui" / "static"
_ASSETS = _STATIC / "assets"
_TRUSTED_KEY = "sharpit.trusted"
_SMALL_BODY_CAP = 4096  # bytes: per-endpoint cap for the toggle and logger-level bodies
_Lifespan = Callable[[Any], AbstractAsyncContextManager[Any]]


@dataclass
class SharpitHandle:
    settings: SharpitSettings
    activation: ActivationStatus
    context: SharpitContext
    original_lifespan: _Lifespan

    def uninstall_capture(self) -> None:
        """Detach every capture hook, as lifespan shutdown does (for tests and apps run without lifespan)."""
        if (wiring := wiring_of(self.context)) is not None:
            wiring.detach(self.context)


class SharpitMount(Mount):
    """A ``Mount`` that also owns the bare ``{path}`` (any method), so it reaches the sub-app and its guard.

    Equivalent to the path regex ``^{path}(?:/(?P<path>.*))?$``; ``matches`` is overridden because Starlette's
    ``Mount.matches`` cannot handle the optional ``path`` group being absent.
    """

    sharpit_handle: SharpitHandle | None = None  # set by install(): a second install() on the same app returns it

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child = super().matches(scope)
        if match is Match.NONE and scope["type"] in ("http", "websocket") and route_path(scope) == self.path:
            root_path = scope.get("root_path", "")
            child = {
                "path_params": dict(scope.get("path_params", {})),
                "app_root_path": scope.get("app_root_path", root_path),
                "root_path": root_path + self.path,
                "endpoint": self.app,
            }
            return Match.FULL, child
        return match, child


def _header_map(scope: Scope) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for key, value in scope["headers"]:
        values.setdefault(key.decode("latin-1").lower(), []).append(value.decode("latin-1"))
    return values


class GuardMiddleware:
    """Runs ``decide_guard`` for every request under the mount and fills in security headers on every response."""

    def __init__(self, app: ASGIApp, ctx: SharpitContext) -> None:
        self.app = app
        self.ctx = ctx
        self.api_prefix = ctx.settings.api_path[len(ctx.settings.path) :]

    async def _send_with_headers(self, send: Send, message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = MutableHeaders(scope=message)
            # a response with its own CSP owns its whole policy (assets keep no Pragma); else fill in what is
            # missing, one header at a time, so a header set downstream is never duplicated
            if "content-security-policy" not in headers:
                for name, value in security_headers("api"):
                    if name not in headers:
                        headers.append(name, value)
        await send(message)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            if scope["type"] == "websocket":  # sharpit has no websocket endpoints: refuse before any guard question
                await send({"type": "websocket.close", "code": 1000, "reason": ""})
            return
        denial = self._decide(scope)
        if denial is not None:
            response = json_response(denial.body, denial.status)
            for name, value in denial.headers:
                response.headers[name] = value
            await response(scope, receive, send)
            return

        await self.app(scope, receive, partial(self._send_with_headers, send))

    def _decide(self, scope: Scope) -> guard.Denial | None:
        values = _header_map(scope)
        # Duplicates are ambiguous (which one did the host app read?), so fail closed with the check that consumes them.
        if len(values.get("host", ())) > 1:
            return guard.Denial(403, {"error": guard.MESSAGE_DISALLOWED_HOST})
        if len(values.get("origin", ())) > 1 or len(values.get("sec-fetch-site", ())) > 1:
            return guard.Denial(403, {"error": guard.MESSAGE_CROSS_SITE})
        headers = {k: ("; " if k == "cookie" else ", ").join(v) for k, v in values.items()}
        sub_path = route_path(scope)
        api_sub_path = None
        if sub_path == self.api_prefix or sub_path.startswith(self.api_prefix + "/"):
            api_sub_path = sub_path[len(self.api_prefix) :]
        client = scope.get("client")
        facts = guard.RequestFacts(
            scope["method"],
            client[0] if client else None,
            headers,
            api_sub_path,
            scope.get("scheme", "http"),
            bool(scope.get("extensions", {}).get("sharpit.probe")),
        )
        settings = self.ctx.settings
        gateway = (
            self.ctx.lazy("gateway", guard.detect_container_gateway)
            if settings.trust_container_gateway.upper() != "OFF"
            else None
        )
        scope[_TRUSTED_KEY] = guard.is_trusted_source(facts, settings, gateway)
        return guard.decide_guard(facts, settings, self.ctx.token, gateway)


# Each 0.2.0 task replaces its own entry with the panel's real availability (spec §13.1).
_NOT_BUILT: tuple[str, ...] = ()


def available_reasons(ctx: SharpitContext) -> dict[str, str | None]:
    """Panel id -> why it is unavailable; an id that is absent or None is available."""
    reasons: dict[str, str | None] = dict.fromkeys(_NOT_BUILT, "Not built yet")
    exchanges = ctx.capture.exchanges
    reasons["http-exchanges"] = exchanges.unavailable_reason if exchanges is not None else None
    wiring = wiring_of(ctx)
    on_root = ctx.capture.log_tail is None or (wiring is not None and wiring.log_handler_on_root())
    reasons["log-tail"] = None if on_root else LOG_TAIL_DETACHED_REASON
    store = ctx.capture.exceptions
    reasons["exceptions"] = store.unavailable_reason if store is not None else None
    reasons["sql-trace"] = tools.sql_trace_unavailable_reason(ctx)
    reasons["activity"] = activity.unavailable_reason(ctx)
    reasons["alembic"] = alembic.unavailable_reason(ctx)
    reasons["database-connection-pools"] = sqla.unavailable_reason()
    return reasons


def _toggle_value(raw: bytes) -> object:
    """``enabled`` of a toggle body: None (flip) for an empty body, JSON ``null`` or a missing/null key; ``0`` (refused)
    for unparsable JSON or a non-object (parsed inline: a JSON ``null`` body flips, as BootUI ``request == null``)."""
    try:
        body: object = json.loads(raw) if raw.strip() else None
    except (ValueError, RecursionError):
        return 0
    return None if body is None else cast("dict[str, Any]", body).get("enabled") if isinstance(body, dict) else 0


async def _read_capped(request: Request, cap: int) -> bytes | None:
    """The body, or ``None`` once it exceeds ``cap`` bytes (by ``Content-Length``, else after ``cap + 1`` read)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > cap:
        return None
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > cap:
            return None
    return bytes(raw)


def _json_or_none(raw: bytes) -> object:
    try:
        return json.loads(raw)
    except (ValueError, RecursionError):  # deep nesting raises RecursionError
        return None


def _page(request: Request) -> tuple[int | None, int | None]:
    """``offset`` and ``limit`` query parameters; a non-integer raises ``BadRequest`` (rendered as 400)."""
    params = request.query_params
    return parse_int_param(params.get("offset"), "offset"), parse_int_param(params.get("limit"), "limit")


async def _bad_request(_request: Request, exc: Exception) -> Response:  # NOSONAR - Starlette coroutine handler
    return error(400, str(exc))


async def _json_http_error(_request: Request, exc: Exception) -> Response:  # NOSONAR - Starlette coroutine handler
    """404/405 inside the active sub-app answer in the API's JSON error shape (405 keeps its ``Allow`` header)."""
    assert isinstance(exc, HTTPException)
    response = error(exc.status_code, "Not Found" if exc.status_code == 404 else "Method Not Allowed")
    response.headers.update(exc.headers or {})
    return response


async def _not_found(scope: Scope, receive: Receive, send: Send) -> None:  # NOSONAR - ASGI callable contract
    """Inactive sharpit: the host's own exception handling renders this, so the 404 is the host's 404."""
    if scope["type"] == "websocket":  # as the host router does for an unknown websocket path
        await send({"type": "websocket.close", "code": 1000, "reason": ""})
        return
    raise HTTPException(404)


from sharpit.fastapi.install import install as install  # noqa: E402 - public adapter compatibility facade


def _routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]:
    from sharpit.fastapi.routes import build_routes
    from sharpit.fastapi.routes.dismissed_findings import build_routes as finding_routes

    routes = build_routes(ctx, host_app)
    # shortcut: spliced after the dismissed-rules routes because routes/__init__.py is not D1's file; move the call
    # into build_routes() when the lanes are merged
    rules = f"{ctx.settings.api_path[len(ctx.settings.path) :]}/dismissed-rules"
    at = 1 + max((i for i, r in enumerate(routes) if getattr(r, "path", "").startswith(rules)), default=len(routes) - 1)
    routes[at:at] = finding_routes(ctx)
    return _with_drift_routes(routes, ctx)


def _with_drift_routes(routes: list[BaseRoute], ctx: SharpitContext) -> list[BaseRoute]:
    """The 2.2.0 capture routes (lane D2) go first: a literal path such as ``/exceptions/caught`` must win over
    ``/exceptions/{id}``, and a drift route with the same path and methods replaces the base one."""
    import sharpit.fastapi.routes as package
    from sharpit.fastapi.routes import exceptions, http_exchanges

    engine_activity = package.activity
    activity = import_module("sharpit.fastapi.routes.activity")
    # shortcut: importing the submodule rebinds the package's ``activity`` global, the engine module routes/__init__.py
    # calls; put it back. Rename the module (or move these routes into routes/__init__.py) once that file may change.
    package.activity = engine_activity
    drift = [route for module in (activity, http_exchanges, exceptions) for route in module.build_routes(ctx)]

    def key(route: BaseRoute) -> tuple[object, frozenset[str]]:
        return getattr(route, "path", None), frozenset(getattr(route, "methods", None) or ())

    replaced = {key(route) for route in drift}
    return [*drift, *(route for route in routes if key(route) not in replaced)]
