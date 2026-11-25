from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
from functools import lru_cache
from urllib.parse import parse_qs

from sharpit.engine import guard
from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.console.types import (
    ActionAuditEvent,
    ActionAuditHook,
    ConsoleCall,
    ConsoleRequest,
    ConsoleResponse,
    ResponseClass,
    ResponseHeaders,
    RouteSpec,
)
from sharpit.engine.context import SharpitContext
from sharpit.engine.daemon_executor import DaemonExecutor
from sharpit.engine.headers import security_headers
from sharpit.engine.paging import BadRequest
from sharpit.engine.spi import HostLoopProvider

_JSON_CONTENT_TYPE = ("Content-Type", "application/json")
_STATIC_ERROR_HEADERS = (_JSON_CONTENT_TYPE, *security_headers("api"))
_LOGGER = logging.getLogger("sharpit")


class _NoOpAuditHook:
    def on_action(self, event: ActionAuditEvent) -> None:
        # the default hook: an install without an audit hook records nothing
        pass


_DEFAULT_AUDIT_HOOK = _NoOpAuditHook()


@lru_cache(maxsize=256)
def _compile(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]+\})", template)
    pattern = ""
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            name = part[1:-1]
            if name.endswith(":path"):
                pattern += f"(?P<{name[:-5]}>.+)"
            else:
                pattern += f"(?P<{name}>[^/]+)"
        else:
            pattern += re.escape(part)
    return re.compile("^" + pattern + "$")


def match_route(routes: tuple[RouteSpec, ...], method: str, path: str) -> tuple[RouteSpec, dict[str, str]] | None:
    for route in routes:
        if route.method != method:
            continue
        matched = _compile(route.template).fullmatch(path)
        if matched:
            return route, matched.groupdict()
    return None


def _allowed_methods(routes: tuple[RouteSpec, ...], path: str) -> str:
    first_by_method: dict[str, RouteSpec] = {}
    for route in routes:
        if _compile(route.template).fullmatch(path):
            first_by_method.setdefault(route.method, route)
    allowed = set(first_by_method)
    get = first_by_method.get("GET")
    if get is not None and not get.stream:
        allowed.add("HEAD")
    return ", ".join(method for method in ("GET", "HEAD", "POST", "DELETE") if method in allowed)


def _headers(request: ConsoleRequest) -> tuple[dict[str, list[str]], guard.Denial | None]:
    values: dict[str, list[str]] = {}
    for key, value in request.raw_headers:
        values.setdefault(key.decode("latin-1").lower(), []).append(value.decode("latin-1"))
    # Duplicates only: comma splitting of server-folded headers belongs to the WSGI adapter (design 3.1), so ASGI keeps
    # today's bytes.
    if len(values.get("host", ())) > 1:
        return values, guard.Denial(403, {"error": guard.MESSAGE_DISALLOWED_HOST})
    if len(values.get("origin", ())) > 1 or len(values.get("sec-fetch-site", ())) > 1:
        return values, guard.Denial(403, {"error": guard.MESSAGE_CROSS_SITE})
    return values, None


def _response_headers(headers: ResponseHeaders, kind: ResponseClass) -> ResponseHeaders:
    if any(name.lower() == "content-security-policy" for name, _ in headers):
        return headers
    merged = list(headers)
    for key, value in security_headers(kind):
        if not any(existing.lower() == key.lower() for existing, _ in merged):
            merged.append((key, value))
    return tuple(merged)


