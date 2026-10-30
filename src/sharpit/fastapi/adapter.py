"""``install()``: mount the sharpit sub-app first in the host router, behind its own guard middleware."""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import BaseRoute, Match, Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sharpit.engine import guard
from sharpit.engine.activation import ActivationStatus, active_profiles, decide
from sharpit.engine.collectors.overview import overview_dto
from sharpit.engine.context import SharpitContext
from sharpit.engine.headers import security_headers
from sharpit.engine.masking import Exposure
from sharpit.engine.panels import panels_report
from sharpit.fastapi.http import json_response
from sharpit.fastapi.introspector import FastApiIntrospector
from sharpit.fastapi.signals import dev_server_signal
from sharpit.settings import load_settings

__all__ = ["GuardMiddleware", "SharpitContext", "SharpitHandle", "SharpitMount", "install"]

logger = logging.getLogger("sharpit")

_STATIC = Path(__file__).resolve().parent.parent / "ui" / "static"
_ASSETS = _STATIC / "assets"
_TRUSTED_KEY = "sharpit.trusted"
_Lifespan = Callable[[Any], AbstractAsyncContextManager[Any]]


@dataclass
class SharpitHandle:
    settings: Any
    activation: ActivationStatus
    context: SharpitContext
    original_lifespan: _Lifespan


