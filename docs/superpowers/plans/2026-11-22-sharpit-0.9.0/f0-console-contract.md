# F0: Framework-Free Console Contract (`src/sharpit/engine/console/`)

This document specifies the framework-free console contract between `src/sharpit/engine/console/` and the host framework adapters (`src/sharpit/fastapi/` for ASGI and `src/sharpit/flask/` for WSGI). It defines the Python type signatures, the five architectural decisions required by Track F of `PLAN.md`, the duplicate and joined-header rules, the Flask activation matrix and proposed `AGENTS.md` safety rule 1 wording, and the F2 route migration batches.

---

## 1. Python Contract Signatures

All types below live in `src/sharpit/engine/console/` (with shared service-provider protocols in `src/sharpit/engine/spi.py` and `src/sharpit/engine/capture/__init__.py`). In accordance with Architecture Rules 1 and 2 in `AGENTS.md`, no module in `src/sharpit/engine/console/` imports `fastapi`, `starlette`, `flask`, or `werkzeug`.

### 1.1 `ConsoleRequest`

```python
from collections.abc import Callable
from dataclasses import dataclass

RawHeaders = tuple[tuple[bytes, bytes], ...]
BodyReader = Callable[[int], bytes | None]


@dataclass(frozen=True, slots=True)
class ConsoleRequest:
    method: str
    path: str
    root_path: str
    raw_query: bytes
    raw_headers: RawHeaders
    read_body: BodyReader
    scheme: str
    peer_addr: str | None
    server: tuple[str, int | None] | None
    is_probe: bool
```

Field invariants:
- `method`: Upper-case HTTP verb (`"GET"`, `"HEAD"`, `"POST"`, `"DELETE"`, `"OPTIONS"`, etc.).
- `path`: Sub-path below `settings.path` as computed by `route_path` (`src/sharpit/engine/capture/__init__.py:100-109`): `""` for the bare mount `/sharpit`, `"/"` for `/sharpit/`, `"/assets/index-v0ytabFJ.js"` for `/sharpit/assets/index-v0ytabFJ.js`, and `"/api/overview"` for `/sharpit/api/overview` when `api_path="/sharpit/api"`. Requests outside `under(full_path, settings.path)` (`src/sharpit/engine/capture/__init__.py:112-114`) are never passed to `Console.handle`.
- `root_path`: Mount prefix above the console (`scope.get("app_root_path", scope.get("root_path", ""))` on ASGI, matching `SharpitMount.matches` in `src/sharpit/fastapi/adapter.py:73-77` and `overview_dto` in `src/sharpit/engine/collectors/overview.py:23`; `environ.get("SCRIPT_NAME", "")` on WSGI).
- `raw_query`: Unparsed query string bytes without a leading `?` (`scope.get("query_string", b"")` on ASGI; `environ.get("QUERY_STRING", "").encode("latin-1")` on WSGI).
- `raw_headers`: Tuple of `(lowercase_name_bytes, raw_value_bytes)` in wire order with every tuple preserved.
- `read_body`: `Callable[[int], bytes | None]` taking a byte cap `cap: int` and returning the request body `bytes`, or `None` when the declared `Content-Length` or streamed byte count exceeds `cap` (matching `_read_capped` in `src/sharpit/fastapi/adapter.py:196-206`).
- `scheme`: `"http"` or `"https"` (`scope.get("scheme", "http")` on ASGI, `src/sharpit/fastapi/adapter.py:143`; `environ.get("wsgi.url_scheme", "http")` on WSGI).
- `peer_addr`: Direct socket peer IP string (`client[0] if client else None` where `client = scope.get("client")` on ASGI, `src/sharpit/fastapi/adapter.py:137-140`; `environ.get("REMOTE_ADDR")` on WSGI), never derived from forwarding headers.
- `server`: `(host, port)` from the listening socket (`scope.get("server")` on ASGI, `src/sharpit/engine/collectors/overview.py:21`; `(environ["SERVER_NAME"], int(environ["SERVER_PORT"]))` when present and numeric on WSGI).
- `is_probe`: Provenance is strictly adapter-owned. On FastAPI (ASGI), `is_probe` is `bool(scope.get("extensions", {}).get("sharpit.probe"))` (`src/sharpit/fastapi/adapter.py:144`), which is set exclusively in-process by `run_probe` (`"extensions": {"sharpit.probe": True}` at `src/sharpit/engine/probe.py:260`; `PROBE_EXTENSION = "sharpit.probe"` at `src/sharpit/fastapi/capture.py:70, 521-522`). A WSGI `environ` key can never set `is_probe`: the WSGI adapter always sets `is_probe=False` on requests entering from the WSGI server, and any in-process WSGI probe tracks synthetic probe execution through a private adapter-owned `ContextVar[bool]` rather than an `environ` entry.

### 1.2 `ConsoleStream` and `ConsoleResponse`

```python
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from sharpit.engine.capture.streams import StreamSlots

ResponseHeaders = tuple[tuple[str, str], ...]
Events = AsyncIterator[tuple[str, str | None, str]]
CloseHook = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ConsoleFile:
    path: Path


@dataclass(slots=True)
class ConsoleStream:
    events: Events
    slots: StreamSlots
    max_seconds: float
    on_close: CloseHook | None = None
    _closed: bool = False

    def close(self) -> None: ...


def frame_sse(event: str, event_id: str | None, data: str) -> bytes: ...


def stream_frames(events: Events, max_seconds: float) -> AsyncGenerator[bytes]: ...


@dataclass(frozen=True, slots=True)
class ConsoleResponse:
    status: int
    headers: ResponseHeaders
    body: bytes | None = None
    file: ConsoleFile | None = None
    stream: ConsoleStream | None = None
```

Invariants:
- Exactly one of `body`, `file`, or `stream` is non-`None` (status-only responses such as `202`, `204`, or `307` use `body=b""`).
- `ConsoleStream.slots` holds a slot already acquired via `slots.acquire()` (`src/sharpit/engine/capture/streams.py:36-41`) before the stream handler returns `ConsoleResponse` (matching `sse_response` in `src/sharpit/fastapi/sse.py:72-76`). When `slots is None or not slots.acquire()`, the handler returns a `503` JSON error response (`{"error": "Too many concurrent sharpit streams"}`, `TOO_MANY_STREAMS` at `src/sharpit/fastapi/sse.py:24`) and never starts `events`.
- `ConsoleStream.close()` is idempotent: the first call invokes `slots.release()` (`src/sharpit/engine/capture/streams.py:43-45`) and `on_close()` (if provided); subsequent calls are no-ops.
- `frame_sse` and `stream_frames` move `_frame` (`src/sharpit/fastapi/sse.py:28-33`) and `_frames` (`src/sharpit/fastapi/sse.py:36-52`) into `src/sharpit/engine/console/sse.py`, timing each `await asyncio.wait_for(anext(events), remaining)` against `loop.time() + max_seconds`, yielding `b"retry: 1000\n\n"` when the window expires, and closing `events.aclose()` in a `finally:` block.

### 1.3 Route Table (`RouteSpec`), Call Object (`ConsoleCall`), and Action Audit Hook

```python
import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import HostLoopProvider

RouteKind = Literal["read", "action"]
ResponseClass = Literal["api", "shell", "asset"]
AuditChannel = Literal["console", "mcp", "cli"]


@dataclass(frozen=True, slots=True)
class ActionAuditEvent:
    action_id: str
    channel: AuditChannel
    panel: str | None
    timestamp_ms: int
    status: int
    ok: bool


class ActionAuditHook(Protocol):
    def on_action(self, event: ActionAuditEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class ConsoleCall:
    ctx: SharpitContext
    request: ConsoleRequest
    headers: Mapping[str, str]
    path_params: Mapping[str, str]
    query_params: Mapping[str, str]
    trusted: bool
    host_loop_provider: HostLoopProvider | None = None

    def page(self) -> tuple[int | None, int | None]: ...


RouteHandler = Callable[[ConsoleCall], ConsoleResponse | Awaitable[ConsoleResponse]]


@dataclass(frozen=True, slots=True)
class RouteSpec:
    id: str
    method: Literal["GET", "POST", "DELETE"]
    template: str
    handler: RouteHandler
    panel: str | None
    kind: RouteKind
    response_class: ResponseClass = "api"
    on_loop: bool = False


ROUTES: tuple[RouteSpec, ...]
```

Invariants:
- `RouteSpec.id`: Unique, stable dot-separated route identifier (for example, `"ui.shell"`, `"ui.asset"`, `"auth.session"`, `"overview.get"`, `"sql_trace.clear"`, `"mcp.rpc"`, `"cli.invoke"`).
- `RouteSpec.template`: Path template below `settings.path` (`"/"`, `"/assets/{file}"`, `f"{api}/auth/session"`, `f"{api}/overview"`, `f"{api}/exceptions/{{id}}"`, `f"{api}/data/repositories/{{name:path}}"`, where `api = settings.api_path[len(settings.path) :]` as in `src/sharpit/fastapi/routes/__init__.py:106`).
- `RouteSpec.panel`: Panel ID from `PANELS` (`src/sharpit/engine/panels.py:27-83`), or `None` for panel-agnostic routes (`"/"`, `"/assets/{file}"`, `"{api}/auth/session"`, `"{api}/panels"`, `"{api}/overview"`, `"{api}/dismissed-rules"`, `"{api}/dismissed-rules/{rule_id:path}"`, `"{api}/dismissed-findings"`, `"{api}/mcp"`, `"{api}/cli"`, `"{api}/cli/tools/{tool}"`).
- `RouteSpec.kind`: `"read"` or `"action"`. `RouteSpec.kind` is **audit metadata only**. The panel access and read-only write gates stay method-based (`unsafe = method not in _SAFE_METHODS` where `_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})`) inside `_panel_access` and `decide_guard` (`src/sharpit/engine/guard.py:47, 339-355, 401`). A dedicated contract test (`tests/engine/test_console_contract.py::test_every_non_get_route_is_classified_as_action`) asserts that every route in `ROUTES` has `kind in ("read", "action")`, every `GET` route has `kind == "read"`, and every non-`GET` (`POST`, `DELETE`) route is classified as `kind == "action"`.
- `RouteSpec.response_class`: `"shell"` for `GET /`, `"asset"` for `GET /assets/{file}`, and `"api"` for all API routes, driving `security_headers(kind)` (`src/sharpit/engine/headers.py:20-32`).
- `RouteSpec.on_loop`: Controls where synchronous (`def`) route handlers execute on FastAPI (ASGI). `async def` handlers are awaited directly on the request event loop on ASGI (and run via `asyncio.run` on WSGI). Synchronous `def` handlers run on sharpit's per-context `DaemonExecutor(4, thread_name_prefix="sharpit-console")` (`src/sharpit/engine/daemon_executor.py:14-35`) unless `on_loop=True`. Nothing that calls `wait_on_host_loop` (`src/sharpit/engine/tools04/hostloop.py:19-37`) ever sets `on_loop=True` or runs on the host event loop.
- `ConsoleCall.trusted`: Boolean computed by `guard.is_trusted_source(facts, settings, gateway)` (`src/sharpit/engine/guard.py:241-253`), replacing `scope[_TRUSTED_KEY]` (`_TRUSTED_KEY = "sharpit.trusted"` in `src/sharpit/fastapi/adapter.py:57, 152`). Used by `POST {api}/auth/session` (`src/sharpit/fastapi/routes/__init__.py:123-130`) to emit `Set-Cookie: SHARPIT_SESSION=<token>; Path=<api_path>; HttpOnly; SameSite=Strict` (plus `; Secure` when `request.scheme == "https"`) only when `not call.trusted and call.ctx.token`.
- `ConsoleCall.page()`: Parses `offset` and `limit` from `query_params` via `parse_int_param` (`src/sharpit/engine/paging.py:15-21`), raising `BadRequest` on non-integer values (matching `_page` in `src/sharpit/fastapi/adapter.py:216-219`).
- **Action audit hooks (at both route dispatch and tool dispatch):**
  - Direct console action routes (`route.kind == "action"` and `route.id not in ("mcp.rpc", "cli.invoke")`) invoke `ActionAuditHook.on_action` inside `Console.handle` with `channel="console"`, `action_id=route.id`, and `panel=route.panel`.
  - Multiplexed tool calls through `POST {api}/mcp` (`McpServer._call_tool`, `src/sharpit/engine/mcp.py:539-557`) and `POST {api}/cli/tools/{tool}` (`cli_invoke`, `src/sharpit/engine/tool_dispatch.py:278-293`) share `call_tool` (`src/sharpit/engine/tool_dispatch.py:205-221`). Because `POST {api}/mcp` and `POST {api}/cli/tools/{tool}` carry both read tools (`tool.action == False`) and action tools (`tool.action == True`), the tool-level audit hook sits inside `call_tool` (`src/sharpit/engine/tool_dispatch.py:205-221`) and fires **only** when `tool.action is True`, with `channel=via` (`"mcp"` or `"cli"`), `action_id=tool.name`, and `panel=tool.panel`. Read routes and read tools never invoke the audit hook, preserving the `no_side_effects` guarantee across REST, MCP, and CLI reads.

