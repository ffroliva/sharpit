"""``install()``: mount the sharpit sub-app first in the host router, behind its own guard middleware."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections.abc import AsyncGenerator, Callable, Iterable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import BaseRoute, Match, Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sharpit.engine import guard, tools
from sharpit.engine.activation import ActivationStatus, active_profiles, decide
from sharpit.engine.capture import route_path
from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.logtail import LogTailBuffer, log_events
from sharpit.engine.capture.streams import StreamSlots
from sharpit.engine.collectors.beans import beans_report
from sharpit.engine.collectors.config import config_report
from sharpit.engine.collectors.loggers import loggers_report, set_level
from sharpit.engine.collectors.mappings import mappings_flat
from sharpit.engine.collectors.overview import overview_dto
from sharpit.engine.collectors.vulns.service import VulnerabilityService
from sharpit.engine.context import SharpitContext
from sharpit.engine.headers import security_headers
from sharpit.engine.mcp import McpServer, payload_too_large
from sharpit.engine.paging import BadRequest, parse_int_param
from sharpit.engine.panels import panels_report
from sharpit.engine.singleflight import ActionBusy
from sharpit.fastapi.capture import LOG_TAIL_DETACHED_REASON, CaptureWiring
from sharpit.fastapi.http import error, json_response
from sharpit.fastapi.introspector import FastApiIntrospector
from sharpit.fastapi.signals import dev_server_signal
from sharpit.fastapi.sse import sse_response
from sharpit.settings import SharpitSettings, load_settings, parse_mode

__all__ = ["GuardMiddleware", "SharpitContext", "SharpitHandle", "SharpitMount", "install"]

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
        if self.context.capture.wiring is not None:
            self.context.capture.wiring.detach(self.context)


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
        sub_path = route_path(scope)
        api_sub_path = None
        if sub_path == self.api_prefix or sub_path.startswith(self.api_prefix + "/"):
            api_sub_path = sub_path[len(self.api_prefix) :]
        client = scope.get("client")
        facts = guard.RequestFacts(
            scope["method"], client[0] if client else None, headers, api_sub_path, scope.get("scheme", "http")
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
_NOT_BUILT = (
    "activity",
    "exceptions",
    "sql-trace",
    "alembic",
    "database-connection-pools",
    "health",
    "threads",
    "rest-api",
    "http-probe",
)


def available_reasons(ctx: SharpitContext) -> dict[str, str | None]:
    """Panel id -> why it is unavailable; an id that is absent or None is available."""
    reasons: dict[str, str | None] = dict.fromkeys(_NOT_BUILT, "Not built yet")
    exchanges = ctx.capture.exchanges
    reasons["http-exchanges"] = exchanges.unavailable_reason if exchanges is not None else None
    wiring = ctx.capture.wiring
    on_root = ctx.capture.log_tail is None or (wiring is not None and wiring.log_handler_on_root())
    reasons["log-tail"] = None if on_root else LOG_TAIL_DETACHED_REASON
    return reasons


def _routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def api_path(request: Request) -> str:
        """The API prefix as the client reached it: ``root_path`` already holds any mount prefix plus ``path``."""
        return request.scope.get("root_path", "") + api

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
            secure = "; Secure" if request.url.scheme == "https" else ""
            cookie = f"{guard.SESSION_COOKIE}={ctx.token}; Path={api_path(request)}; HttpOnly; SameSite=Strict"
            response.headers.append("set-cookie", cookie + secure)
        return response

    def panels(_request: Request) -> Response:
        flags = {pid: (p.enabled, p.read_only) for pid, p in settings.panels.items()}
        return json_response(panels_report(settings.read_only, flags, available_reasons(ctx)))

    def overview(request: Request) -> Response:
        return json_response(overview_dto(ctx, request.scope))

    def config(request: Request) -> Response:
        params = request.query_params
        offset, limit = _page(request)
        overrides_only = params.get("overridesOnly", "").strip().lower() == "true"
        return json_response(config_report(ctx, params.get("q"), params.get("source"), overrides_only, offset, limit))

    def loggers(request: Request) -> Response:
        return json_response(loggers_report(request.query_params.get("q"), *_page(request)))

    def mappings(request: Request) -> Response:
        return json_response(mappings_flat(ctx, request.query_params.get("q"), *_page(request)))

    def beans(request: Request) -> Response:
        params = request.query_params
        return json_response(beans_report(ctx, params.get("q"), params.get("classification"), *_page(request)))

    def http_exchanges(request: Request) -> Response:
        params = request.query_params
        offset, limit = _page(request)
        return json_response(
            tools.http_exchanges_report(
                ctx, params.get("q"), params.get("method"), params.get("statusClass"), offset, limit
            )
        )

    def log_tail_recent(_request: Request) -> Response:
        return json_response(tools.log_tail_lines(ctx))

    async def log_tail_stream(request: Request) -> Response:
        buffer = ctx.capture.log_tail
        if buffer is None:  # the panel gate answers first; only a disabled panel has no buffer
            raise HTTPException(404)
        # Last-Event-ID first: an automatic reconnect sends it while the URL still carries a manual ?after=
        last = request.headers.get("last-event-id") or request.query_params.get("after")
        return sse_response(ctx, log_events(buffer, buffer.resume_point(last)))

    def vulnerability_service() -> VulnerabilityService:
        return tools.vulnerability_service(ctx)

    def vulnerabilities(_request: Request) -> Response:
        return json_response(vulnerability_service().report())

    def vulnerabilities_scan(_request: Request) -> Response:
        try:
            return json_response(vulnerability_service().scan())
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    def dismissed_rules(_request: Request) -> Response:
        return json_response({"dismissed": vulnerability_service().dismissals.list()})

    def dismissed_rule(request: Request) -> Response:
        store = vulnerability_service().dismissals
        rule: str = request.path_params["rule_id"]
        ids = store.add(rule) if request.method == "POST" else store.remove(rule)
        return json_response({"dismissed": ids})

    def mcp_server() -> McpServer:
        return ctx.lazy("mcp", lambda: McpServer(ctx))

    cap = settings.mcp_max_payload_bytes  # MCP and CLI bodies (the CLI has no payload setting of its own)
    small_cap = min(cap, _SMALL_BODY_CAP)  # the toggle and logger-level bodies are a few bytes of JSON

    async def mcp(request: Request) -> Response:
        raw = await _read_capped(request, cap)
        if raw is None:
            return json_response(payload_too_large(), 413)
        # mcp_server() may build the server: off the event loop, like every other ctx.lazy() call in an async handler
        server = await run_in_threadpool(mcp_server)
        status, body, extra = await run_in_threadpool(server.handle, raw, request.headers, request.scope)
        response = (
            Response(status_code=202, headers=dict(security_headers("api")))
            if body is None
            else json_response(body, status)
        )
        response.headers.update(dict(extra))
        return response

    def mcp_status(request: Request) -> Response:
        return json_response(mcp_server().status(api_path(request)))

    async def mcp_toggle(request: Request) -> Response:
        raw = await _read_capped(request, small_cap)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        # BootUI McpServerController: an empty body or a missing/null ``enabled`` flips; binding refuses the rest
        # parsed inline: a JSON ``null`` body flips (BootUI ``request == null``), unparsable JSON is refused
        try:
            body: object = json.loads(raw) if raw.strip() else None
        except (ValueError, RecursionError):
            body = 0
        enabled = None if body is None else cast("dict[str, Any]", body).get("enabled") if isinstance(body, dict) else 0
        if not isinstance(enabled, bool | None):
            return error(400, "Request body must be a JSON object with a boolean or null 'enabled'")
        base = api_path(request)
        return json_response(await run_in_threadpool(lambda: mcp_server().toggle(enabled, base)))

    def cli(request: Request) -> Response:
        return json_response(tools.cli_status(ctx, api_path(request)))

    async def cli_tool(request: Request) -> Response:
        raw = await _read_capped(request, cap)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        args: object = _json_or_none(raw) if raw.strip() else {}  # invalid JSON -> "Tool arguments must be an object"
        call = tools.CallContext(ctx, request.scope)
        status, body = await run_in_threadpool(tools.cli_invoke, call, request.path_params["tool"], args)
        return json_response(body, status)

    async def logger_level(request: Request) -> Response:
        raw = await _read_capped(request, small_cap)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        body = _json_or_none(raw)
        level = cast("dict[str, Any]", body).get("level") if isinstance(body, dict) else 0
        if not isinstance(level, str | None):
            return error(400, "Request body must be a JSON object with a string or null 'level'")
        return json_response(set_level(request.path_params["name"], level))

    return [
        Route("/", shell, methods=["GET"]),
        Route("/assets/{file}", asset, methods=["GET"]),
        Route(f"{api}/auth/session", session, methods=["POST"]),
        Route(f"{api}/panels", panels, methods=["GET"]),
        Route(f"{api}/overview", overview, methods=["GET"]),
        Route(f"{api}/config", config, methods=["GET"]),
        Route(f"{api}/loggers", loggers, methods=["GET"]),
        Route(f"{api}/mappings/flat", mappings, methods=["GET"]),
        Route(f"{api}/beans", beans, methods=["GET"]),
        Route(f"{api}/http-exchanges", http_exchanges, methods=["GET"]),
        Route(f"{api}/log-tail/recent", log_tail_recent, methods=["GET"]),
        Route(f"{api}/log-tail/stream", log_tail_stream, methods=["GET"]),
        Route(f"{api}/loggers/{{name:path}}", logger_level, methods=["POST"]),
        Route(f"{api}/vulnerabilities", vulnerabilities, methods=["GET"]),
        Route(f"{api}/vulnerabilities/scan", vulnerabilities_scan, methods=["POST"]),
        Route(f"{api}/dismissed-rules", dismissed_rules, methods=["GET"]),
        Route(f"{api}/dismissed-rules/{{rule_id:path}}", dismissed_rule, methods=["POST", "DELETE"]),
        Route(f"{api}/mcp", mcp, methods=["POST"]),
        Route(f"{api}/mcp-server", mcp_status, methods=["GET"]),
        Route(f"{api}/mcp-server/toggle", mcp_toggle, methods=["POST"]),
        Route(f"{api}/cli", cli, methods=["GET"]),
        Route(f"{api}/cli/tools/{{tool}}", cli_tool, methods=["POST"]),
    ]


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


async def _bad_request(_request: Request, exc: Exception) -> Response:
    return error(400, str(exc))


async def _json_http_error(_request: Request, exc: Exception) -> Response:
    """404/405 inside the active sub-app answer in the API's JSON error shape (405 keeps its ``Allow`` header)."""
    assert isinstance(exc, HTTPException)
    response = error(exc.status_code, "Not Found" if exc.status_code == 404 else "Method Not Allowed")
    response.headers.update(exc.headers or {})
    return response


