"""Sharpit management routes, assembled for the guarded sub-application."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from functools import partial
from importlib import import_module
from typing import Any, Literal, cast

from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import BaseRoute, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from sharpit.engine import guard, tools
from sharpit.engine import probe as probe_engine
from sharpit.engine.advisors.retention import MAX_PAGE_LIMIT, AdvisorViolationError, parse_integer
from sharpit.engine.capture import activity
from sharpit.engine.capture.exceptions import ExceptionStore, unknown_group
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.streams import change_events
from sharpit.engine.collectors import alembic, pools
from sharpit.engine.collectors.beans import beans_report
from sharpit.engine.collectors.config import config_report
from sharpit.engine.collectors.health import health_service
from sharpit.engine.collectors.loggers import loggers_report, set_level
from sharpit.engine.collectors.mappings import mappings_flat
from sharpit.engine.collectors.overview import overview_dto
from sharpit.engine.collectors.threads import threads_report
from sharpit.engine.collectors.vulns.service import VulnerabilityService
from sharpit.engine.context import SharpitContext
from sharpit.engine.mcp import McpServer, payload_too_large
from sharpit.engine.paging import BadRequest, parse_int_param
from sharpit.engine.panels import PANELS, panels_report
from sharpit.engine.panels04 import MODULE_PANEL_IDS
from sharpit.engine.singleflight import ActionBusy
from sharpit.fastapi.sse import sse_response

_adapter = cast(Any, import_module("sharpit.fastapi.adapter"))
_PAYLOAD_TOO_LARGE = "Request payload exceeds limit"


async def _read_capped(request: Request, cap: int) -> bytes | None:
    return await _adapter._read_capped(request, cap)


def _json_or_none(raw: bytes) -> object:
    return _adapter._json_or_none(raw)


def _page(request: Request) -> tuple[int | None, int | None]:
    return _adapter._page(request)


def _toggle_value(raw: bytes) -> object:
    return _adapter._toggle_value(raw)


def available_reasons(ctx: SharpitContext) -> dict[str, str | None]:
    return _adapter.available_reasons(ctx)


def log_events(buffer: Any, resume: Any) -> Any:
    return _adapter.log_events(buffer, resume)


def security_headers(kind: Literal["api", "shell", "asset"]) -> list[tuple[str, str]]:
    return _adapter.security_headers(kind)


def error(status: int, message: str, **extra: Any) -> Response:
    return _adapter.error(status, message, **extra)


def json_response(data: Any, status: int = 200) -> Response:
    return _adapter.json_response(data, status)


def _probe_request_body(raw: bytes) -> dict[str, Any] | Response:
    try:
        body: object = json.loads(raw) if raw.strip() else {}
    except (ValueError, RecursionError):
        return error(400, "Request body must be a JSON object")
    if not isinstance(body, dict):
        return error(400, "Request body must be a JSON object")
    return cast(dict[str, Any], body)


def _root_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def api_path(request: Request) -> str:
        """The API prefix as the client reached it: ``root_path`` already holds any mount prefix plus ``path``."""
        return request.scope.get("root_path", "") + api

    def shell(_request: Request) -> Response:
        html = ctx.lazy("shell", lambda: (_adapter._STATIC / "index.html").read_bytes())
        return Response(html, media_type="text/html; charset=utf-8", headers=dict(security_headers("shell")))

    def asset(request: Request) -> Response:
        name: str = request.path_params["file"]
        target = (_adapter._ASSETS / name).resolve()
        if target.parent != _adapter._ASSETS.resolve() or not target.is_file():
            raise HTTPException(404)
        return FileResponse(target, headers=dict(security_headers("asset")))

    def session(request: Request) -> Response:
        # Reached only once the guard has authorised the request (trusted source, bearer or session cookie).
        response = Response(status_code=204, headers=dict(security_headers("api")))
        if not request.scope.get(_adapter._TRUSTED_KEY, False) and ctx.token:
            secure = "; Secure" if request.url.scheme == "https" else ""
            cookie = f"{guard.SESSION_COOKIE}={ctx.token}; Path={api_path(request)}; HttpOnly; SameSite=Strict"
            response.headers.append("set-cookie", cookie + secure)
        return response

    return [
        Route("/", shell, methods=["GET"]),
        Route("/assets/{file}", asset, methods=["GET"]),
        Route(f"{api}/auth/session", session, methods=["POST"]),
    ]


def _read_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

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

    return [
        Route(f"{api}/panels", panels, methods=["GET"]),
        Route(f"{api}/overview", overview, methods=["GET"]),
        Route(f"{api}/config", config, methods=["GET"]),
        Route(f"{api}/loggers", loggers, methods=["GET"]),
        Route(f"{api}/mappings/flat", mappings, methods=["GET"]),
        Route(f"{api}/beans", beans, methods=["GET"]),
    ]


def _activity_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def activity_feed(request: Request) -> Response:
        params = request.query_params
        return json_response(
            activity.activity_report(
                ctx,
                params.get("type"),
                params.get("severity"),
                parse_int_param(params.get("since"), "since"),
                parse_int_param(params.get("limit"), "limit"),
                params.get("q"),
            )
        )

    def activity_profile(request: Request) -> Response:
        return json_response(activity.request_profile(ctx, request.path_params["id"]))

    async def activity_stream(_request: Request) -> Response:  # NOSONAR - SSE stream runs on the event loop
        changes = ctx.capture.activity_changes
        if changes is None:  # the panel gate answers first; only a disabled panel has no fan-in
            raise HTTPException(404)
        return sse_response(ctx, change_events(changes))

    def log_tail_recent(_request: Request) -> Response:
        return json_response(tools.log_tail_lines(ctx))

    async def log_tail_stream(request: Request) -> Response:  # NOSONAR - SSE stream runs on the event loop
        buffer = ctx.capture.log_tail
        if buffer is None:  # the panel gate answers first; only a disabled panel has no buffer
            raise HTTPException(404)
        # Last-Event-ID first: an automatic reconnect sends it while the URL still carries a manual ?after=
        last = request.headers.get("last-event-id") or request.query_params.get("after")
        return sse_response(ctx, log_events(buffer, buffer.resume_point(last)))

    return [
        Route(f"{api}/activity", activity_feed, methods=["GET"]),
        Route(f"{api}/activity/stream", activity_stream, methods=["GET"]),
        Route(f"{api}/activity/request/{{id}}", activity_profile, methods=["GET"]),
        Route(f"{api}/log-tail/recent", log_tail_recent, methods=["GET"]),
        Route(f"{api}/log-tail/stream", log_tail_stream, methods=["GET"]),
    ]


def _sql_trace_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]
    cap = settings.mcp_max_payload_bytes
    small_cap = min(cap, _adapter._SMALL_BODY_CAP)

    def sql_trace(_request: Request) -> Response:
        return json_response(tools.sql_trace_report(ctx))

    def sql_trace_recorder() -> SqlTraceRecorder:
        recorder = ctx.capture.sql_trace
        if recorder is None:  # SHARPIT_SQL_TRACE_ENABLED=false: nothing to clear or pause
            raise HTTPException(404)
        return recorder

    async def sql_trace_stream(_request: Request) -> Response:  # NOSONAR - SSE stream runs on the event loop
        return sse_response(ctx, change_events(sql_trace_recorder().changes))

    def sql_trace_clear(_request: Request) -> Response:
        sql_trace_recorder().clear()
        return json_response(tools.sql_trace_report(ctx))

    async def sql_trace_recording(request: Request) -> Response:
        raw = await _read_capped(request, small_cap)
        if raw is None:
            return error(413, _PAYLOAD_TOO_LARGE)
        # BootUI SqlTraceControllerSupport.recording: an empty body or a missing/null ``enabled`` flips
        enabled = _toggle_value(raw)
        if enabled is not None and not isinstance(enabled, bool):
            return error(400, "Request body must be a JSON object with a boolean or null 'enabled'")
        recorder = sql_trace_recorder()
        recorder.set_recording(not recorder.recording if enabled is None else enabled)
        return json_response(tools.sql_trace_report(ctx))

    return [
        Route(f"{api}/sql-trace", sql_trace, methods=["GET"]),
        Route(f"{api}/sql-trace/stream", sql_trace_stream, methods=["GET"]),
        Route(f"{api}/sql-trace/clear", sql_trace_clear, methods=["POST"]),
        Route(f"{api}/sql-trace/recording", sql_trace_recording, methods=["POST"]),
    ]


def _logger_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    cap = settings.mcp_max_payload_bytes  # MCP and CLI bodies (the CLI has no payload setting of its own)
    small_cap = min(cap, _adapter._SMALL_BODY_CAP)  # the toggle and logger-level bodies are a few bytes of JSON

    async def logger_level(request: Request) -> Response:
        raw = await _read_capped(request, small_cap)
        if raw is None:
            return error(413, "Request payload exceeds limit")
        body = _json_or_none(raw)
        level = cast(dict[str, Any], body).get("level") if isinstance(body, dict) else 0
        if not isinstance(level, str | None):
            return error(400, "Request body must be a JSON object with a string or null 'level'")
        return json_response(set_level(request.path_params["name"], level))

    return [
        Route(f"{api}/loggers/{{name:path}}", logger_level, methods=["POST"]),
    ]


def _http_exchange_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def http_exchanges(request: Request) -> Response:
        params = request.query_params
        offset, limit = _page(request)
        return json_response(
            tools.http_exchanges_report(
                ctx, params.get("q"), params.get("method"), params.get("statusClass"), offset, limit
            )
        )

    return [
        Route(f"{api}/http-exchanges", http_exchanges, methods=["GET"]),
    ]


async def _http_probe(ctx: SharpitContext, host_app: Any, request: Request) -> Response:
    settings = ctx.settings
    raw = await _read_capped(request, settings.mcp_max_payload_bytes)
    if raw is None:
        return error(413, _PAYLOAD_TOO_LARGE)
    body = _probe_request_body(raw)
    if isinstance(body, Response):
        return body
    incoming_root = request.scope.get("root_path", "")
    mount_path = settings.path.rstrip("/")
    host_root = incoming_root.removesuffix(mount_path)
    try:
        probe_request = probe_engine.validate_probe(body, settings.path, host_root.rstrip("/"))
    except BadRequest as exc:
        return error(400, str(exc))
    slots = ctx.lazy("probe_slots", probe_engine.ProbeSlots)
    if not slots.acquire():
        return error(409, "Too many concurrent HTTP probes")
    released = False

    def release_slot() -> None:
        nonlocal released
        if not released:
            released = True
            slots.release()

    async def run_host(
        host: ASGIApp,
        scope: Scope,
        receive: Receive,
        send: Send,
        register_cancel: Callable[[Callable[[], None]], None],
    ) -> None:
        import anyio

        with anyio.CancelScope() as cancel_scope:
            register_cancel(cancel_scope.cancel)
            await host(scope, receive, send)

    try:
        result = await probe_engine.run_probe(
            host_app,
            probe_request,
            request.scope,
            host_root.rstrip("/"),
            ctx.masker,
            timeout=probe_engine.PROBE_TIMEOUT,
            on_complete=release_slot,
            host_runner=run_host,
        )
    except asyncio.CancelledError:
        raise
    except BaseException:
        release_slot()
        raise
    return json_response(result)


def _http_probe_routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]
    return [Route(f"{api}/http-probe", partial(_http_probe, ctx, host_app), methods=["POST"], name="http_probe")]


def _exception_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def exceptions(request: Request) -> Response:
        store = _exception_store(ctx)
        if request.method == "DELETE":
            store.clear()
            return Response(status_code=204, headers=dict(security_headers("api")))
        return json_response(store.report())

    async def exceptions_stream(_request: Request) -> Response:  # NOSONAR - SSE stream runs on the event loop
        return sse_response(ctx, change_events(_exception_store(ctx).changes))

    def exception_detail(request: Request) -> Response:
        gid: str = request.path_params["id"]
        detail = _exception_store(ctx).detail(gid)
        return json_response(detail) if detail is not None else error(404, unknown_group(gid))

    return [
        Route(f"{api}/exceptions", exceptions, methods=["GET", "DELETE"]),
        Route(f"{api}/exceptions/stream", exceptions_stream, methods=["GET"]),  # before {id}: never an id
        Route(f"{api}/exceptions/{{id}}", exception_detail, methods=["GET"]),
    ]


def _exception_status_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]
    cap = settings.mcp_max_payload_bytes
    small_cap = min(cap, _adapter._SMALL_BODY_CAP)

    async def exception_status(request: Request) -> Response:
        raw = await _read_capped(request, small_cap)
        if raw is None:
            return error(413, _PAYLOAD_TOO_LARGE)
        body = _json_or_none(raw) if raw.strip() else None
        value = cast(dict[str, Any], body).get("status") if isinstance(body, dict) else None
        gid: str = request.path_params["id"]
        try:
            updated = _exception_store(ctx).set_status(gid, value if isinstance(value, str) else None)
        except ValueError as exc:  # checked before the group, as BootUI ExceptionsService.updateStatus
            return error(400, str(exc))
        return json_response(updated) if updated is not None else error(404, unknown_group(gid))

    return [
        Route(f"{api}/exceptions/{{id}}/status", exception_status, methods=["POST"]),
    ]


def _exception_store(ctx: SharpitContext) -> ExceptionStore:
    store = ctx.capture.exceptions
    if store is None:  # the panel gate answers first; only a disabled panel has no store
        raise HTTPException(404)
    return store


def _database_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def alembic_migrations(_request: Request) -> Response:
        return json_response(alembic.alembic_report(ctx))

    async def alembic_refresh(_request: Request) -> Response:
        try:
            return json_response(await alembic.refresh_alembic(ctx))
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    def health(_request: Request) -> Response:
        return json_response(health_service(ctx).report())

    async def health_check(_request: Request) -> Response:
        try:
            return json_response(await health_service(ctx).check())
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    return [
        Route(f"{api}/alembic/migrations", alembic_migrations, methods=["GET"]),
        Route(f"{api}/alembic/refresh", alembic_refresh, methods=["POST"]),
        Route(f"{api}/health", health, methods=["GET"]),
        Route(f"{api}/health/check", health_check, methods=["POST"]),
    ]


def _pool_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def connection_pools(_request: Request) -> Response:
        return json_response(pools.pools_report(ctx))

    def connection_pool_snapshot(request: Request) -> Response:
        snapshot = pools.pool_snapshot(ctx, request.path_params["name"])
        if snapshot is None:
            raise HTTPException(404)
        return json_response(snapshot)

    return [
        Route(f"{api}/database-connection-pools/pools", connection_pools, methods=["GET"]),
        Route(
            f"{api}/database-connection-pools/pools/{{name:path}}/snapshot", connection_pool_snapshot, methods=["GET"]
        ),
    ]


def _thread_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    async def thread_dump(request: Request) -> Response:  # NOSONAR - reads asyncio task state on the event loop
        # on the loop: the task list is read directly; an off-loop reader (MCP) hands it to the loop instead
        params = request.query_params
        return json_response(threads_report(ctx, params.get("q"), params.get("state"), *_page(request)))

    return [
        Route(f"{api}/threads", thread_dump, methods=["GET"]),
    ]


def _vulnerability_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def vulnerability_service() -> VulnerabilityService:
        return tools.vulnerability_service(ctx)

    def vulnerabilities(_request: Request) -> Response:
        return json_response(vulnerability_service().report())

    def vulnerabilities_scan(_request: Request) -> Response:
        try:
            return json_response(vulnerability_service().scan())
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    return [
        Route(f"{api}/vulnerabilities", vulnerabilities, methods=["GET"]),
        Route(f"{api}/vulnerabilities/scan", vulnerabilities_scan, methods=["POST"]),
    ]


def _rest_api_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def rest_api(_request: Request) -> Response:
        return json_response(tools.rest_api_service(ctx).report())

    def rest_api_scan(_request: Request) -> Response:
        try:
            return json_response(tools.rest_api_service(ctx).scan())
        except ActionBusy as exc:
            return json_response(exc.body(), 409)

    def rest_api_violations(request: Request) -> Response:
        params = request.query_params
        try:
            offset = parse_integer(params.get("offset"), "offset")
            limit = parse_integer(params.get("limit"), "limit")
            page = tools.rest_api_service(ctx).violations(
                request.path_params["rule_id"], params.get("scanId"), offset, limit, MAX_PAGE_LIMIT
            )
        except AdvisorViolationError as exc:  # BootUI AdvisorViolationExceptionHandler
            return json_response({"error": exc.message}, exc.status)
        return json_response(page)

    return [
        Route(f"{api}/rest-api", rest_api, methods=["GET"]),
        Route(f"{api}/rest-api/scan", rest_api_scan, methods=["POST"]),
        Route(f"{api}/rest-api/rules/{{rule_id}}/violations", rest_api_violations, methods=["GET"]),
    ]


def _dismissed_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def dismissed_rules(_request: Request) -> Response:
        return json_response({"dismissed": tools.dismissal_store(ctx).list()})

    def dismissed_rule(request: Request) -> Response:
        store = tools.dismissal_store(ctx)
        rule: str = request.path_params["rule_id"]
        ids = store.add(rule) if request.method == "POST" else store.remove(rule)
        return json_response({"dismissed": ids})

    return [
        Route(f"{api}/dismissed-rules", dismissed_rules, methods=["GET"]),
        Route(f"{api}/dismissed-rules/{{rule_id:path}}", dismissed_rule, methods=["POST", "DELETE"]),
    ]


def _mcp_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def api_path(request: Request) -> str:
        """The API prefix as the client reached it: ``root_path`` already holds any mount prefix plus ``path``."""
        return request.scope.get("root_path", "") + api

    cap = settings.mcp_max_payload_bytes  # MCP and CLI bodies (the CLI has no payload setting of its own)
    small_cap = min(cap, _adapter._SMALL_BODY_CAP)  # the toggle and logger-level bodies are a few bytes of JSON

    def mcp_server() -> McpServer:
        return ctx.lazy("mcp", lambda: McpServer(ctx))

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
            return error(413, _PAYLOAD_TOO_LARGE)
        # BootUI McpServerController: an empty body or a missing/null ``enabled`` flips; binding refuses the rest
        enabled = _toggle_value(raw)
        if enabled is not None and not isinstance(enabled, bool):
            return error(400, "Request body must be a JSON object with a boolean or null 'enabled'")
        base = api_path(request)
        return json_response(await run_in_threadpool(lambda: mcp_server().toggle(enabled, base)))

    return [
        Route(f"{api}/mcp", mcp, methods=["POST"]),
        Route(f"{api}/mcp-server", mcp_status, methods=["GET"]),
        Route(f"{api}/mcp-server/toggle", mcp_toggle, methods=["POST"]),
    ]


def _cli_routes(ctx: SharpitContext) -> list[BaseRoute]:
    settings = ctx.settings
    api = settings.api_path[len(settings.path) :]

    def api_path(request: Request) -> str:
        """The API prefix as the client reached it: ``root_path`` already holds any mount prefix plus ``path``."""
        return request.scope.get("root_path", "") + api

    cap = settings.mcp_max_payload_bytes  # MCP and CLI bodies (the CLI has no payload setting of its own)

    def cli(request: Request) -> Response:
        return json_response(tools.cli_status(ctx, api_path(request)))

    async def cli_tool(request: Request) -> Response:
        raw = await _read_capped(request, cap)
        if raw is None:
            return error(413, _PAYLOAD_TOO_LARGE)
        args: object = _json_or_none(raw) if raw.strip() else {}  # invalid JSON -> "Tool arguments must be an object"
        call = tools.CallContext(ctx, request.scope)
        status, body = await run_in_threadpool(tools.cli_invoke, call, request.path_params["tool"], args)
        return json_response(body, status)

    return [
        Route(f"{api}/cli", cli, methods=["GET"]),
        Route(f"{api}/cli/tools/{{tool}}", cli_tool, methods=["POST"]),
    ]


def _panel_04_routes(ctx: SharpitContext, host_app: Any = None) -> list[BaseRoute]:
    routes: list[BaseRoute] = []
    for panel in PANELS:
        if panel.id not in MODULE_PANEL_IDS or not panel.implemented:
            continue
        module = import_module(f"sharpit.fastapi.routes.{panel.id.replace('-', '_')}")
        build_routes = getattr(module, "build_routes", None)
        if build_routes is not None:
            routes.extend(build_routes(ctx, host_app))
    return routes


def build_routes(ctx: SharpitContext, host_app: Any) -> list[BaseRoute]:
    return [
        *_root_routes(ctx),
        *_read_routes(ctx),
        *_http_exchange_routes(ctx),
        *_http_probe_routes(ctx, host_app),
        *_activity_routes(ctx),
        *_exception_routes(ctx),
        *_exception_status_routes(ctx),
        *_logger_routes(ctx),
        *_sql_trace_routes(ctx),
        *_database_routes(ctx),
        *_pool_routes(ctx),
        *_thread_routes(ctx),
        *_vulnerability_routes(ctx),
        *_rest_api_routes(ctx),
        *_dismissed_routes(ctx),
        *_mcp_routes(ctx),
        *_cli_routes(ctx),
        *_panel_04_routes(ctx, host_app),
    ]