class SharpitMount(Mount):
    """A ``Mount`` that also owns the bare ``{path}`` (any method), so it reaches the sub-app and its guard.

    Equivalent to the path regex ``^{path}(?:/(?P<path>.*))?$``; ``matches`` is overridden because Starlette's
    ``Mount.matches`` cannot handle the optional ``path`` group being absent.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child = super().matches(scope)
        if match is Match.NONE and scope["type"] in ("http", "websocket") and _route_path(scope) == self.path:
            root_path = scope.get("root_path", "")
            child = {
                "path_params": dict(scope.get("path_params", {})),
                "app_root_path": scope.get("app_root_path", root_path),
                "root_path": root_path + self.path,
                "endpoint": self.app,
            }
            return Match.FULL, child
        return match, child


def _route_path(scope: Scope) -> str:
    """Path below ``root_path`` (as Starlette's private ``get_route_path``): ``""`` for the bare mount path."""
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if root_path and (path == root_path or path.startswith(root_path + "/")):
        return path[len(root_path) :]
    return path


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

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "content-security-policy" not in headers:
                    for name, value in security_headers("api"):
                        headers.append(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _decide(self, scope: Scope) -> guard.Denial | None:
        values = _header_map(scope)
        # Duplicates are ambiguous (which one did the host app read?), so fail closed with the check that consumes them.
        if len(values.get("host", ())) > 1:
            return guard.Denial(403, {"error": guard.MESSAGE_DISALLOWED_HOST})
        if len(values.get("origin", ())) > 1 or len(values.get("sec-fetch-site", ())) > 1:
            return guard.Denial(403, {"error": guard.MESSAGE_CROSS_SITE})
        headers = {k: ("; " if k == "cookie" else ", ").join(v) for k, v in values.items()}
        route_path = _route_path(scope)
        api_sub_path = None
        if route_path == self.api_prefix or route_path.startswith(self.api_prefix + "/"):
            api_sub_path = route_path[len(self.api_prefix) :]
        client = scope.get("client")
        facts = guard.RequestFacts(scope["method"], client[0] if client else None, headers, api_sub_path)
        settings = self.ctx.settings
        gateway = (
            self.ctx.lazy("gateway", guard.detect_container_gateway)
            if settings.trust_container_gateway.upper() != "OFF"
            else None
        )
        scope[_TRUSTED_KEY] = guard.is_trusted_source(facts, settings, gateway)
        return guard.decide_guard(facts, settings, self.ctx.token, gateway)


def _routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def shell(_request: Request) -> Response:
        html = ctx.lazy("shell", lambda: (_STATIC / "index.html").read_bytes())
        return Response(html, media_type="text/html; charset=utf-8", headers=dict(security_headers("shell")))

    def asset(request: Request) -> Response:
        name: str = request.path_params["file"]
        target = (_ASSETS / name).resolve()
        if target.parent != _ASSETS.resolve() or not target.is_file():
            raise HTTPException(404)
        return FileResponse(target, headers=dict(security_headers("asset")))

    def session(request: Request) -> Response:
        # Reached only once the guard has authorised the request (trusted source, bearer or session cookie).
        response = Response(status_code=204, headers=dict(security_headers("api")))
        if not request.scope.get(_TRUSTED_KEY, False) and ctx.token:
            root = request.scope.get("app_root_path", "")
            secure = "; Secure" if request.url.scheme == "https" else ""
            cookie = f"{guard.SESSION_COOKIE}={ctx.token}; Path={root}{settings.api_path}; HttpOnly; SameSite=Strict"
            response.headers.append("set-cookie", cookie + secure)
        return response

    def panels(_request: Request) -> Response:
        flags = {pid: (p.enabled, p.read_only) for pid, p in settings.panels.items()}
        return json_response(panels_report(settings.read_only, flags, {}))

    def overview(request: Request) -> Response:
        return json_response(overview_dto(ctx, request.scope))

    return [
        Route("/", shell, methods=["GET"]),
        Route("/assets/{file}", asset, methods=["GET"]),
        Route(f"{api}/auth/session", session, methods=["POST"]),
        Route(f"{api}/panels", panels, methods=["GET"]),
        Route(f"{api}/overview", overview, methods=["GET"]),
    ]


async def _not_found(scope: Scope, receive: Receive, send: Send) -> None:
    """Inactive sharpit: the host's own exception handling renders this, so the 404 is the host's 404."""
    raise HTTPException(404)


def _banner(ctx: SharpitContext, generated: bool) -> str:
    lines = [f"sharpit active at {ctx.settings.path}/ ({ctx.activation.reason})"]
    if generated:
        lines.append(f"sharpit authentication token (generated for this process): {ctx.token}")
    return "\n".join(lines)


def install(app: Any, *, settings: Sequence[object] = (), **options: Any) -> SharpitHandle:
    sharpit_settings = load_settings(options, os.environ)
    profiles = tuple(active_profiles(sharpit_settings, os.environ))
    activation = decide(sharpit_settings, profiles, dev_server_signal(sys.argv))
    token, generated = guard.resolve_token(sharpit_settings) if activation.enabled else (None, False)
    ctx = SharpitContext(
        sharpit_settings,
        activation,
        FastApiIntrospector(app),
        token=token,
        profiles=profiles,
        app_settings=tuple(settings),
    )
    router = app.router
    original: _Lifespan = router.lifespan_context
    handle = SharpitHandle(sharpit_settings, activation, ctx, original)

    if not activation.enabled:
        router.routes.insert(0, SharpitMount(sharpit_settings.path, app=_not_found, name="sharpit"))
        logger.info("sharpit inactive: %s", activation.reason)
        return handle

    @asynccontextmanager
    async def lifespan(host_app: Any) -> AsyncGenerator[Any]:
        async with original(host_app) as state:
            if ctx.startup_time_ms is None:
                ctx.startup_time_ms = round((time.monotonic() - ctx.installed_at) * 1000)
            yield state

    router.lifespan_context = lifespan
    sub_app = Starlette(routes=_routes(ctx), middleware=[Middleware(GuardMiddleware, ctx=ctx)])
    router.routes.insert(0, SharpitMount(sharpit_settings.path, app=sub_app, name="sharpit"))
    if sharpit_settings.show_banner:
        print(_banner(ctx, generated), file=sys.stderr)
    if sharpit_settings.expose_values is Exposure.FULL:
        logger.warning("SHARPIT_EXPOSE_VALUES=FULL: sharpit shows configuration values unmasked, secrets included")
    return handle