async def _not_found(scope: Scope, receive: Receive, send: Send) -> None:
    """Inactive sharpit: the host's own exception handling renders this, so the 404 is the host's 404."""
    if scope["type"] == "websocket":  # as the host router does for an unknown websocket path
        await send({"type": "websocket.close", "code": 1000, "reason": ""})
        return
    raise HTTPException(404)


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

    capture = ctx.capture
    capture.stream_slots = StreamSlots()
    if sharpit_settings.panels["log-tail"].enabled:
        capture.log_tail = LogTailBuffer(sharpit_settings.log_tail_max_lines, sharpit_settings.log_tail_max_bytes)
    if sharpit_settings.panels["http-exchanges"].enabled:
        capture.exchanges = HttpExchangeBuffer(sharpit_settings.http_exchanges_max_exchanges)
    wiring = capture.wiring = CaptureWiring()
    wiring.attach_at_install(app, ctx)

    @asynccontextmanager
    async def lifespan(host_app: Any) -> AsyncGenerator[Any]:
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
        routes=_routes(ctx),
        middleware=[Middleware(GuardMiddleware, ctx=ctx)],
        exception_handlers={404: _json_http_error, 405: _json_http_error, BadRequest: _bad_request},
    )
    mount = SharpitMount(sharpit_settings.path, app=sub_app, name="sharpit")
    mount.sharpit_handle = handle
    router.routes.insert(0, mount)
    if sharpit_settings.show_banner:
        print(_banner(ctx, generated), file=sys.stderr)
    elif generated:  # nothing else can ever reveal a generated token
        print(f"sharpit authentication token (generated for this process): {token}", file=sys.stderr)
    return handle