class Console:
    def __init__(
        self,
        ctx: SharpitContext,
        routes: tuple[RouteSpec, ...] = (),
        audit_hook: ActionAuditHook | None = None,
    ) -> None:
        self.ctx = ctx
        self.routes = routes
        self.audit_hook: ActionAuditHook = audit_hook or _DEFAULT_AUDIT_HOOK

    async def handle(
        self, request: ConsoleRequest, *, host_loop_provider: HostLoopProvider | None = None
    ) -> ConsoleResponse:
        try:
            return await self._handle(request, host_loop_provider)
        except Exception as exc:
            try:
                if isinstance(exc, AdvisorViolationError):
                    return self._json(exc.status, {"error": exc.message})
                if isinstance(exc, BadRequest):
                    return self._json(400, {"error": str(exc)})
                _LOGGER.warning("sharpit console request failed: %s", self.ctx.masker.mask_text(str(exc)))
                return self._json(500, {"error": "Internal Server Error"})
            except Exception:
                return ConsoleResponse(
                    500,
                    _STATIC_ERROR_HEADERS,
                    b'{"error":"Internal Server Error"}',
                )

    def _json(self, status: int, value: object, headers: tuple[tuple[str, str], ...] = ()) -> ConsoleResponse:
        body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        headers = _response_headers((*headers, _JSON_CONTENT_TYPE), "api")
        return ConsoleResponse(status, headers, body)

    async def _handle(self, request: ConsoleRequest, host_loop_provider: HostLoopProvider | None) -> ConsoleResponse:
        values, header_denial = _headers(request)
        if header_denial is not None:
            return self._json(header_denial.status, header_denial.body)
        headers = {key: ("; " if key == "cookie" else ", ").join(items) for key, items in values.items()}
        api_prefix = self.ctx.settings.api_path[len(self.ctx.settings.path) :]
        subpath = (
            request.path[len(api_prefix) :]
            if request.path == api_prefix or request.path.startswith(api_prefix + "/")
            else None
        )
        facts = guard.RequestFacts(
            request.method, request.peer_addr, headers, subpath, request.scheme, request.is_probe
        )
        settings = self.ctx.settings
        gateway = (
            self.ctx.lazy("gateway", guard.detect_container_gateway)
            if settings.trust_container_gateway.upper() != "OFF"
            else None
        )
        trusted = guard.is_trusted_source(facts, settings, gateway)
        denial = guard.decide_guard(facts, settings, self.ctx.token, gateway)
        if denial:
            return self._json(denial.status, denial.body, denial.headers)
        if request.path == "":
            location = f"{request.root_path}{settings.path}/" + (
                ("?" + request.raw_query.decode("latin-1")) if request.raw_query else ""
            )
            return ConsoleResponse(307, (("Location", location), *security_headers("api")), b"")
        selected = self._select_route(request.method, request.path)
        if isinstance(selected, ConsoleResponse):
            return selected
        route, params = selected
        call = ConsoleCall(
            self.ctx,
            request,
            headers,
            params,
            {k: v[-1] for k, v in parse_qs(request.raw_query.decode("latin-1"), keep_blank_values=True).items()},
            trusted,
            host_loop_provider,
        )
        response = await self._run_handler(route, call)
        response = self._head_response(response) if request.method == "HEAD" else response
        self._audit(route, response)
        headers = _response_headers(response.headers, route.response_class)
        return ConsoleResponse(response.status, headers, response.body, response.file, response.stream)

    def _select_route(self, method: str, path: str) -> tuple[RouteSpec, dict[str, str]] | ConsoleResponse:
        matched = match_route(self.routes, "GET" if method == "HEAD" else method, path)
        if matched is not None:
            if method == "HEAD" and matched[0].stream:
                return self._method_not_allowed("GET")
            return matched
        allow = _allowed_methods(self.routes, path)
        if allow:
            return self._method_not_allowed(allow)
        return self._json(404, {"error": "Not Found"})

    def _method_not_allowed(self, allow: str) -> ConsoleResponse:
        return self._json(405, {"error": "Method Not Allowed"}, (("Allow", allow),))

    def _head_response(self, response: ConsoleResponse) -> ConsoleResponse:
        if response.stream is not None:
            response.stream.close()
            return self._method_not_allowed("GET")
        if response.file is not None:
            return response
        headers = response.headers
        if (
            response.body is not None
            and response.status not in (204, 304)
            and not any(name.lower() == "content-length" for name, _ in headers)
        ):
            headers = (*headers, ("Content-Length", str(len(response.body))))
        return ConsoleResponse(response.status, headers, b"")

    async def _run_handler(self, route: RouteSpec, call: ConsoleCall) -> ConsoleResponse:
        if inspect.iscoroutinefunction(route.handler):
            return await route.handler(call)
        if route.on_loop:
            response = route.handler(call)
        else:
            loop = asyncio.get_running_loop()
            executor = self.ctx.lazy(
                "console.executor",
                lambda: DaemonExecutor(4, thread_name_prefix="sharpit-console"),
            )
            response = await loop.run_in_executor(executor, route.handler, call)
        if inspect.isawaitable(response):
            response = await response
        return response

    def _audit(self, route: RouteSpec, response: ConsoleResponse) -> None:
        if route.kind == "action" and route.id not in ("mcp.rpc", "cli.invoke"):
            event = ActionAuditEvent(
                action_id=route.id,
                channel="console",
                panel=route.panel,
                timestamp_ms=int(time.time() * 1000),
                status=response.status,
                ok=200 <= response.status < 400,
            )
            self.audit_hook.on_action(event)