### 1.4 Activation Boundary, WebSocket Refusal, and `Console.handle`

```python
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import HostLoopProvider


class Console:
    ctx: SharpitContext

    def __init__(self, ctx: SharpitContext) -> None: ...

    async def handle_asgi(
        self,
        request: ConsoleRequest,
        *,
        host_loop_provider: HostLoopProvider | None = None,
    ) -> ConsoleResponse: ...

    def handle_wsgi(self, request: ConsoleRequest) -> ConsoleResponse: ...

    def handle(
        self,
        request: ConsoleRequest,
        *,
        host_loop_provider: HostLoopProvider | None = None,
    ) -> ConsoleResponse: ...
```

#### Adapter-Owned Pre-Steps (Inactive 404 and WebSocket Refusal)

1. **Inactive console (`not ctx.activation.enabled`, `src/sharpit/engine/activation.py:14-18`):**
   - The inactive path stays in the adapter. FastAPI mounts a host-rendered 404; Flask returns an adapter-owned 404 for every path under the mount. This prevents a Flask host catch-all route from answering under an inactive console mount, while preserving FastAPI's existing host exception behavior. The difference follows each adapter's routing model.
   - On FastAPI (ASGI), when `not activation.enabled`, `install()` mounts `sharpit_mount_type(sharpit_settings.path, app=_not_found, name="sharpit")` (`src/sharpit/fastapi/install.py:324-331`). `_not_found` (`src/sharpit/fastapi/adapter.py:234-239`) raises Starlette `HTTPException(404)` on HTTP scopes so the host's exception handling renders the host's 404 with **no** `security_headers`.
   - On Flask (WSGI), when `not activation.enabled`, the adapter returns 404 for every path under the mount and never calls the host `app.wsgi_app`; no host catch-all can answer there.
2. **WebSocket refusal (`scope["type"] == "websocket"`):**
   - WebSocket refusal is an ASGI protocol concern and stays in the FastAPI adapter (`GuardMiddleware.__call__` at `src/sharpit/fastapi/adapter.py:111-114` when active, and `_not_found` at `src/sharpit/fastapi/adapter.py:236-238` when inactive), sending `{"type": "websocket.close", "code": 1000, "reason": ""}` before `Console.handle` is ever called.

#### `Console.handle` Execution Pipeline (Active Console)

For every active HTTP request under `settings.path`, `Console.handle` runs the following steps in strict order:

1. **Header grouping, duplicate/joined security-header denial, and header joining (`src/sharpit/fastapi/adapter.py:84-88, 126-132`):**
   - Group `request.raw_headers` by `key.decode("latin-1").lower()` into `values: dict[str, list[str]]` preserving wire order (`_header_map`, `src/sharpit/fastapi/adapter.py:84-88`).
   - If `len(values.get("host", ())) > 1`, immediately return a `403` JSON response `{"error": guard.MESSAGE_DISALLOWED_HOST}` (`src/sharpit/fastapi/adapter.py:128-129`, `src/sharpit/engine/guard.py:38-40`) with `security_headers("api")`.
   - If `len(values.get("origin", ())) > 1 or len(values.get("sec-fetch-site", ())) > 1`, immediately return a `403` JSON response `{"error": guard.MESSAGE_CROSS_SITE}` (`src/sharpit/fastapi/adapter.py:130-131`, `src/sharpit/engine/guard.py:41`) with `security_headers("api")`.
   - Join header values into `headers: dict[str, str]` using today's exact separator rule (`src/sharpit/fastapi/adapter.py:132`):
     ```python
     headers = {k: ("; " if k == "cookie" else ", ").join(v) for k, v in values.items()}
     ```
     Never use first-occurrence-wins.

2. **Guard chain and method-based panel access (`src/sharpit/fastapi/adapter.py:133-153`, `src/sharpit/engine/guard.py:339-401`):**
   - Compute `api_prefix = ctx.settings.api_path[len(ctx.settings.path) :]` and `api_sub_path = request.path[len(api_prefix) :]` when `request.path == api_prefix or request.path.startswith(api_prefix + "/")`, else `None` (`src/sharpit/fastapi/adapter.py:97, 133-136`).
   - Construct `facts = guard.RequestFacts(request.method, request.peer_addr, headers, api_sub_path, request.scheme, request.is_probe)` (`src/sharpit/engine/guard.py:95-102`).
   - Resolve `gateway = ctx.lazy("gateway", guard.detect_container_gateway) if settings.trust_container_gateway.upper() != "OFF" else None` (`src/sharpit/fastapi/adapter.py:147-151`, `src/sharpit/engine/guard.py:416-435`).
   - Compute `trusted = guard.is_trusted_source(facts, settings, gateway)` (`src/sharpit/engine/guard.py:241-253`).
   - Run `denial = guard.decide_guard(facts, settings, ctx.token, gateway)` (`src/sharpit/engine/guard.py:373-401`), which evaluates in order:
     1. Internal probe denial (`facts.probe` -> `403 {"error": "sharpit refused an internal probe request."}`, `guard.py:377-378`).
     2. Trusted source / `allow_non_localhost` / `_via_trusted_proxy` check (`403` with `MESSAGE_FORWARDED_SOURCE` or `MESSAGE_NON_LOOPBACK_SOURCE`, `guard.py:379-384`).
     3. Host allow-list check (`403` with `MESSAGE_DISALLOWED_HOST`, `guard.py:385-390`).
     4. Cross-site check (`_is_cross_site` -> `403` with `MESSAGE_CROSS_SITE`, `guard.py:322-336, 391-392`).
     5. Token authentication for untrusted sources on API paths (`api_sub_path is not None` -> `401 {"error": AUTHENTICATION_REQUIRED_MESSAGE}` with `WWW-Authenticate: Bearer realm="sharpit"` and `Cache-Control: no-store`, `guard.py:393-400`).
     6. Panel access and method-based write gate (`_panel_access(facts.method, facts.api_sub_path, settings)`, `guard.py:339-355, 401`, using `panel_for_api_path` in `src/sharpit/engine/panels.py:100-105` and `owning_panel_access` in `guard.py:358-370` -> `403 {"error": PANEL_ACCESS_DENIED, "panel": ..., "reason": ...}`).
   - Because `decide_guard` and `_panel_access` run **before** route matching, any request to an unknown path under a disabled panel (or an unsafe method under a read-only panel) is refused with `403` before route lookup, matching today's `GuardMiddleware` behavior.
   - If `denial is not None`, return `ConsoleResponse` with `denial.status`, JSON `denial.body`, `denial.headers`, and missing headers filled from `security_headers("api")` (`src/sharpit/fastapi/adapter.py:104-107, 116-121`).

3. **Idle tracker activity mark (`src/sharpit/fastapi/install.py:52-86, 372-388`):**
   - When `api_sub_path is not None` and an `IdleTracker` is attached to the context, call `idle_tracker.mark_active()`.

4. **Bare mount redirect and route matching (`src/sharpit/fastapi/adapter.py:70-81, 226-231`):**
   - If `request.path == ""` (bare `/sharpit`, matched by `SharpitMount.matches` at `src/sharpit/fastapi/adapter.py:72-80`): return `307 Temporary Redirect` with `Location` pointing to `{request.root_path}{ctx.settings.path}/` (preserving `?{raw_query}` when `request.raw_query` is non-empty, matching Starlette's slash redirect) and `security_headers("api")`.
   - Match `(request.method, request.path)` against `ROUTES`:
     - On non-stream `GET` routes, `HEAD` works as it does today: the same status and headers, with the body stripped.
     - Stream routes refuse `HEAD` with `405` before a slot is acquired, and their `Allow` header is `GET` only.
   - If `request.path` matches at least one route template for other HTTP methods only, return `405` JSON `{"error": "Method Not Allowed"}` with `Allow: <comma-joined methods, including HEAD when GET is supported on non-stream routes, or GET only on stream routes>` and `security_headers("api")` (matching `_json_http_error` in `src/sharpit/fastapi/adapter.py:226-231`).
   - If no template matches `request.path`, return `404` JSON `{"error": "Not Found"}` with `security_headers("api")` (matching `_json_http_error` in `src/sharpit/fastapi/adapter.py:226-231`).

5. **Handler dispatch, audit hook, and response security headers:**
   - Build `ConsoleCall(ctx=self.ctx, request=request, headers=headers, path_params=path_params, query_params=query_params, trusted=trusted, host_loop_provider=host_loop_provider)`.
   - Invoke `route.handler(call)` directly (there is no inner `try / except` around the handler; exception handling is owned exclusively by the single outermost adapter catch below). If `request.method == "HEAD"` on a matched non-stream `GET` route, strip the response body (`body=b""`) while preserving `status` and `headers`.
   - If `route.kind == "action"` and `route.id not in ("mcp.rpc", "cli.invoke")` and an `ActionAuditHook` is registered, invoke `audit_hook.on_action(...)`.
   - Fill in response headers from `security_headers(route.response_class)` (`src/sharpit/engine/headers.py:20-32`) following `GuardMiddleware._send_with_headers` (`src/sharpit/fastapi/adapter.py:99-108`): if `"content-security-policy"` is not already present on the response, append each `(name, value)` from `security_headers(route.response_class)` whose header name is not already present.

#### Outermost Adapter Exception Boundary

There is **exactly one outermost catch per adapter**, so exception ownership is unambiguous:
1. **Single pre-response catch enclosing the entire pipeline:**
   - Each adapter (`src/sharpit/fastapi/` and `src/sharpit/flask/`) wraps request construction, the entire `Console.handle` call (header decoding/grouping, `decide_guard`, idle-tracker mark, route matching, handler dispatch, audit hook, and response security-header fill), and response header/body emission in a single outermost `try / except Exception` block:
     - `BadRequest` (`src/sharpit/engine/paging.py:11-12`) maps to `400` JSON `{"error": str(exc)}` with `security_headers("api")`, matching `_bad_request` in `src/sharpit/fastapi/adapter.py:222-223` and `src/sharpit/fastapi/install.py:360`.
     - `AdvisorViolationError` (`src/sharpit/engine/advisors/retention.py:19-25`) maps to `exc.status` JSON `{"error": exc.message}` with `security_headers("api")`, matching `src/sharpit/fastapi/routes/__init__.py:558-559`, `architecture.py:37-38`, `database_advisor.py:46-47`, `dismissed_findings.py:77-78`, `fastapi.py:41-42`, and `security.py:38-39`.
     - Any other `Exception` logs a masked line (`ctx.masker.mask_text`, `src/sharpit/engine/masking.py:609`) and maps to a `500` JSON response `{"error": "Internal Server Error"}` with `security_headers("api")` and no traceback. Adapters never let an exception escape into the host framework (under `flask run --debug`, an uncaught exception would otherwise be rendered by Werkzeug's `DebuggedApplication` debugger).
2. **Minimal static fallback if building the 500 response itself fails:**
   - If logging, masking, or building the `500` response itself raises an exception inside the outermost `except` block, the adapter sends a fixed minimal response: a static `500` body (`b'{"error":"Internal Server Error"}'`) and static security headers (`security_headers("api")`), with no masking call.
3. **Stream failure after `start_response` (or ASGI `http.response.start`):**
   - A stream that fails after `start_response` (during `__next__` / `__anext__` or `close()`) cannot become a `500`. Instead, the stream is aborted: close the stream (`frames.aclose()` and private event loop shutdown on WSGI), release its `StreamSlots` slot (`ConsoleStream.close()`), and log a masked line. No traceback reaches the client.

### 1.5 Host Ports (`HostProbe`, `CaptureHooks`, `HostLoopProvider`, `AppIntrospector`)

```python
import asyncio
from collections.abc import Mapping
from typing import Any, Protocol
from sharpit.engine.collectors.pentesting.evidence import SyntheticResponse
from sharpit.engine.probe import ProbeRequest


class HostProbe(Protocol):
    async def run_http_probe(
        self,
        request: ProbeRequest,
        caller_headers: tuple[tuple[bytes, bytes], ...],
        caller_client: tuple[str, int] | None,
        caller_server: tuple[str, int | None] | None,
        host_root_path: str,
        on_complete: Any = None,
    ) -> dict[str, Any]: ...

    async def run_pentest_probe(
        self,
        root_path: str = "",
    ) -> tuple[SyntheticResponse, SyntheticResponse]: ...
```

Existing ports and context wiring:
- `CaptureHooks` already exists in `src/sharpit/engine/capture/__init__.py:21-24` (`def hook_failed(self, hook: str, exc: BaseException) -> None: ...`) and is stored at `ctx.capture.wiring` (`src/sharpit/engine/capture/__init__.py:84`). `CaptureWiring` in `src/sharpit/fastapi/capture.py:180-498` implements it on FastAPI.
- `HostLoopProvider` already exists in `src/sharpit/engine/spi.py:10-13` (`def current_loop(self) -> asyncio.AbstractEventLoop | None: ...`) and is consumed by `running_host_loop` and `wait_on_host_loop` in `src/sharpit/engine/tools04/hostloop.py:14-37` and carried on `CallContext.host_loop_provider` in `src/sharpit/engine/tools.py:101-118`. On FastAPI, `_RequestHostLoopProvider(asyncio.get_running_loop())` (`src/sharpit/fastapi/routes/__init__.py:50-55, 621, 670`) binds the active request event loop; on Flask (WSGI), the adapter passes a provider whose `current_loop()` returns `None`.
- `HostProbe` abstracts the two in-process synthetic probe entry points: `run_probe` in `src/sharpit/engine/probe.py:221-370` (invoked by `_http_probe` in `src/sharpit/fastapi/routes/__init__.py:304-360`) and `pentesting_probe.run_probe` in `src/sharpit/fastapi/pentesting_probe.py:46-57` (invoked by `pentesting.py:31-45`). On FastAPI, the ASGI adapter implements `HostProbe` over the host `ASGIApp`; on Flask in 0.9.0, `host_probe` is `None` (in-process HTTP probe and active pentest probing remain ASGI-only in 0.9.0 as recorded in `PLAN.md:223-224` and F0b).
- `overview_dto(ctx, scope)` (`src/sharpit/engine/collectors/overview.py:19-46`), `CallContext.scope` (`src/sharpit/engine/tools.py:104, 409`), and `McpServer.handle(..., scope, ...)` (`src/sharpit/engine/mcp.py:387-418, 450-557`) replace their ASGI `scope` dictionary reads (`scope.get("server")` and `scope.get("app_root_path", scope.get("root_path"))` in `overview.py:21-23`; `scope.get("root_path", "")` in `pentesting.py:32`) with typed request metadata (`server`, `root_path`, and `web_application_type` / `platform`), so no WSGI adapter ever constructs a synthetic ASGI `scope`.

---

## 2. Decisions for the Five Plan Questions

### Decision 1: Where Each Handler Runs on Each Adapter, and Whether a Console Read on FastAPI Takes a Host Threadpool Slot

**Decision:**
1. **A console read on FastAPI never takes a host threadpool slot** (`anyio.to_thread.current_default_thread_limiter()`).
2. **Handler execution model (`async def` vs. sync `def` with `RouteSpec.on_loop`):**
   - **Handlers may be `async def` or sync `def`.**
   - **On FastAPI (ASGI):**
     - The guard chain (`decide_guard`, `src/sharpit/engine/guard.py:373-401`), duplicate-header check, bare-mount redirect, and route matching always run synchronously on the ASGI event loop thread before body reading or handler dispatch.
     - **`async def` handlers** (SSE stream routes, async database action routes `POST /alembic/refresh`, `POST /health/check`, `POST /mysql/read`, `POST /postgresql/read`, `POST /database-advisor/scan`, and `POST /http-probe`, `GET /pentesting`, `POST /pentesting/scan`) and **sync `def` handlers marked `on_loop=True`** (including `GET /threads`, which inspects the running loop's tasks directly via `_tasks` and `_collect` in `src/sharpit/engine/collectors/threads.py:153-182` without spawning threads, plus fast in-memory read handlers) run **directly on the ASGI event loop thread**.
     - **Sync `def` handlers with `on_loop=False`** (the default for sync handlers, including filesystem-scanning reads such as `GET /config` in `src/sharpit/engine/collectors/config/__init__.py:69-152`, `GET /profile-diff` in `src/sharpit/engine/collectors/config/profiles.py:148-180`, `GET /alembic/migrations` in `src/sharpit/engine/collectors/alembic.py:389-394`, `GET /rest-api/error-contract` in `src/sharpit/engine/collectors/restapi/error_contract.py:305-339`, agent-session disk reads in `src/sharpit/fastapi/routes/agent_sessions.py:15-72`, sync advisor scans, file-writing overrides/dismissals, and tool dispatchers `POST /mcp` and `POST /cli/tools/{tool}`) run via `await loop.run_in_executor(executor, route.handler, call)` on a sharpit-owned lazy executor `ctx.lazy("console.executor", lambda: DaemonExecutor(4, thread_name_prefix="sharpit-console"))` (`src/sharpit/engine/daemon_executor.py:14-35`).
     - **Nothing that waits on the host loop runs on it (`src/sharpit/engine/tools04/hostloop.py:19-37`):** `POST /mcp` (`src/sharpit/fastapi/routes/__init__.py:615-629`) and `POST /cli/tools/{tool}` (`src/sharpit/fastapi/routes/__init__.py:665-672`) capture `_RequestHostLoopProvider(asyncio.get_running_loop())` (`routes/__init__.py:50-55, 621, 670`) on the ASGI event loop thread, read the capped request body, and then execute `McpServer.handle` (`src/sharpit/engine/mcp.py:387-418`) or `tools.cli_invoke` (`src/sharpit/engine/tool_dispatch.py:278-293`) off-loop on sharpit's `DaemonExecutor`. Inside `call_tool`, `ToolGate.run` (`src/sharpit/engine/tool_dispatch.py:70-102`) and `wait_on_host_loop` (`src/sharpit/engine/tools04/hostloop.py:19-37`, which calls `asyncio.run_coroutine_threadsafe(coro, loop)` and blocks on `future.result(timeout)`) never block the host event loop thread.
   - **On Flask (WSGI):**
     - Sync `def` handlers (`on_loop=True` and `on_loop=False` alike) run synchronously on the calling WSGI worker thread.
     - `async def` handlers run via `asyncio.run(...)` on the calling WSGI worker thread (with `host_loop_provider.current_loop()` returning `None`, following `src/sharpit/engine/tools04/mysql.py:36-49`, `postgresql.py:36-49`, and `database_advisor.py:57-68`).

**Reason:**
- `tests/fastapi/test_threads_api.py:77-90` (`test_get_threads_mcp_no_side_effects`) and `src/sharpit/fastapi/routes/__init__.py:505-508` (`thread_dump`) require `GET /sharpit/api/threads` to read `asyncio.all_tasks()` directly on the running event loop thread (`running is loop` in `src/sharpit/engine/collectors/threads.py:168-172`) without starting extra threads.
- `tests/fastapi/test_concurrency.py:19-50` (`test_other_panels_are_not_serialised_behind_a_slow_config_scan`) monkeypatches `config_module.scan_packages` with a blocking wait (`release.wait(10)`) and asserts that concurrent requests to `/sharpit/api/mcp`, `/sharpit/api/mcp-server/toggle`, and `/sharpit/api/mcp-server` complete while `/sharpit/api/config` is scanning. Running `on_loop=False` sync handlers on sharpit's `DaemonExecutor(4, thread_name_prefix="sharpit-console")` keeps the event loop unblocked during slow disk scans while isolating sharpit from Starlette's `run_in_threadpool` and the host's AnyIO thread limiter.

**Proving Test:**
- `tests/fastapi/test_concurrency.py::test_console_reads_complete_when_host_anyio_threadpool_is_exhausted` — occupies all tokens of `anyio.to_thread.current_default_thread_limiter()`, issues concurrent `GET /sharpit/api/overview`, `GET /sharpit/api/threads`, and `GET /sharpit/api/config` calls, and asserts all return `200` without waiting on the AnyIO limiter.

---

### Decision 2: The Stream Form (Standard-Library `asyncio` as a Stated Runtime Requirement for Every Adapter)

**Decision:**
Choose option **(b): `asyncio` is a stated, tested runtime requirement for every adapter**, keeping the existing `asyncio`-based stream primitives in `src/sharpit/engine/capture/streams.py:1-228` as the single stream implementation in the engine:
- In `src/sharpit/engine/capture/streams.py`:
  - `_Ticker` (`streams.py:48-96`) is initialized with `loop: asyncio.AbstractEventLoop` and `detach: Callable[[_Ticker], None]`, uses `self._ready = asyncio.Event()` (`streams.py:56`), and is signalled from any thread via `self._loop.call_soon_threadsafe(self._wake)` (`streams.py:67`), which schedules `self._loop.call_later(delay, self._tick)` (`streams.py:76`) using `self._loop.time()` (`streams.py:74, 84`) at `TICK_SECONDS = 0.25` (`streams.py:21`).
  - `Subscription(_Ticker)` (`streams.py:99-110`) and `LineSubscription(_Ticker)` (`streams.py:113-157`) are `AsyncIterator` classes whose `__anext__` awaits `self._ready.wait()`.
  - `_Hub` (`streams.py:160-181`) maintains `self._subscribers: list[_Ticker]` under `self._lock = threading.RLock()` and prunes any subscriber whose `_signal()` returns `False` because `self._loop.is_closed()` (`streams.py:61, 173`).
  - `change_events(stream: ChangeStream)` (`streams.py:221-228`), `log_events(buffer: LogTailBuffer, after: int | None)` (`src/sharpit/engine/capture/logtail.py:98-105`), and `_agent_sessions_events(store: Any, debounce_seconds: float)` (`src/sharpit/fastapi/routes/agent_sessions_stream.py:22-42`) are async generators that subscribe with `asyncio.get_running_loop()`.
- In `src/sharpit/engine/console/sse.py`, `frame_sse` and `stream_frames` (moved from `_frame` and `_frames` in `src/sharpit/fastapi/sse.py:28-52`) consume `Events = AsyncIterator[tuple[str, str | None, str]]` over `max_seconds`.
- **On FastAPI (ASGI):** The adapter iterates `stream_frames(stream.events, stream.max_seconds)` directly on the current ASGI event loop while setting `SSE_TASK` (`src/sharpit/engine/capture/streams.py:20`) and releasing the slot via `stream.close()` in `finally:` (`src/sharpit/fastapi/sse.py:61-69`).
- **On Flask (WSGI) and any synchronous adapter:** Because `asyncio` is part of the Python `>=3.12` standard library and `_Hub.signal()` (`src/sharpit/engine/capture/streams.py:169-173`) already dispatches across threads to each subscriber's own `self._loop` via `call_soon_threadsafe`, the WSGI adapter drives `stream_frames(stream.events, stream.max_seconds)` on a per-stream private event loop (`loop = asyncio.new_event_loop()`) on the serving WSGI worker thread:
  - Each `__next__()` call runs `loop.run_until_complete(anext(frames))` until `StopAsyncIteration` (after the closing `b"retry: 1000\n\n"` frame).
  - `close()` (called by the WSGI server on normal completion or client disconnect) idempotently runs `loop.run_until_complete(frames.aclose())` (which executes the `finally:` block in `change_events` at `streams.py:227-228` or `log_events` at `logtail.py:104-105`, calling `subscription.close()` -> `self._detach(self)` to remove the `_Ticker` from `_Hub._subscribers`), closes `loop`, and calls `ConsoleStream.close()`.

**Reason:**
- Grounding the choice in `src/sharpit/engine/capture/streams.py:48-228` shows that `_Ticker`, `Subscription`, `LineSubscription`, `_Hub`, `ChangeStream`, `LineStream`, `change_events`, `log_events`, and `_agent_sessions_events` are already multi-loop capable: `_Ticker` binds to the `asyncio.AbstractEventLoop` passed to `subscribe(loop)` rather than a global loop, and `_Hub.signal()` safely wakes any subscriber loop from any thread.
- Introducing a second `threading.Condition` pull/close protocol in the engine (option a) would either duplicate `_Ticker`'s 250 ms coalescing timer (`TICK_SECONDS = 0.25`, `streams.py:21`) and `LineSubscription`'s 1000-line replay/overflow queue (`LINE_QUEUE = 1000`, `streams.py:22, 130-143`) or wrap the existing `asyncio` generators in a bridge anyway. Declaring standard-library `asyncio` as the engine's runtime stream requirement keeps a single tested implementation of `_Ticker` and `_frames` across all adapters and ensures zero behavioral or timing drift on FastAPI.

**Proving Test:**
- `tests/engine/test_console_streams.py::test_private_loop_wsgi_stream_receives_cross_thread_signals_and_detaches_on_close` — drives `stream_frames(change_events(stream), max_seconds=0.6)` on a worker thread's private `asyncio.new_event_loop()`, triggers `stream.signal()` from a second thread, and asserts the iterator yields `event: update` frames (`src/sharpit/engine/capture/streams.py:226`), terminates with `b"retry: 1000\n\n"` (`src/sharpit/fastapi/sse.py:46`), and leaves `stream.subscriber_count == 0` (`streams.py:165-167`) and `slots.count == 0` (`streams.py:33`).

---

### Decision 3: The WSGI Capacity Rule (`SHARPIT_WSGI_STREAM_MAX` Default `0`, Overload Response, Cleanup on Disconnect)

**Decision:**
1. **`SHARPIT_WSGI_STREAM_MAX` setting (field default `0`, never inferred from launcher arguments):**
   - FastAPI (ASGI) uses `MAX_STREAMS = 20` (`src/sharpit/engine/capture/streams.py:23`, `StreamSlots()` in `src/sharpit/fastapi/install.py:91`).
   - Flask (WSGI) never inspects `sys.argv`, `GUNICORN_CMD_ARGS`, or `environ["wsgi.multithread"]` to guess worker or thread counts (launcher flags are server-specific and ambiguous; for example, `gunicorn -t` is `--timeout`, not `--threads`, and Werkzeug's `FlaskClient` sets `wsgi.multithread = False` in tests).
   - Add `SharpitSettings.wsgi_stream_max: int = 0` (`src/sharpit/settings.py`), configured via environment variable `SHARPIT_WSGI_STREAM_MAX` or `install(..., wsgi_stream_max=...)`, validated as a non-negative integer (`>= 0`):
     - **The field default is `0`**, which means SSE streaming is off on Flask, with an availability reason (`WSGI_STREAM_CAPACITY_UNKNOWN`).
     - **An invalid value** (non-integer or `< 0`) **fails safe to `0`** and adds a settings warning (`src/sharpit/settings.py:259-314`).
     - **`4` is a documented suggested value** for multi-worker or multi-threaded WSGI dev setups (e.g., `SHARPIT_WSGI_STREAM_MAX=4`), **NOT a default**.
2. **`HEAD` refusal and overload response (`503`):**
   - Stream routes refuse `HEAD` with `405` (`Allow: GET` only) in route matching before any slot is acquired.
   - On `GET`, before starting an event generator, the stream route checks `slots = ctx.capture.stream_slots`; if `slots is None or not slots.acquire()` (including when `wsgi_stream_max` is `0`), it returns `503` JSON `{"error": "Too many concurrent sharpit streams"}` (`TOO_MANY_STREAMS` in `src/sharpit/fastapi/sse.py:24, 72-76`) with `security_headers("api")`.
3. **Cleanup on disconnect, normal window completion, and post-`start_response` abort:**
   - Every open stream is bounded by `ctx.settings.stream_max_seconds` (default `3.0` s, `src/sharpit/settings.py:104`), after which `stream_frames` yields `b"retry: 1000\n\n"` and exits normally, freeing the WSGI worker thread at most every 3 seconds.
   - Under PEP 3333, the WSGI server calls `close()` on the response iterator both when the response completes and when the client disconnects early. `WsgiEventStream.close()` is idempotent and guarantees that `frames.aclose()` runs on the private event loop (detaching the `_Ticker` from `_Hub._subscribers` via `subscription.close()` at `src/sharpit/engine/capture/streams.py:91-96, 228`), closes the private event loop (so `_Ticker._signal()`'s `self._loop.is_closed()` check at `streams.py:61` also drops it on any concurrent signal), and calls `ConsoleStream.close()` to release the `StreamSlots` slot (`streams.py:43-45`) exactly once.
   - If a stream fails after `start_response` (during `__next__` or `close()`), it cannot become a `500`: the adapter aborts the stream, closes it, releases its slot, and logs a masked line with no traceback reaching the client.

**Reason:**
- Inferring worker concurrency from command-line arguments is brittle across WSGI servers (Gunicorn `-t` is timeout in seconds, uWSGI and Waitress use different flags, and programmatic launchers pass no CLI flags). Defaulting `SharpitSettings.wsgi_stream_max` to `0` (streaming off with an explicit availability reason) fails safe on single-worker WSGI servers while allowing users to opt in by setting a positive capacity (with `4` documented as a suggested value).

**Proving Test:**
- `tests/engine/test_console_streams.py::test_wsgi_stream_slots_cap_and_idempotent_disconnect_cleanup` — verifies that `wsgi_stream_max` defaults to `0` (and invalid `SHARPIT_WSGI_STREAM_MAX` values fail safe to `0` with a warning), that `HEAD` on a stream route returns `405` with `Allow: GET` only and `slots.count == 0`, that `limit=0` or exceeding `StreamSlots(limit=2)` immediately returns `503 {"error": "Too many concurrent sharpit streams"}` without starting the async generator, and that aborting an active stream early (via `.close()` twice or an exception during `__next__`) closes the stream, logs a masked line on error, and leaves `stream.subscriber_count == 0` and `slots.count == 0`.

---

### Decision 4: Route Order, Including the `SharpitMount` Bare-Path Match and Inventory Test

**Decision:**
1. **Mount prefix check (`under(path, settings.path)`):**
   - Both `SharpitMount` on FastAPI (`src/sharpit/fastapi/adapter.py:61-81`, inserted at index `0` via `router.routes.insert(0, mount)` in `src/sharpit/fastapi/install.py:327, 364`) and the Flask WSGI wrapper match a request if and only if `under(path, settings.path)` (`path == prefix or path.startswith(prefix + "/")`, `src/sharpit/engine/capture/__init__.py:112-114`) is `True`. Sibling prefixes such as `/sharpit-other` do not match and pass straight to the host application.
2. **Bare-path match (`request.path == ""` for `/sharpit`):**
   - When a request arrives for bare `/sharpit` (any HTTP method), `Console.handle` runs step 1 (duplicate/joined security-header check) and step 2 (`decide_guard`) **before** step 4 issues the `307 Temporary Redirect` to `{request.root_path}{ctx.settings.path}/` (preserving `?{raw_query}` when present) with `security_headers("api")`.
3. **Literal-before-parameter route ordering in `ROUTES`:**
   - Today `src/sharpit/fastapi/adapter.py:245-284` constructs the route list by calling `build_routes(ctx, host_app)` (`src/sharpit/fastapi/routes/__init__.py:692-716`), splicing `dismissed_findings.build_routes(ctx)` after `/dismissed-rules` (`adapter.py:252-254`), and calling `_with_drift_routes(routes, ctx)` (`adapter.py:258-284`) so that `activity.py`, `http_exchanges.py`, and `exceptions.py` replace base routes or insert literal sub-paths (`GET /api/http-exchanges/routes`, `GET /api/activity/resources`, `GET /api/activity/journal`, `GET /api/exceptions/caught`, `GET /api/exceptions/stream`) ahead of parameterized siblings (`GET /api/exceptions/{id}`).
   - In `src/sharpit/engine/console/`, `ROUTES` places literal routes ahead of single-segment parameters (`{id}`, `{spanId}`, `{observation_id}`, `{sensor}`, `{tool}`, `{rule_id}`, `{file}`, `{name}`) and single-segment or multi-segment routes ahead of `:path` catch-alls (`{name:path}`, `{rule_id:path}`), retiring `_with_drift_routes` and the `dismissed_findings` splice in `src/sharpit/fastapi/adapter.py:245-284`.
4. **Automated route inventory parity test:**
   - `tests/engine/test_console_contract.py::test_routes_inventory_matches_fastapi_build_routes` calls `adapter._routes(ctx, app)` (`src/sharpit/fastapi/adapter.py:245-255`) and compares the resulting 138 Starlette `Route` entries (144 `(method, path)` pairs across `GET`, `POST`, and `DELETE`) against `ROUTES`, asserting that the set of `(method, path)` pairs is identical and that every literal sibling precedes any parameterized sibling that could shadow it.

**Reason:**
- Splicing routes at runtime in `_with_drift_routes` (`src/sharpit/fastapi/adapter.py:258-284`) was a temporary lane-isolation shortcut noted in `adapter.py:250-251, 266-267`. Pre-ordering `ROUTES` and pinning it against `adapter._routes(ctx, app)` guarantees identical route resolution on FastAPI and Flask.

**Proving Test:**
- `tests/engine/test_console_contract.py::test_routes_inventory_matches_fastapi_build_routes` and `tests/engine/test_console_contract.py::test_bare_mount_runs_guard_before_307_redirect`.

---

### Decision 5: The Request ID Header (`X-Sharpit-Request-Id`)

**Decision:**
1. **Console responses (`Console.handle`) never emit `x-sharpit-request-id`.** On FastAPI today, `CaptureMiddleware.__call__` bypasses paths under `settings.path` (`if under(route_path(scope), self.ctx.settings.path):` at `src/sharpit/fastapi/capture.py:551-560`), counting them via `buffer.count_hidden_self()` without invoking `with_request_id_header`.
2. **Host application responses on FastAPI (ASGI):** `CaptureMiddleware` (`src/sharpit/fastapi/capture.py:505-509, 606-611`) and `with_request_id_header` (`src/sharpit/fastapi/request_id_header.py:15-51`) continue to append `(b"x-sharpit-request-id", info.id.encode("ascii"))` to host HTTP responses when:
   - `settings.http_exchanges_expose_request_id_header` is `True`, `panel_is_implemented("http-exchanges")` is `True`, and `settings.panels["http-exchanges"].enabled` is `True` (`capture.py:505-509`),
   - `ctx.capture.exchanges is not None` (`request_id_header.py:27`),
   - the response headers do not already contain `x-sharpit-request-id` (case-insensitive, `request_id_header.py:30`), and
   - `guard.is_trusted_source(facts, settings, gateway)` is `True` (`request_id_header.py:36-49`).
3. **Host application responses on Flask (WSGI) in 0.9.0:** `x-sharpit-request-id` is **not emitted on Flask in 0.9.0** (recorded in `PLAN.md:223-224` and F0b as ASGI-only).

**Reason:**
- `x-sharpit-request-id` exposes the `HttpExchangeBuffer` exchange ID (`info.id` in `src/sharpit/fastapi/capture.py:568-577, 608`) so callers can look up the captured HTTP exchange in `GET /sharpit/api/http-exchanges` and `GET /sharpit/api/activity/request/{id}`. Because HTTP exchange capture (`HttpExchangeBuffer`) is ASGI-only in 0.9.0 (`PLAN.md:223-224`), emitting `x-sharpit-request-id` on Flask would return an ID with no corresponding exchange record.

**Proving Test:**
- `tests/engine/test_console_contract.py::test_console_responses_never_include_request_id_header`.

---

## 3. Duplicate Headers, Joined Headers, and the WSGI Request-Target Rule

### 3.1 Duplicate Header Denial and the ASGI Comma Decision

In `GuardMiddleware._decide` (`src/sharpit/fastapi/adapter.py:126-132`), duplicate security-critical headers are checked on the raw header multi-map before `decide_guard` runs:
```python
if len(values.get("host", ())) > 1:
    return guard.Denial(403, {"error": guard.MESSAGE_DISALLOWED_HOST})
if len(values.get("origin", ())) > 1 or len(values.get("sec-fetch-site", ())) > 1:
    return guard.Denial(403, {"error": guard.MESSAGE_CROSS_SITE})
headers = {k: ("; " if k == "cookie" else ", ").join(v) for k, v in values.items()}
```

**Decision on the ASGI comma rule:**
The pre-guard comma check on ASGI is **dropped**; `Console.handle` checks `len(values.get("host", ())) > 1` and `len(values.get("origin", ())) > 1 or len(values.get("sec-fetch-site", ())) > 1` on `request.raw_headers`, while the **WSGI adapter** splits comma-containing `HTTP_HOST`, `HTTP_ORIGIN`, and `HTTP_SEC_FETCH_SITE` values on `","` into multiple `(name_bytes, value_bytes)` tuples when constructing `ConsoleRequest.raw_headers` (as specified in `PLAN.md:75` and `PLAN.md:237-238`).

**Reason:**
1. On ASGI, the HTTP server passes raw wire header pairs in `scope["headers"]` without folding duplicate headers. Duplicate `Host`, `Origin`, or `Sec-Fetch-Site` headers arrive as multiple tuples and are denied with `403` (`MESSAGE_DISALLOWED_HOST` or `MESSAGE_CROSS_SITE`). A single comma-containing `Host: localhost, evil.example` or `Origin: http://localhost, http://evil.example` from a trusted peer is already denied with `403` (`MESSAGE_DISALLOWED_HOST` or `MESSAGE_CROSS_SITE`) inside `decide_guard` because `_is_registered_name` (`src/sharpit/engine/guard.py:186-187`) rejects `","` in `extract_request_host` (`guard.py:115-120`) and `extract_origin_host` (`guard.py:123-136`).
2. Applying a pre-guard comma check to raw ASGI tuples would change today's FastAPI bytes on two F1 response corpus cases:
   - A single-tuple `Sec-Fetch-Site: same-origin, cross-site` header on ASGI (which today passes `len(values.get("sec-fetch-site", ())) > 1` at `src/sharpit/fastapi/adapter.py:130` and evaluates `facts.headers.get("sec-fetch-site", "").casefold() == "cross-site"` as `False` at `src/sharpit/engine/guard.py:323`, returning `200`, whereas pre-guard comma rejection would return `403 MESSAGE_CROSS_SITE`).
   - An untrusted-peer request carrying a single comma-containing `Host`, `Origin`, or `Sec-Fetch-Site` header (which today reaches `decide_guard` and fails first at step 1, `is_trusted_source` at `src/sharpit/engine/guard.py:380-384`, returning `403 MESSAGE_NON_LOOPBACK_SOURCE` rather than `MESSAGE_DISALLOWED_HOST` or `MESSAGE_CROSS_SITE`).
3. Keeping comma splitting in the WSGI adapter preserves 100% byte-for-byte identity with today's FastAPI response corpus across F1 and F2 while ensuring that folded duplicate headers in WSGI produce the exact same `403` status and error messages (`MESSAGE_DISALLOWED_HOST` and `MESSAGE_CROSS_SITE`).

### 3.2 Werkzeug `","` Header Folding and Absolute-Form Request Targets on WSGI

Two Werkzeug/WSGI behaviors require explicit rules in the Flask WSGI adapter (`src/sharpit/flask/`) when building `ConsoleRequest`:

1. **Comma-folded security headers (`","` without a space):**
   - Under PEP 3333, Werkzeug's `WSGIRequestHandler` joins duplicate incoming headers with `","` (no space), while other WSGI servers join with `", "`.
   - None of `Host`, `Origin`, or `Sec-Fetch-Site` can contain `","` (`0x2c`) in a valid single header value.
   - When extracting `ConsoleRequest.raw_headers` from the PEP 3333 `environ` dictionary:
     1. If `environ.get("CONTENT_TYPE")` is present, append `(b"content-type", environ["CONTENT_TYPE"].encode("latin-1"))`.
     2. If `environ.get("CONTENT_LENGTH")` is present and non-empty, append `(b"content-length", environ["CONTENT_LENGTH"].encode("latin-1"))`.
     3. For every `(key, value)` in `environ.items()` where `key.startswith("HTTP_")` and `isinstance(value, str)`: let `name = key[5:].replace("_", "-").lower().encode("latin-1")`. If `name in (b"host", b"origin", b"sec-fetch-site")` and `"," in value`, emit one `(name, part.encode("latin-1"))` tuple per comma-separated segment (`value.split(",")`) so `Console.handle` sees `len(values[...]) > 1` and denies the request with `403` (`MESSAGE_DISALLOWED_HOST` for `host`; `MESSAGE_CROSS_SITE` for `origin` and `sec-fetch-site`). Otherwise, emit `(name, value.encode("latin-1"))`.
     4. There is no test-only adapter branch for pre-parsed raw header pairs; tests exercise the WSGI adapter exclusively through standard PEP 3333 `environ` dictionaries.
2. **Absolute-form request targets (`RAW_URI` / `REQUEST_URI`) and `HTTP_HOST` validation on WSGI:**
   - When an HTTP/1.1 client sends an absolute-form request target on the request line (for example, `GET http://localhost/sharpit/api/overview HTTP/1.1` with header `Host: evil.example`), Werkzeug's `WSGIRequestHandler.make_environ` parses the URI's authority and overwrites `environ["HTTP_HOST"] = "localhost"`, discarding the `Host: evil.example` header while keeping the raw request target in `environ["REQUEST_URI"]` / `environ["RAW_URI"]`.
   - Therefore, for every active request under `settings.path`, the WSGI adapter validates `RAW_URI` / `REQUEST_URI` and `HTTP_HOST` before calling `Console.handle` and **returns `403` itself** (with `security_headers("api")`, never synthesizing a fake `Host` header):
     1. **When `RAW_URI` or `REQUEST_URI` is absolute-form** (or any non-origin form: a non-empty string that does not start with `"/"` or starts with `"//"`, such as `http://localhost/sharpit/api/overview`): the adapter returns `403` JSON `{"error": guard.MESSAGE_DISALLOWED_HOST}` with `security_headers("api")`.
     2. **When `HTTP_HOST` is missing or blank** (`not environ.get("HTTP_HOST", "").strip()`): the adapter returns `403` JSON `{"error": guard.MESSAGE_DISALLOWED_HOST}` with `security_headers("api")`.
     3. **When the server exposes neither `RAW_URI` nor `REQUEST_URI`** (both are missing or empty in `environ`): in that case the adapter cannot detect whether the request arrived in absolute-form (because PEP 3333 `PATH_INFO` contains only the stripped path after `HTTP_HOST` may already have been overwritten), so it **fails closed** by returning `403` with `security_headers("api")` and an availability reason that names the server limitation (that the WSGI server exposes neither `RAW_URI` nor `REQUEST_URI`).

---

## 4. Activation on Flask

### 4.1 Current Signal and Activation Behavior

Today:
- `dev_server_signal(argv: Sequence[str]) -> str | None` in `src/sharpit/fastapi/signals.py:8-19` inspects `argv` only:
  - If `"--reload" in argv[1:]`, it returns `"uvicorn --reload"` (`signals.py:13-14`).
  - If `len(argv) > 1 and argv[1] == "dev"` and `argv[0]` ends with `fastapi`, `fastapi.exe`, or `fastapi/__main__.py`, it returns `"fastapi dev"` (`signals.py:15-18`).
  - Otherwise it returns `None` (`signals.py:19`).
- `decide(settings: SharpitSettings, profiles: Sequence[str], dev_signal: str | None) -> ActivationStatus` in `src/sharpit/engine/activation.py:39-69` returns `ActivationStatus(enabled, localhost_only, reason, tuple(warnings))` (`activation.py:14-18`) with the exact reason strings at lines 48–69.

### 4.2 Reloader Child Recognition Rules for Flask

The Werkzeug reloader child's `argv` equals the parent's because Werkzeug replays `sys.orig_argv` when spawning the child process, so `argv` cannot tell parent from child. Only `WERKZEUG_RUN_MAIN` can distinguish the serving child from the reloader parent. Conversely, `WERKZEUG_RUN_MAIN` alone is insufficient because child subprocesses or the shell environment can inherit `WERKZEUG_RUN_MAIN=true` even when no reloader is active.

In F3, the Flask serving child enables via `dev_server_signal` **only when ALL four of these conditions hold**:
- **(a)** `WERKZEUG_RUN_MAIN == "true"` (`environ.get("WERKZEUG_RUN_MAIN") == "true"`);
- **(b)** `argv` is a Flask CLI `run` invocation: `argv[0]` basename is `flask` or `flask.exe`, or the process was started as `python -m flask` (`argv[0]` ends with `flask/__main__.py`), and `run` is the first positional command;
- **(c)** `--no-reload` is absent from `argv[1:]`;
- **(d)** reloading is on: `--reload` is present in `argv[1:]`, or debug is on (`--debug` is present in `argv[1:]` without `--no-debug`, or `FLASK_DEBUG` is truthy in `environ` without `--no-debug`), the way `flask/cli.py` derives `reload = debug`.

When all four conditions (a)–(d) hold, `dev_server_signal` returns `"flask run --reload"` (when `--reload` is present) or `"flask run --debug"` (when reloading is derived from `--debug` or truthy `FLASK_DEBUG`).

**Anything else is disabled, and that fails closed:**
- The reloader parent process (`WERKZEUG_RUN_MAIN` unset or not `"true"`) is disabled ((a) fails).
- An inherited `WERKZEUG_RUN_MAIN=true` with `flask run --no-reload` (or `flask run --debug --no-reload` / `FLASK_DEBUG=1 flask run --no-reload`) is disabled ((c) fails).
- An inherited `WERKZEUG_RUN_MAIN=true` with plain `flask run` and no debug (`FLASK_DEBUG` unset/falsy, no `--debug`, no `--reload`) is disabled ((d) fails).
- `python app.py` with `app.run(debug=True)` gives disabled in both the parent and the `WERKZEUG_RUN_MAIN=true` child ((b) fails because `argv` is not a Flask CLI `run` invocation). **Known limit:** programmatic `app.run(debug=True)` is not auto-detected (matching programmatic `uvicorn.run(..., reload=True)` in `src/sharpit/fastapi/signals.py:11`); the user sets `SHARPIT_ENABLED=ON`.
- An application subprocess inheriting `WERKZEUG_RUN_MAIN=true` (whose `argv` is not a Flask CLI `run` invocation) is disabled ((b) fails).
- `gunicorn` and `gunicorn --reload` are disabled ((a) and (b) fail; Gunicorn is not a recognized Flask dev-server signal).

### 4.3 Activation Matrix for Flask

All `enabled` values and `ActivationStatus.reason` strings below match `decide()` in `src/sharpit/engine/activation.py:39-69` (with `SHARPIT_ENABLED` unset / `AUTO` and no active `SHARPIT_PROFILES` unless noted):

| Command / Environment | Parent (`WERKZEUG_RUN_MAIN` unset) | Serving Child / Process with `WERKZEUG_RUN_MAIN=true` | `dev_server_signal()` in Child | `ActivationStatus.enabled` (Parent / Child) | `ActivationStatus.reason` in Serving Process (`src/sharpit/engine/activation.py:48-69`) |
|---|---|---|---|---|---|
| `flask run` (no debug, no `--reload`) | Disabled ((a), (d) false) | No child spawned | `None` | `False` / — | `"Disabled: no enabled profile and no reloading development server detected"` |
| `flask run --debug` | Disabled ((a) false; parent is reloader watcher) | Enabled ((a)–(d) all hold) | `"flask run --debug"` | `False` / `True` | `"Enabled because a reloading development server was detected (flask run --debug)"` |
| `FLASK_DEBUG=1 flask run` | Disabled ((a) false; parent is reloader watcher) | Enabled ((a)–(d) all hold; `flask/cli.py` derives `reload = debug`) | `"flask run --debug"` | `False` / `True` | `"Enabled because a reloading development server was detected (flask run --debug)"` |
| `flask run --reload` | Disabled ((a) false; parent is reloader watcher) | Enabled ((a)–(d) all hold) | `"flask run --reload"` | `False` / `True` | `"Enabled because a reloading development server was detected (flask run --reload)"` |
| `flask run --debug --no-reload` or `FLASK_DEBUG=1 flask run --no-reload` | Disabled ((a), (c) false; `--no-reload` disables reloader) | No child spawned | `None` | `False` / — | `"Disabled: no enabled profile and no reloading development server detected"` |
| Inherited `WERKZEUG_RUN_MAIN=true` with `flask run --no-reload` (or `flask run --debug --no-reload`) | — | Disabled ((c) false: `--no-reload` is present) | `None` | — / `False` | `"Disabled: no enabled profile and no reloading development server detected"` |
| Inherited `WERKZEUG_RUN_MAIN=true` with plain `flask run` and no debug | — | Disabled ((d) false: reloading and debug are both off) | `None` | — / `False` | `"Disabled: no enabled profile and no reloading development server detected"` |
| `python app.py` with `app.run(debug=True)` (known limit: user sets `SHARPIT_ENABLED=ON`) | Disabled ((a), (b) false) | Disabled ((b) false: `argv` is `app.py`, not Flask CLI `run`) | `None` | `False` / `False` | `"Disabled: no enabled profile and no reloading development server detected"` |
| App subprocess inheriting `WERKZEUG_RUN_MAIN=true` (non-`flask run` `argv`) | — | Disabled ((b) false: `argv` is not Flask CLI `run`) | `None` | — / `False` | `"Disabled: no enabled profile and no reloading development server detected"` |
| `gunicorn app:app` or `gunicorn --reload app:app` | Disabled ((a), (b) false) | Disabled ((a), (b) false) | `None` | `False` / `False` | `"Disabled: no enabled profile and no reloading development server detected"` |
| Any invocation with `SHARPIT_ENABLED=OFF` | Disabled | Disabled | any | `False` / `False` | `"Disabled by SHARPIT_ENABLED=OFF"` |
| Any invocation with `SHARPIT_ENABLED=ON` (and `SHARPIT_PROFILES=prod`) | Enabled (with warning) | Enabled (with warning) | any | `True` / `True` | `"Explicitly enabled (SHARPIT_ENABLED=ON) despite disabled profile 'prod'"` |
| `flask run` with `SHARPIT_PROFILES=dev` | Enabled | — | `None` | `True` / — | `"Enabled by active profile 'dev'"` |

### 4.4 Proposed Wording Change to Safety Rule 1 in `AGENTS.md`

*(Proposal for the maintainer; `AGENTS.md` is not modified by F0 and changes only in F3's pull request alongside `tests/engine/test_import_boundary.py` / `signals.py` per `PLAN.md:19-20, 244-245`.)*

Current wording in `AGENTS.md` (Safety model, rule 1):
> 1. **Fails closed.** Activation order: a disabled profile disables (unless `SHARPIT_ENABLED=ON`, with a warning) →
>    `OFF` disables → `ON` enables → an enabled profile enables → a reloading dev server (`uvicorn --reload`,
>    `fastapi dev`) enables → otherwise disabled. Inactive means every path under the mount answers 404.

**Proposal for the maintainer — `AGENTS.md` Safety model, rule 1 wording:**
> 1. **Fails closed.** Activation order: a disabled profile disables (unless `SHARPIT_ENABLED=ON`, with a warning) →
>    `OFF` disables → `ON` enables → an enabled profile enables → a reloading dev server (`uvicorn --reload`,
>    `fastapi dev`, or the Flask CLI reloader serving child when all four hold: `WERKZEUG_RUN_MAIN == "true"`, `argv` is
>    a `flask` / `python -m flask` `run` invocation with `run` as the first positional command, `--no-reload` is absent,
>    and reloading is on via `--reload`, `--debug`, or truthy `FLASK_DEBUG`) enables → otherwise disabled (the reloader
>    parent, an inherited `WERKZEUG_RUN_MAIN` with `flask run --no-reload` or plain `flask run` without debug,
>    `python app.py` with `app.run(debug=True)`, and `gunicorn` with or without `--reload` stay disabled). Inactive
>    means every path under the mount answers 404.

---

## 5. Order of F2's Panel Batches and Route Modules Moved

`src/sharpit/fastapi/routes/` contains `routes/__init__.py` (`1-716`) plus 38 sibling modules. In F2, every one of the 38 sibling modules and every inline route builder function in `src/sharpit/fastapi/routes/__init__.py` moves into `src/sharpit/engine/console/routes/` in **exactly one** batch below.

Ordering rules:
1. **No stream route moves before the Decision 2 stream spike and tests merge.** Batches 1–4 contain zero SSE streaming routes and can proceed as soon as F0 and F1 merge. Batches 5 and 6 contain all 8 SSE streaming routes plus `src/sharpit/fastapi/sse.py` and are gated by the stream decision.
2. **Each batch proves F1 response corpus identity before the next batch starts.** After each batch pull request, the F1 transport and panel corpora, the `no_side_effects` suite, and the overhead budgets (`tests/fastapi/test_sql_trace_overhead.py`, `tests/fastapi/test_transactions_overhead.py`) must pass unchanged.

| Batch | Focus | Sibling Modules in `src/sharpit/fastapi/routes/` (count) | Inline Builders in `src/sharpit/fastapi/routes/__init__.py` | Routes Covered |
|---|---|---|---|---|
| **Batch 1** | UI shell, assets, session auth, panel discovery, overview, config, mappings, loggers, beans, startup, scheduled | `config_overrides.py`, `profile_diff.py`, `startup.py`, `scheduled.py` (4) | `_root_routes` (`104-136`), `_read_routes` (`139-173`), `_logger_routes` (`264-283`) | `GET /`, `GET /assets/{file}`, `POST /api/auth/session`, `GET /api/panels`, `GET /api/overview`, `GET /api/config`, `POST /api/config/overrides`, `DELETE /api/config/overrides/{name}`, `GET /api/profile-diff`, `GET /api/loggers`, `POST /api/loggers/{name:path}`, `GET /api/mappings/flat`, `GET /api/beans`, `GET /api/startup`, `GET /api/scheduled` |
| **Batch 2** | Database, SQLAlchemy, Alembic, pools, health, data, dialects, database advisor, SQLAlchemy statistics, SQL trace insights, cache, dev-services | `data.py`, `postgresql.py`, `mysql.py`, `database_advisor.py`, `sqlalchemy_statistics.py`, `sql_trace.py`, `cache.py`, `dev_services.py` (8) | `_alembic_action_handler` (`426-442`), `_database_routes` (`445-477`), `_pool_routes` (`480-498`) | `GET /api/alembic/migrations`, `POST /api/alembic/refresh`, `POST /api/alembic/migrate`, `POST /api/alembic/clean`, `GET /api/health`, `POST /api/health/check`, `GET /api/database-connection-pools/pools`, `GET /api/database-connection-pools/pools/{name:path}/snapshot`, `GET /api/data/repositories`, `GET /api/data/repositories/{name:path}`, `GET /api/postgresql`, `POST /api/postgresql/read`, `GET /api/mysql`, `POST /api/mysql/read`, `GET /api/database-advisor`, `POST /api/database-advisor/scan`, `GET /api/database-advisor/rules/{rule_id}/violations`, `GET /api/sqlalchemy-statistics`, `POST /api/sqlalchemy-statistics/enable`, `GET /api/sql-trace/insights`, `POST /api/cache/clear` (`IMPLEMENTED = False`), `dev_services.py` (`IMPLEMENTED = False`) |
| **Batch 3** | Advisors, rule & finding dismissals, vulnerabilities, REST API & error contract, HTTP probe, app security, pentesting | `dismissed_findings.py`, `architecture.py`, `security.py`, `fastapi.py`, `fastapi_security.py`, `pentesting.py` (6) | `_http_probe` & `_http_probe_routes` (`304-366`), `_vulnerability_routes` (`515-534`), `_rest_api_routes` (`537-579`), `_dismissed_routes` (`582-598`) | `POST /api/http-probe`, `GET /api/vulnerabilities`, `POST /api/vulnerabilities/scan`, `GET /api/rest-api`, `GET /api/rest-api/error-contract`, `POST /api/rest-api/scan`, `GET /api/rest-api/rules/{rule_id}/violations`, `GET /api/dismissed-rules`, `POST, DELETE /api/dismissed-rules/{rule_id:path}`, `GET /api/dismissed-findings`, `POST, DELETE /api/dismissed-findings`, `GET /api/architecture`, `POST /api/architecture/scan`, `GET /api/architecture/rules/{rule_id}/violations`, `GET /api/security`, `POST /api/security/scan`, `GET /api/security/rules/{rule_id}/violations`, `GET /api/fastapi`, `POST /api/fastapi/scan`, `GET /api/fastapi/rules/{rule_id}/violations`, `GET /api/fastapi-security`, `GET /api/fastapi-security/explain`, `GET /api/fastapi-security/endpoints`, `GET /api/pentesting`, `POST /api/pentesting/scan` |
| **Batch 4** | Runtime observability, threads, live memory, metrics, traces, email, runtime insights, sensors, GitHub, AI | `lowfootprint.py`, `metrics.py`, `traces.py`, `email.py`, `runtime_insights.py`, `java_agent.py`, `code_inventory.py`, `code_paths.py`, `side_effects.py`, `github.py`, `ai.py` (11) | `_thread_routes` (`501-512`) | `GET /api/threads`, `GET /api/live-memory/footprint`, `POST /api/live-memory/footprint`, `GET /api/metrics`, `GET /api/metrics/detail`, `GET, DELETE /api/traces`, `GET /api/traces/{id}`, `GET, DELETE /api/email`, `GET /api/email/{id}`, `GET /api/email/{id}/eml`, `GET /api/runtime-insights`, `GET /api/runtime-insights/insights/{observation_id}`, `GET /api/runtime-insights/resource-profile`, `POST /api/runtime-insights/resource-profile`, `POST /api/runtime-insights/resource-profile/stop`, `GET /api/java-agent`, `POST /api/java-agent/sensors/{sensor}`, `GET /api/code-inventory`, `GET /api/code-inventory/changes`, `GET /api/code-inventory/methods`, `GET /api/code-inventory/dependencies`, `GET /api/code-paths`, `GET /api/code-paths/route`, `GET /api/code-paths/beans`, `GET /api/code-paths/requests/{id}`, `GET /api/code-paths/probes`, `POST /api/code-paths/probes`, `POST /api/code-paths/probes/{id}/stop`, `GET, DELETE /api/code-paths/probes/{id}`, `GET /api/side-effects`, `GET /api/side-effects/sensor`, `GET /api/github`, `POST /api/github/refresh`, `GET /api/ai/overview`, `GET /api/ai/chats`, `GET /api/ai/chats/{spanId}`, `GET /api/ai/tokens` |
| **Batch 5** *(gated by stream decision)* | Live capture buffers & core SSE streams (`src/sharpit/fastapi/sse.py`), activity, log tail, SQL trace, HTTP exchanges, exceptions, transactions, security logs | `activity.py`, `http_exchanges.py`, `exceptions.py`, `transactions.py`, `security_logs.py` (5) | `_activity_routes` (`176-219`), `_sql_trace_routes` (`222-261`), `_http_exchange_routes` (`286-301`), `_exception_routes` (`369-392`), `_exception_status_routes` (`395-416`) | `GET /api/activity`, `GET /api/activity/resources`, `GET /api/activity/journal`, `GET /api/activity/stream`, `GET /api/activity/request/{id}`, `GET /api/log-tail/recent`, `GET /api/log-tail/stream`, `GET /api/sql-trace`, `GET /api/sql-trace/stream`, `POST /api/sql-trace/clear`, `POST /api/sql-trace/recording`, `GET /api/http-exchanges`, `GET /api/http-exchanges/routes`, `GET /api/exceptions/caught`, `GET, DELETE /api/exceptions`, `GET /api/exceptions/stream`, `GET /api/exceptions/{id}`, `POST /api/exceptions/{id}/status`, `GET /api/transactions`, `POST /api/transactions/clear`, `POST /api/transactions/recording`, `GET /api/transactions/stream`, `GET /api/security-logs`, `GET /api/security-logs/stream` |
| **Batch 6** *(gated by stream decision)* | Agent sessions (`copilot`, `claude-code`) & streams, MCP server, CLI gateway; retires `_with_drift_routes` and `routes/__init__.py` | `agent_sessions.py`, `agent_sessions_stream.py`, `copilot.py`, `claude_code.py` (4) | `_mcp_routes` (`601-649`), `_cli_routes` (`652-677`), `_panel_04_routes` (`680-689`), `build_routes` (`692-716`) | `GET /api/copilot/sessions`, `GET /api/copilot/dashboard`, `GET /api/copilot/sessions/{id}`, `GET /api/copilot/sessions/{id}/events`, `GET /api/copilot/sessions/{id}/events/{eventId}/raw`, `GET /api/copilot/stream`, `GET /api/claude-code/sessions`, `GET /api/claude-code/dashboard`, `GET /api/claude-code/sessions/{id}`, `GET /api/claude-code/sessions/{id}/events`, `GET /api/claude-code/sessions/{id}/events/{eventId}/raw`, `GET /api/claude-code/stream`, `POST /api/mcp`, `GET /api/mcp-server`, `POST /api/mcp-server/toggle`, `GET /api/cli`, `POST /api/cli/tools/{tool}` |

Module count check: `4 + 8 + 6 + 11 + 5 + 4 = 38` sibling modules, plus `src/sharpit/fastapi/routes/__init__.py` (`39` files total under `src/sharpit/fastapi/routes/`).

---

## Appendix A: Grounded Code Citations and Verification Commands

Every file, line range, and symbol cited across `f0-console-contract.md`, `f0-console-contract-scenario.md`, and `f0b-flask-panel-availability.md` was verified against the working tree after merging `origin/release/0.9.0`.

| File & Line Range | Cited Symbols | Verification Command |
|---|---|---|
| `src/sharpit/engine/activation.py:14-69` | `ActivationStatus`, `ActivationStatus.enabled`, `ActivationStatus.reason`, `active_profiles`, `decide` | `git grep -n "class ActivationStatus\|def active_profiles\|def decide" src/sharpit/engine/activation.py` |
| `src/sharpit/engine/advisors/dismissals.py:55-220` | `DismissedFinding`, `Findings`, `owning_panel`, `DismissalStore` | `git grep -n "class DismissedFinding\|class Findings\|def owning_panel\|class DismissalStore" src/sharpit/engine/advisors/dismissals.py` |
| `src/sharpit/engine/advisors/retention.py:19-36` | `AdvisorViolationError`, `parse_integer` | `git grep -n "class AdvisorViolationError\|def parse_integer" src/sharpit/engine/advisors/retention.py` |
| `src/sharpit/engine/capture/__init__.py:21-114` | `CaptureHooks`, `CaptureHooks.hook_failed`, `CaptureState`, `route_path`, `under` | `git grep -n "class CaptureHooks\|def hook_failed\|class CaptureState\|def route_path\|def under" src/sharpit/engine/capture/__init__.py` |
| `src/sharpit/engine/capture/activity.py:82-386` | `unavailable_reason`, `activity_report`, `request_profile`, `journal_status_dto`, `resources_dto` | `git grep -n "def unavailable_reason\|def activity_report\|def request_profile\|def journal_status_dto\|def resources_dto" src/sharpit/engine/capture/activity.py` |
| `src/sharpit/engine/capture/correlation.py:21-77` | `paging_of`, `RequestInfo`, `REQUEST`, `TEST`, `INTERNAL`, `new_request_id` | `git grep -n "def paging_of\|class RequestInfo\|REQUEST:\|TEST:\|INTERNAL:\|def new_request_id" src/sharpit/engine/capture/correlation.py` |
| `src/sharpit/engine/capture/exceptions.py:101,217-533` | `CAUGHT_UNAVAILABLE`, `caught_report`, `ExceptionStore`, `unknown_group` | `git grep -n "CAUGHT_UNAVAILABLE\|def caught_report\|class ExceptionStore\|def unknown_group" src/sharpit/engine/capture/exceptions.py` |
| `src/sharpit/engine/capture/exchanges.py:80-269` | `exchange_row`, `http_event`, `unavailable_report`, `HttpExchangeBuffer` | `git grep -n "def exchange_row\|def http_event\|def unavailable_report\|class HttpExchangeBuffer" src/sharpit/engine/capture/exchanges.py` |
| `src/sharpit/engine/capture/journal.py:239-457` | `RuntimeJournal` | `git grep -n "class RuntimeJournal" src/sharpit/engine/capture/journal.py` |
| `src/sharpit/engine/capture/logtail.py:36-363` | `LogTailBuffer`, `log_events`, `SharpitLogHandler` | `git grep -n "class LogTailBuffer\|async def log_events\|class SharpitLogHandler" src/sharpit/engine/capture/logtail.py` |
| `src/sharpit/engine/capture/mail.py:180-720` | `MailRecorder`, `ensure_wrapped`, `attach` | `git grep -n "class MailRecorder\|def ensure_wrapped\|def attach" src/sharpit/engine/capture/mail.py` |
| `src/sharpit/engine/capture/mailview.py:96-146` | `email_report`, `email_message`, `clear_emails`, `render_eml` | `git grep -n "def email_report\|def email_message\|def clear_emails\|def render_eml" src/sharpit/engine/capture/mailview.py` |
| `src/sharpit/engine/capture/securitylogs.py:59-295` | `SecurityEventBuffer`, `security_logs_report`, `context_report`, `on_security_event`, `attach` | `git grep -n "class SecurityEventBuffer\|def security_logs_report\|def context_report\|def on_security_event\|def attach" src/sharpit/engine/capture/securitylogs.py` |
| `src/sharpit/engine/capture/sqltrace.py:183-452` | `SqlTraceRecorder` | `git grep -n "class SqlTraceRecorder" src/sharpit/engine/capture/sqltrace.py` |
| `src/sharpit/engine/capture/streams.py:20-228` | `SSE_TASK`, `TICK_SECONDS`, `LINE_QUEUE`, `MAX_STREAMS`, `StreamSlots`, `_Ticker`, `Subscription`, `LineSubscription`, `_Hub`, `ChangeStream`, `LineStream`, `change_events` | `git grep -n "SSE_TASK\|TICK_SECONDS\|LINE_QUEUE\|MAX_STREAMS\|class StreamSlots\|class _Ticker\|class Subscription\|class LineSubscription\|class _Hub\|class ChangeStream\|class LineStream\|async def change_events" src/sharpit/engine/capture/streams.py` |
| `src/sharpit/engine/capture/traces.py:251-457` | `SpanBuffer`, `span_buffer` | `git grep -n "class SpanBuffer\|def span_buffer" src/sharpit/engine/capture/traces.py` |
| `src/sharpit/engine/capture/transactions.py:94-569` | `context_report`, `TransactionRecorder`, `attach` | `git grep -n "def context_report\|class TransactionRecorder\|def attach" src/sharpit/engine/capture/transactions.py` |
| `src/sharpit/engine/collectors/agentsessions/__init__.py:15-56` | `AgentSessionSettings`, `copilot_settings`, `claude_code_settings`, `session_store` | `git grep -n "class AgentSessionSettings\|def copilot_settings\|def claude_code_settings\|def session_store" src/sharpit/engine/collectors/agentsessions/__init__.py` |
| `src/sharpit/engine/collectors/agentsessions/store.py:140-366` | `SessionStore` | `git grep -n "class SessionStore" src/sharpit/engine/collectors/agentsessions/store.py` |
| `src/sharpit/engine/collectors/ai/usage.py:177-356` | `ai_overview`, `ai_chats`, `ai_chat_detail`, `ai_tokens` | `git grep -n "def ai_overview\|def ai_chats\|def ai_chat_detail\|def ai_tokens" src/sharpit/engine/collectors/ai/usage.py` |
| `src/sharpit/engine/collectors/alembic.py:292-630` | `unavailable_reason`, `alembic_report`, `refresh_alembic`, `migrate`, `clean` | `git grep -n "def unavailable_reason\|def alembic_report\|async def refresh_alembic\|def migrate\|def clean" src/sharpit/engine/collectors/alembic.py` |
| `src/sharpit/engine/collectors/alembic_cli.py:98-140` | `run_alembic` | `git grep -n "def run_alembic" src/sharpit/engine/collectors/alembic_cli.py` |
| `src/sharpit/engine/collectors/appsecurity.py:15-194` | `model_of`, `security_report`, `endpoints_report`, `explain` | `git grep -n "def model_of\|def security_report\|def endpoints_report\|def explain" src/sharpit/engine/collectors/appsecurity.py` |
| `src/sharpit/engine/collectors/architecture/report.py:73-185` | `scan_application`, `ArchitectureService`, `architecture_service` | `git grep -n "def scan_application\|class ArchitectureService\|def architecture_service" src/sharpit/engine/collectors/architecture/report.py` |
| `src/sharpit/engine/collectors/beans.py:27-36` | `beans_report` | `git grep -n "def beans_report" src/sharpit/engine/collectors/beans.py` |
| `src/sharpit/engine/collectors/cache/clear.py:180-361` | `CacheService` | `git grep -n "class CacheService" src/sharpit/engine/collectors/cache/clear.py` |
| `src/sharpit/engine/collectors/config/__init__.py:69-152` | `config_report` | `git grep -n "def config_report" src/sharpit/engine/collectors/config/__init__.py` |
| `src/sharpit/engine/collectors/config/overrides.py:288-449` | `ConfigOverrideService`, `apply_overrides_file`, `override_service` | `git grep -n "class ConfigOverrideService\|def apply_overrides_file\|def override_service" src/sharpit/engine/collectors/config/overrides.py` |
| `src/sharpit/engine/collectors/config/profiles.py:148-180` | `profiles_report` | `git grep -n "def profiles_report" src/sharpit/engine/collectors/config/profiles.py` |
| `src/sharpit/engine/collectors/data.py:143-188` | `repositories_report`, `repository_detail` | `git grep -n "def repositories_report\|def repository_detail" src/sharpit/engine/collectors/data.py` |
| `src/sharpit/engine/collectors/database_advisor/report.py:226-272` | `DatabaseAdvisorService`, `run_scan` | `git grep -n "class DatabaseAdvisorService\|async def run_scan" src/sharpit/engine/collectors/database_advisor/report.py` |
| `src/sharpit/engine/collectors/fastapi_advisor/report.py:113-135` | `FastapiAdvisor` | `git grep -n "class FastapiAdvisor" src/sharpit/engine/collectors/fastapi_advisor/report.py` |
| `src/sharpit/engine/collectors/github/dashboard.py:22-94` | `GitHubDashboard` | `git grep -n "class GitHubDashboard" src/sharpit/engine/collectors/github/dashboard.py` |
| `src/sharpit/engine/collectors/health.py:78-267` | `HealthService`, `health_service` | `git grep -n "class HealthService\|def health_service" src/sharpit/engine/collectors/health.py` |
| `src/sharpit/engine/collectors/insights/service.py:258-437` | `InsightsService`, `insights_service` | `git grep -n "class InsightsService\|def insights_service" src/sharpit/engine/collectors/insights/service.py` |
| `src/sharpit/engine/collectors/loggers.py:28-53` | `loggers_report`, `set_level` | `git grep -n "def loggers_report\|def set_level" src/sharpit/engine/collectors/loggers.py` |
| `src/sharpit/engine/collectors/mappings.py:37-56` | `mappings_flat` | `git grep -n "def mappings_flat" src/sharpit/engine/collectors/mappings.py` |
| `src/sharpit/engine/collectors/metrics/__init__.py:37-394` | `MetricsRequestError`, `metrics_report`, `metric_detail` | `git grep -n "class MetricsRequestError\|def metrics_report\|def metric_detail" src/sharpit/engine/collectors/metrics/__init__.py` |
| `src/sharpit/engine/collectors/mysql/service.py:75-114` | `mysql_report`, `has_async_engine`, `unavailable_report`, `refresh_mysql` | `git grep -n "def mysql_report\|def has_async_engine\|def unavailable_report\|async def refresh_mysql" src/sharpit/engine/collectors/mysql/service.py` |
| `src/sharpit/engine/collectors/overview.py:19-46` | `overview_dto` | `git grep -n "def overview_dto" src/sharpit/engine/collectors/overview.py` |
| `src/sharpit/engine/collectors/pentesting/service.py:18-44` | `PentestingService` | `git grep -n "class PentestingService" src/sharpit/engine/collectors/pentesting/service.py` |
| `src/sharpit/engine/collectors/pools.py:75-84` | `pools_report`, `pool_snapshot` | `git grep -n "def pools_report\|def pool_snapshot" src/sharpit/engine/collectors/pools.py` |
| `src/sharpit/engine/collectors/postgresql/service.py:72-111` | `postgresql_report`, `has_async_engine`, `unavailable_report`, `refresh_postgresql` | `git grep -n "def postgresql_report\|def has_async_engine\|def unavailable_report\|async def refresh_postgresql" src/sharpit/engine/collectors/postgresql/service.py` |
| `src/sharpit/engine/collectors/restapi/error_contract.py:305-339` | `error_contract_report` | `git grep -n "def error_contract_report" src/sharpit/engine/collectors/restapi/error_contract.py` |
| `src/sharpit/engine/collectors/restapi/service.py:168-190` | `RestApiService` | `git grep -n "class RestApiService" src/sharpit/engine/collectors/restapi/service.py` |
| `src/sharpit/engine/collectors/scheduled/__init__.py:77-78` | `scheduled_report` | `git grep -n "def scheduled_report" src/sharpit/engine/collectors/scheduled/__init__.py` |
| `src/sharpit/engine/collectors/security/report.py:232-273` | `build_inputs`, `SecurityService` | `git grep -n "def build_inputs\|class SecurityService" src/sharpit/engine/collectors/security/report.py` |
| `src/sharpit/engine/collectors/sqlastats.py:132-157` | `statistics_report` | `git grep -n "def statistics_report" src/sharpit/engine/collectors/sqlastats.py` |
| `src/sharpit/engine/collectors/startup.py:37-69` | `StartupTimeline`, `startup_report`, `startup_view` | `git grep -n "class StartupTimeline\|def startup_report\|def startup_view" src/sharpit/engine/collectors/startup.py` |
| `src/sharpit/engine/collectors/threads.py:153-254` | `_collect`, `_tasks`, `threads_report` | `git grep -n "def _collect\|def _tasks\|def threads_report" src/sharpit/engine/collectors/threads.py` |
| `src/sharpit/engine/collectors/vulns/service.py:77-203` | `VulnerabilityService` | `git grep -n "class VulnerabilityService" src/sharpit/engine/collectors/vulns/service.py` |
| `src/sharpit/engine/context.py:27-90` | `SharpitContext`, `SharpitContext.lazy`, `application_family` | `git grep -n "class SharpitContext\|def lazy\|def application_family" src/sharpit/engine/context.py` |
| `src/sharpit/engine/daemon_executor.py:14-35` | `DaemonExecutor` | `git grep -n "class DaemonExecutor" src/sharpit/engine/daemon_executor.py` |
| `src/sharpit/engine/guard.py:24-435` | `SESSION_COOKIE`, `MESSAGE_NON_LOOPBACK_SOURCE`, `MESSAGE_FORWARDED_SOURCE`, `MESSAGE_DISALLOWED_HOST`, `MESSAGE_CROSS_SITE`, `AUTHENTICATION_REQUIRED_MESSAGE`, `PANEL_ACCESS_DENIED`, `_SAFE_METHODS`, `RequestFacts`, `Denial`, `extract_request_host`, `extract_origin_host`, `is_trusted_source`, `_session_cookie`, `_is_cross_site`, `_panel_access`, `owning_panel_access`, `decide_guard`, `detect_container_gateway` | `git grep -n "SESSION_COOKIE =\|MESSAGE_NON_LOOPBACK_SOURCE =\|MESSAGE_FORWARDED_SOURCE =\|MESSAGE_DISALLOWED_HOST =\|MESSAGE_CROSS_SITE =\|AUTHENTICATION_REQUIRED_MESSAGE =\|PANEL_ACCESS_DENIED =\|_SAFE_METHODS =\|class RequestFacts\|class Denial\|def extract_request_host\|def extract_origin_host\|def is_trusted_source\|def _session_cookie\|def _is_cross_site\|def _panel_access\|def owning_panel_access\|def decide_guard\|def detect_container_gateway" src/sharpit/engine/guard.py` |
| `src/sharpit/engine/headers.py:7-32` | `CSP`, `PERMISSIONS_POLICY`, `NO_STORE`, `IMMUTABLE`, `NO_CACHE`, `security_headers` | `git grep -n "CSP =\|PERMISSIONS_POLICY =\|NO_STORE =\|IMMUTABLE =\|NO_CACHE =\|def security_headers" src/sharpit/engine/headers.py` |
| `src/sharpit/engine/lowfootprint.py:11-50` | `LowFootprintService` | `git grep -n "class LowFootprintService" src/sharpit/engine/lowfootprint.py` |
| `src/sharpit/engine/masking.py:609-620` | `Masker.mask_text` | `git grep -n "def mask_text" src/sharpit/engine/masking.py` |
| `src/sharpit/engine/mcp.py:324,379-557` | `McpServer`, `McpServer.handle`, `McpServer._call_tool`, `payload_too_large` | `git grep -n "class McpServer\|def handle(\|def _call_tool(\|def payload_too_large" src/sharpit/engine/mcp.py` |
| `src/sharpit/engine/otel.py:71-128` | `SharpitSpanProcessor`, `attach`, `disarm` | `git grep -n "class SharpitSpanProcessor\|def attach\|def disarm" src/sharpit/engine/otel.py` |
| `src/sharpit/engine/paging.py:11-43` | `BadRequest`, `parse_int_param`, `paged` | `git grep -n "class BadRequest\|def parse_int_param\|def paged" src/sharpit/engine/paging.py` |
| `src/sharpit/engine/panels.py:13-132` | `Panel`, `PANELS`, `disabled_reason`, `read_only_reason`, `panel_for_api_path`, `panels_report` | `git grep -n "class Panel\|PANELS:\|def disabled_reason\|def read_only_reason\|def panel_for_api_path\|def panels_report" src/sharpit/engine/panels.py` |
| `src/sharpit/engine/panels04/__init__.py:37-77` | `IMPLEMENTED`, `MODULE_PANEL_IDS`, `module_implemented` | `git grep -n "IMPLEMENTED =\|MODULE_PANEL_IDS =\|def module_implemented" src/sharpit/engine/panels04/__init__.py` |
| `src/sharpit/engine/probe.py:49-370` | `ProbeRequest`, `validate_probe`, `ProbeSlots`, `run_probe` | `git grep -n "class ProbeRequest\|def validate_probe\|class ProbeSlots\|async def run_probe" src/sharpit/engine/probe.py` |
| `src/sharpit/engine/sensors/floor.py:109-383` | `SensorRefusal`, `java_agent_report`, `switch_sensor`, `code_inventory_report`, `code_paths_report`, `side_effects_report` | `git grep -n "class SensorRefusal\|def java_agent_report\|def switch_sensor\|def code_inventory_report\|def code_paths_report\|def side_effects_report" src/sharpit/engine/sensors/floor.py` |
| `src/sharpit/engine/spi.py:10-180` | `HostLoopProvider`, `AppInfo`, `RouteInfo`, `ApiModel`, `ProviderInfo`, `AppIntrospector`, `SecurityModel`, `SecurityFacts` | `git grep -n "class HostLoopProvider\|class AppInfo\|class RouteInfo\|class ApiModel\|class ProviderInfo\|class AppIntrospector\|class SecurityModel\|class SecurityFacts" src/sharpit/engine/spi.py` |
| `src/sharpit/engine/sqla/__init__.py:39-103` | `unavailable_reason`, `sql_trace_unavailable_reason` | `git grep -n "def unavailable_reason\|def sql_trace_unavailable_reason" src/sharpit/engine/sqla/__init__.py` |
| `src/sharpit/engine/sqla/inspect.py:298-389` | `EngineRegistry` | `git grep -n "class EngineRegistry" src/sharpit/engine/sqla/inspect.py` |
| `src/sharpit/engine/sqla/listeners.py:59-337` | `before_cursor_execute`, `after_cursor_execute`, `handle_error`, `add`, `remove` | `git grep -n "def before_cursor_execute\|def after_cursor_execute\|def handle_error\|def add(\|def remove(" src/sharpit/engine/sqla/listeners.py` |
| `src/sharpit/engine/tool_dispatch.py:45-293` | `ToolGate`, `call_tool`, `cli_status`, `cli_invoke` | `git grep -n "class ToolGate\|def call_tool\|def cli_status\|def cli_invoke" src/sharpit/engine/tool_dispatch.py` |
| `src/sharpit/engine/tools.py:101-746` | `CallContext`, `_BoundHostLoopProvider`, `Tool`, `TOOLS`, `COMMANDS` | `git grep -n "class CallContext\|class _BoundHostLoopProvider\|class Tool\|TOOLS, COMMANDS" src/sharpit/engine/tools.py` |
| `src/sharpit/engine/tools04/database_advisor.py:53-68` | `_scan` | `git grep -n "def _scan" src/sharpit/engine/tools04/database_advisor.py` |
| `src/sharpit/engine/tools04/hostloop.py:14-37` | `running_host_loop`, `wait_on_host_loop` | `git grep -n "def running_host_loop\|def wait_on_host_loop" src/sharpit/engine/tools04/hostloop.py` |
| `src/sharpit/engine/tools04/mysql.py:33-49` | `_read` | `git grep -n "def _read" src/sharpit/engine/tools04/mysql.py` |
| `src/sharpit/engine/tools04/pentesting.py:21-37` | `_scan` | `git grep -n "def _scan" src/sharpit/engine/tools04/pentesting.py` |
| `src/sharpit/engine/tools04/postgresql.py:33-49` | `_read` | `git grep -n "def _read" src/sharpit/engine/tools04/postgresql.py` |
| `src/sharpit/fastapi/adapter.py:55-284` | `_STATIC`, `_ASSETS`, `_TRUSTED_KEY`, `_SMALL_BODY_CAP`, `SharpitMount`, `_header_map`, `GuardMiddleware`, `available_reasons`, `_toggle_value`, `_read_capped`, `_json_or_none`, `_page`, `_bad_request`, `_json_http_error`, `_not_found`, `_routes`, `_with_drift_routes` | `git grep -n "_STATIC =\|class SharpitMount\|def _header_map\|class GuardMiddleware\|def available_reasons\|def _toggle_value\|async def _read_capped\|def _json_or_none\|def _page\|async def _bad_request\|async def _json_http_error\|async def _not_found\|def _routes\|def _with_drift_routes" src/sharpit/fastapi/adapter.py` |
| `src/sharpit/fastapi/capture.py:70-701` | `PROBE_EXTENSION`, `CaptureWiring`, `CaptureMiddleware` | `git grep -n "PROBE_EXTENSION =\|class CaptureWiring\|class CaptureMiddleware" src/sharpit/fastapi/capture.py` |
| `src/sharpit/fastapi/capture_exceptions.py:46-241` | `_record_exception`, `_route_template`, `_wrap_handler`, `WrappingHandlers`, `unwrap_exception_handlers`, `_record_logged` | `git grep -n "def _record_exception\|def _route_template\|def _wrap_handler\|class WrappingHandlers\|def unwrap_exception_handlers\|def _record_logged" src/sharpit/fastapi/capture_exceptions.py` |
| `src/sharpit/fastapi/http.py:12-18` | `json_response`, `error` | `git grep -n "def json_response\|def error" src/sharpit/fastapi/http.py` |
| `src/sharpit/fastapi/install.py:52-388` | `IdleTracker`, `_configure_capture`, `install`, `_activity_middleware` | `git grep -n "class IdleTracker\|def _configure_capture\|def install(\|def _activity_middleware" src/sharpit/fastapi/install.py` |
| `src/sharpit/fastapi/introspector.py:431-900` | `FastApiIntrospector` | `git grep -n "class FastApiIntrospector" src/sharpit/fastapi/introspector.py` |
| `src/sharpit/fastapi/pentesting_exposure.py:18-90` | `read_security_facts`, `framework_evidence` | `git grep -n "def read_security_facts\|def framework_evidence" src/sharpit/fastapi/pentesting_exposure.py` |
| `src/sharpit/fastapi/pentesting_probe.py:34-139` | `probe`, `run_probe`, `_request` | `git grep -n "async def probe\|async def run_probe\|async def _request" src/sharpit/fastapi/pentesting_probe.py` |
| `src/sharpit/fastapi/request_id_header.py:15-51` | `HEADER`, `with_request_id_header` | `git grep -n "HEADER =\|def with_request_id_header" src/sharpit/fastapi/request_id_header.py` |
| `src/sharpit/fastapi/routes/__init__.py:50-716` | `_RequestHostLoopProvider`, `_root_routes`, `_read_routes`, `_activity_routes`, `_sql_trace_routes`, `_logger_routes`, `_http_exchange_routes`, `_http_probe`, `_http_probe_routes`, `_exception_routes`, `_exception_status_routes`, `_alembic_action_handler`, `_database_routes`, `_pool_routes`, `_thread_routes`, `_vulnerability_routes`, `_rest_api_routes`, `_dismissed_routes`, `_mcp_routes`, `_cli_routes`, `_panel_04_routes`, `build_routes` | `git grep -n "class _RequestHostLoopProvider\|def _root_routes\|def _read_routes\|def _activity_routes\|def _sql_trace_routes\|def _logger_routes\|def _http_exchange_routes\|async def _http_probe\|def _http_probe_routes\|def _exception_routes\|def _exception_status_routes\|def _alembic_action_handler\|def _database_routes\|def _pool_routes\|def _thread_routes\|def _vulnerability_routes\|def _rest_api_routes\|def _dismissed_routes\|def _mcp_routes\|def _cli_routes\|def _panel_04_routes\|def build_routes" src/sharpit/fastapi/routes/__init__.py` |
| `src/sharpit/fastapi/signals.py:8-19` | `dev_server_signal` | `git grep -n "def dev_server_signal" src/sharpit/fastapi/signals.py` |
| `src/sharpit/fastapi/sse.py:24-76` | `TOO_MANY_STREAMS`, `Events`, `_frame`, `_frames`, `_SseResponse`, `sse_response` | `git grep -n "TOO_MANY_STREAMS =\|Events =\|def _frame(\|async def _frames(\|class _SseResponse\|def sse_response" src/sharpit/fastapi/sse.py` |
| `src/sharpit/flask/introspector.py:54-103` | `FlaskIntrospector`, `FlaskIntrospector.app_info`, `FlaskIntrospector.routes`, `FlaskIntrospector.providers` | `git grep -n "class FlaskIntrospector\|def app_info\|def routes\|def providers" src/sharpit/flask/introspector.py` |
| `src/sharpit/pytest_plugin/http_security_flask.py:21-74` | `route_of`, `observe_flask` | `git grep -n "def route_of\|def observe_flask" src/sharpit/pytest_plugin/http_security_flask.py` |
| `src/sharpit/settings.py:31-314` | `PanelSettings`, `SharpitSettings`, `load_settings` | `git grep -n "class PanelSettings\|class SharpitSettings\|def load_settings" src/sharpit/settings.py` |
| `tests/fastapi/test_concurrency.py:19-50` | `test_other_panels_are_not_serialised_behind_a_slow_config_scan` | `git grep -n "def test_other_panels_are_not_serialised_behind_a_slow_config_scan" tests/fastapi/test_concurrency.py` |
| `tests/fastapi/test_install.py:49-62, 415-438` | `test_inactive_404_every_path_and_method`, `test_duplicate_host_header_is_denied_as_disallowed_host`, `test_duplicate_origin_header_is_denied_as_cross_site`, `test_websocket_scope_is_closed`, `test_inactive_websocket_scope_is_closed` | `git grep -n "def test_inactive_404_every_path_and_method\|def test_duplicate_host_header_is_denied_as_disallowed_host\|def test_duplicate_origin_header_is_denied_as_cross_site\|def test_websocket_scope_is_closed\|def test_inactive_websocket_scope_is_closed" tests/fastapi/test_install.py` |
| `tests/fastapi/test_threads_api.py:47-90` | `test_task_request_path_masked`, `test_threads_get_shape_and_filters`, `test_get_threads_mcp_no_side_effects` | `git grep -n "def test_task_request_path_masked\|def test_threads_get_shape_and_filters\|def test_get_threads_mcp_no_side_effects" tests/fastapi/test_threads_api.py` |
| `tests/test_safety_matrix.py:647-690` | `DUPLICATES`, `test_duplicate_guard_headers_are_403`, `test_inactive_is_404_everywhere` | `git grep -n "DUPLICATES =\|def test_duplicate_guard_headers_are_403\|def test_inactive_is_404_everywhere" tests/test_safety_matrix.py` |
