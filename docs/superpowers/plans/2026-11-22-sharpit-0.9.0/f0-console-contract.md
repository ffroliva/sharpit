# F0: Framework-Free Console Contract (`src/sharpit/engine/console/`)

This document specifies the framework-free console contract between `src/sharpit/engine/console/` and the host framework adapters (`src/sharpit/fastapi/` for ASGI and `src/sharpit/flask/` for WSGI). It covers the Python type signatures, the five architectural decisions from Track F of `PLAN.md`, the WSGI joined-header rule, the Flask activation matrix and proposed `AGENTS.md` safety rule 1 wording, and the F2 route migration batches.

---

## 1. Python Contract Signatures

All types below live in `src/sharpit/engine/console/` (with host port protocols in `src/sharpit/engine/spi.py` and `src/sharpit/engine/capture/__init__.py`). In accordance with Architecture Rules 1 and 2 in `AGENTS.md`, no module in `src/sharpit/engine/console/` imports `fastapi`, `starlette`, `flask`, or `werkzeug`.

### 1.1 `ConsoleRequest`

```python
from collections.abc import Callable
from dataclasses import dataclass

RawHeaders = tuple[tuple[bytes, bytes], ...]


class BodyTooLargeError(Exception):
    """Raised by ConsoleRequest.read_body when the payload exceeds max_bytes."""

    max_bytes: int

    def __init__(self, max_bytes: int) -> None: ...


class ClientDisconnectedError(Exception):
    """Raised by ConsoleRequest.read_body when the client disconnects mid-body."""


BodyReader = Callable[[int], bytes]


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
    is_probe: bool = False
```

Field invariants:
- `method`: Upper-case HTTP verb (`"GET"`, `"HEAD"`, `"POST"`, `"DELETE"`, etc.).
- `path`: Normalized path relative to `settings.path` (`""` for the bare mount `/sharpit`, `"/"` for `/sharpit/`, `"/index.html"` for `/sharpit/index.html`, `"/api/overview"` for `/sharpit/api/overview` when `api_path="/sharpit/api"`). Requests outside `under(full_path, settings.path)` (`src/sharpit/engine/capture/__init__.py:112-114`) are never passed to `Console.handle`.
- `root_path`: Mount prefix above the application (`scope.get("app_root_path", scope.get("root_path", ""))` on ASGI; `environ.get("SCRIPT_NAME", "")` on WSGI), stripped of any trailing slash.
- `raw_query`: Unparsed query string bytes without a leading `?` (`scope.get("query_string", b"")` on ASGI; `environ.get("QUERY_STRING", "").encode("latin-1")` on WSGI).
- `raw_headers`: Tuple of `(lowercase_name_bytes, raw_value_bytes)` in wire order with every duplicate tuple preserved.
- `read_body`: `Callable[[int], bytes]` taking `max_bytes: int` (default `1_048_576` for JSON action bodies) that reads at most `max_bytes + 1` bytes and raises `BodyTooLargeError(max_bytes)` when the payload exceeds `max_bytes`.
- `scheme`: `"http"` or `"https"` (`scope.get("scheme", "http")` on ASGI; `environ.get("wsgi.url_scheme", "http")` on WSGI).
- `peer_addr`: Direct socket peer IP string (`scope["client"][0]` when `scope.get("client")` is present on ASGI; `environ.get("REMOTE_ADDR")` on WSGI), never derived from forwarding headers.
- `server`: `(host, port)` from the listening socket (`scope.get("server")` on ASGI; `(environ["SERVER_NAME"], int(environ["SERVER_PORT"]))` when present on WSGI).
- `is_probe`: `True` only when the request was synthesized in-process by `HostProbe` (`bool(scope.get("state", {}).get("sharpit_probe"))` on ASGI, `src/sharpit/fastapi/adapter.py:155`; `bool(environ.get("sharpit.probe"))` on WSGI).

### 1.2 `ConsoleStream` and `ConsoleResponse`

```python
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from sharpit.engine.capture.streams import SseEvent, StreamSlots

ResponseHeaders = tuple[tuple[str, str], ...]
EventSource = Callable[[], AsyncIterator[SseEvent]]
CloseHook = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ConsoleFile:
    path: Path
    media_type: str


@dataclass(slots=True)
class ConsoleStream:
    source: EventSource
    slots: StreamSlots
    max_seconds: float
    on_close: CloseHook
    _closed: bool = False

    def close(self) -> None: ...


def stream_frames(
    source: EventSource,
    *,
    max_seconds: float,
) -> AsyncIterator[bytes]: ...


@dataclass(frozen=True, slots=True)
class ConsoleResponse:
    status: int
    headers: ResponseHeaders
    body: bytes | None = None
    file: ConsoleFile | None = None
    stream: ConsoleStream | None = None
```

Invariants:
- Exactly one of `body`, `file`, or `stream` is non-`None` (for `204` or `304` or `307`, `body` is `b""`).
- `ConsoleStream.slots` holds a slot already acquired via `slots.acquire()` (`src/sharpit/engine/capture/streams.py:34-40`) before `Console.handle` returns the `ConsoleResponse`.
- `ConsoleStream.close()` is idempotent: the first call invokes `on_close()` and `slots.release()`; subsequent calls are no-ops.
- `stream_frames(source, max_seconds=...)` is the single engine SSE framer (replacing `src/sharpit/fastapi/sse.py:30-75`), setting `SSE_TASK` (`src/sharpit/engine/capture/streams.py:20`), encoding each `(event, event_id, data)` tuple via `format_sse` (`streams.py:173-181`), and emitting `b"retry: 1000\n\n"` when `max_seconds` elapses.

### 1.3 Route Table (`RouteSpec`) and Handler Call Object (`ConsoleCall`)

```python
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from sharpit.engine.context import EngineContext

RouteKind = Literal["read", "action"]
RouteHandler = Callable[["ConsoleCall"], ConsoleResponse]


@dataclass(frozen=True, slots=True)
class ConsoleCall:
    ctx: EngineContext
    request: ConsoleRequest
    headers: Mapping[str, str]
    path_params: Mapping[str, str]
    query_params: Mapping[str, str]
    query_multi: Mapping[str, tuple[str, ...]]
    set_cookie: str | None = None

    def json_body(self, *, max_bytes: int = 1_048_576) -> Any: ...


@dataclass(frozen=True, slots=True)
class RouteSpec:
    method: Literal["GET", "POST", "DELETE"]
    template: str
    handler: RouteHandler
    panel: str | None
    kind: RouteKind
    off_loop: bool = False


ROUTES: tuple[RouteSpec, ...]
```

Invariants:
- `template`: Path template relative to `settings.api_path` for API routes (e.g., `"/overview"`, `"/exceptions/stream"`, `"/exceptions/{id}"`, `"/data/repositories/{name:path}"`) or relative to `settings.path` for static UI routes (`"/"`, `"/index.html"`, `"/assets/{file}"`).
- `panel`: BootUI panel ID (`"overview"`, `"sql"`, `"exceptions"`, `"config"`, etc.) checked by `check_panel_access(ctx.settings, panel)` (`src/sharpit/engine/guard.py:313-336`), or `None` for panel-agnostic endpoints (`"/"`, `"/index.html"`, `"/assets/{file}"`, `"/panels"`, `"/dismissed-rules"`, `"/dismissed-findings"`, `"/mcp"`, `"/mcp-server"`, `"/cli"`).
- `kind`: `"read"` or `"action"`. When `kind == "action"` and `panel is not None`, `Console.handle` (or the panel's write-gate check for `"config"`, `"loggers"`, `"alembic"`, `"cache"`, `"code-paths"`) enforces `check_panel_writable(ctx.settings, panel)` (`src/sharpit/engine/guard.py:339-377`), refusing read-only panels with `403 PANEL_ACCESS_DENIED` and the panel's read-only reason (`guard.py:356-367`).
- `off_loop`: `False` for in-memory reads and SSE stream setup (which run directly on the ASGI event loop thread on FastAPI); `True` for disk-reading GET routes (`/assets/{file}`, `/config`, `/profile-diff`, `/alembic/migrations`, `/rest-api/error-contract`, `/copilot/*`, `/claude-code/*`) and synchronous blocking action routes (`/mcp`, `/cli/tools/{tool}`, sync scans, file-writing overrides).

### 1.4 `Console.handle` (Single Entry Point)

```python
from sharpit.engine.context import EngineContext


class Console:
    ctx: EngineContext

    def __init__(self, ctx: EngineContext) -> None: ...

    def match(
        self,
        method: str,
        path: str,
    ) -> tuple[RouteSpec | None, dict[str, str], tuple[str, ...]]: ...

    def handle(self, request: ConsoleRequest) -> ConsoleResponse: ...
```

`Console.handle(request)` executes the following pipeline in strict order:
1. **Activation (`src/sharpit/engine/activation.py:42-69`):** If `not self.ctx.activation.active`, return `ConsoleResponse(status=404, headers=(("content-type", "text/plain; charset=utf-8"),), body=b"Not Found")` with no security headers and no side effects.
2. **Duplicate security-critical header denial (`src/sharpit/engine/guard.py:218-226`):** Run `has_duplicate_security_headers(request.raw_headers)` (extended with the joined-header rule in §3). On match, return `400` JSON `error_body(PANEL_ACCESS_DENIED, DUPLICATE_HEADER_REASON, details={"panelId": None})` with `Cache-Control: no-store, must-revalidate` and `SECURITY_HEADERS`.
3. **Guard chain (`src/sharpit/engine/guard.py:239-310`):** Extract first-occurrence headers via `extract_headers(request.raw_headers)` (`src/sharpit/engine/headers.py:7-16`) and run `evaluate_guard(self.ctx.settings, method=request.method, path=full_mount_path, client_host=request.peer_addr, headers=headers, query_token=query_params.get("token"), is_entry=is_ui_entry(request), session_token=self.ctx.session_token, is_probe=request.is_probe)`. On rejection, return the guard's status (`401` or `403`), JSON `error_body`, `Cache-Control: no-store, must-revalidate`, and `SECURITY_HEADERS`.
4. **Bare mount redirect and route matching:**
   - If `request.path == ""` (bare `/sharpit`), return `307 Temporary Redirect` with `Location: {request.root_path}{self.ctx.settings.path}/` (appending `?{raw_query}` when `request.raw_query` is non-empty) and `SECURITY_HEADERS` for `GET`/`HEAD`, or `404 {"error": "Not Found"}` with `SECURITY_HEADERS` for other methods.
   - Match `(request.method, request.path)` against `ROUTES` (treating `HEAD` as matching `GET` routes and stripping the response body after dispatch). If the path matches templates for other methods only, return `405 {"error": "Method Not Allowed"}` with `Allow: <comma-joined sorted methods>` and `SECURITY_HEADERS`. If no template matches, return `404 {"error": "Not Found"}` with `SECURITY_HEADERS`.
5. **Panel access (`src/sharpit/engine/guard.py:313-377`):** If `route.panel is not None`, run `check_panel_access(self.ctx.settings, route.panel)` (`403 PANEL_ACCESS_DENIED` when disabled). If `route.kind == "action"` and `route.panel in WRITABLE_GATED_PANELS`, run `check_panel_writable(self.ctx.settings, route.panel)` (`403 PANEL_ACCESS_DENIED` with read-only reason when read-only).
6. **Dispatch & security headers:** Call `route.handler(call)`. Attach `Set-Cookie` from `decision.set_cookie` when present, `Cache-Control: no-store, must-revalidate` on API and UI entry responses, and `SECURITY_HEADERS` (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`, `src/sharpit/engine/guard.py:41-46`) on every response.

### 1.5 Host Ports (`HostProbe`, `CaptureHooks`, `HostLoopProvider`)

```python
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ProbeCaller:
    headers: tuple[tuple[bytes, bytes], ...]
    peer_addr: str | None
    server: tuple[str, int | None] | None


class HostProbe(Protocol):
    def execute(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str] | None = None,
        body: str | None = None,
        caller: ProbeCaller | None = None,
        follow_auth: bool = True,
    ) -> dict[str, Any]: ...


class CaptureHooks(Protocol):
    def attach_sql_engine(self, engine: object) -> bool: ...
    def detach_sql_engines(self) -> None: ...


class HostLoopProvider(Protocol):
    def current_loop(self) -> asyncio.AbstractEventLoop | None: ...
```

Port wiring on `EngineContext` (`src/sharpit/engine/context.py:31-79`):
- `CaptureHooks` already exists in `src/sharpit/engine/capture/__init__.py:21-25` and is passed to `EngineContext.__init__`.
- `HostLoopProvider` already exists from H3 in `src/sharpit/engine/spi.py:10-14` (`ctx.loop_provider`, `src/sharpit/engine/context.py:42,57`). On FastAPI, `FastApiLoopProvider.current_loop()` returns the active ASGI loop (`src/sharpit/fastapi/install.py:92-119`); on Flask, `FlaskLoopProvider.current_loop()` returns `None`.
- `HostProbe` wraps `src/sharpit/engine/probe.py:224-301`: on FastAPI, `AsgiHostProbe.execute(...)` schedules `run_probe(app, ...)` on `ctx.loop_provider.current_loop()` (or awaits it directly when already on the loop); on Flask, `ctx.host_probe` is `None` until F5 provides `WsgiHostProbe` over `app.wsgi_app`.
- `AppIntrospector` (`src/sharpit/engine/spi.py:99-105`) gains two read-only properties with defaults: `platform: str = "fastapi"` (`"flask"` on `FlaskIntrospector`) and `web_application_type: str = "ASGI"` (`"WSGI"` on `FlaskIntrospector`), eliminating the hardcoded literals in `src/sharpit/engine/panels.py:132` and `src/sharpit/engine/collectors/overview.py:33` and removing the `scope` parameter from `overview_dto(ctx, server=..., root_path=...)`.

---

## 2. Decisions for the Five Plan Questions

### Decision 1: Where Each Handler Runs on Each Adapter, and Whether a Console Read on FastAPI Takes a Host Threadpool Slot

**Decision:**
1. **A console read on FastAPI never takes a host threadpool slot** (`anyio.to_thread.current_default_thread_limiter()`).
2. **On FastAPI (ASGI):**
   - Steps 1–5 of `Console.handle` (activation, duplicate-header check, guard, bare-mount redirect, route match, panel access), all **in-memory read handlers** (`RouteSpec.off_loop == False`, covering 56 GET endpoints: `/`, `/index.html`, `/panels`, `/overview`, `/loggers`, `/mappings/flat`, `/beans`, `/activity*`, `/log-tail/recent`, `/sql-trace*`, `/http-exchanges*`, `/exceptions*`, `/health`, `/database-connection-pools/*`, `/threads`, `/vulnerabilities`, cached advisor report and rule-violation GETs, `/dismissed-rules`, `/dismissed-findings`, `/mcp-server`, `/cli`, `/live-memory/footprint`, `/data/*`, `/transactions`, `/postgresql`, `/mysql`, `/traces*`, `/security-logs`, `/sqlalchemy-statistics`, `/fastapi-security*`, `/pentesting`, `/metrics*`, `/startup`, `/scheduled`, `/github`, `/ai/*`, `/java-agent`, `/code-inventory*`, `/code-paths*`, `/side-effects*`, `/email*`, `/runtime-insights*`), and SSE stream setup (`/activity/stream`, `/log-tail/stream`, `/exceptions/stream`, `/sql-trace/stream`, `/http-exchanges/stream`, `/copilot/stream`, `/claude-code/stream`) run **synchronously on the ASGI event loop thread**.
   - **Disk-reading GET handlers** (`/assets/{file}`, `/config`, `/profile-diff`, `/alembic/migrations`, `/rest-api/error-contract`, `/copilot/projects`, `/copilot/sessions`, `/copilot/sessions/{id}`, `/claude-code/projects`, `/claude-code/sessions`, `/claude-code/sessions/{id}`) and **blocking synchronous action handlers** (`POST /mcp`, `POST /mcp-server/toggle`, `POST /cli/tools/{tool}`, `POST /vulnerabilities/scan`, `POST /github/refresh`, `POST /rest-api/scan`, `POST /architecture/scan`, `POST /security/scan`, `POST /fastapi/scan`, `POST /alembic/migrate`, `POST /alembic/clean`, `POST /config/overrides`, `DELETE /config/overrides/{name}`, `POST /dismissed-rules/{rule_id}`, `DELETE /dismissed-rules/{rule_id}`, `POST /dismissed-findings`, `DELETE /dismissed-findings`, `POST /cache/clear`, `POST /loggers/{name}`, `POST /code-paths/probes`, `POST /code-paths/probes/{id}/stop`, `DELETE /code-paths/probes/{id}`, `DELETE /email`, `DELETE /runtime-insights`) set `off_loop=True` on `RouteSpec`. On FastAPI, after the guard and panel-access checks pass on the event loop thread, the ASGI adapter reads the capped request body (if any) on the loop and dispatches `route.handler(call)` via `await loop.run_in_executor(ctx.console_executor, route.handler, call)`, where `ctx.console_executor` is a sharpit-owned `DaemonExecutor(4)` (`src/sharpit/engine/daemon_executor.py:13-35`).
   - **Loop-bound async collectors** (`POST /alembic/refresh`, `POST /health/check`, `POST /mysql/read`, `POST /postgresql/read`, `POST /database-advisor/scan`, `POST /http-probe`, `POST /pentesting/scan`) run via `HostLoopProvider` / `HostProbe` and each collector's existing `DaemonExecutor(2)`.
3. **On Flask (WSGI):** Every route handler (`off_loop=False` and `off_loop=True` alike) runs synchronously on the calling WSGI worker thread inside `Console.handle(request)`. When an action handler invokes an async database collector (`refresh_alembic`, `health_service.check`, `refresh_mysql`, `refresh_postgresql`, `database_advisor.run_scan`) and `ctx.loop_provider.current_loop()` is `None`, the engine runs the coroutine via `asyncio.run(...)` on the calling WSGI worker thread.

**Reason:**
- `tests/fastapi/test_threads_api.py:72-90` (`test_threads_endpoint_spawns_no_extra_threads`) asserts `threading.active_count() <= before + 1` across `GET /sharpit/api/threads` and requires `asyncio.get_running_loop()` (`src/sharpit/engine/collectors/threads.py:168-172`) to inspect live asyncio tasks on the host event loop. Running in-memory reads on a worker thread would both spawn a thread and miss the host event loop.
- `tests/fastapi/test_concurrency.py:19-46` (`test_slow_config_does_not_block_overview`) patches `collect_config` with a 0.4 s `time.sleep` and asserts that three concurrent `GET /sharpit/api/overview` calls finish in under 0.35 s. Marking `/config` (and other filesystem-reading GETs) `off_loop=True` keeps the event loop unblocked during first-time project file scans.
- Using `ctx.console_executor` (`DaemonExecutor(4)`) instead of `starlette.concurrency.run_in_threadpool` guarantees that sharpit never competes for tokens in the host application's `anyio.to_thread.current_default_thread_limiter()`, so the developer console remains responsive even when the host app's sync route threadpool is completely deadlocked or saturated.

**Proving Test:**
- `tests/fastapi/test_concurrency.py::test_in_memory_console_reads_complete_when_host_anyio_threadpool_is_exhausted` — acquires all tokens from `anyio.to_thread.current_default_thread_limiter()`, issues concurrent `GET /sharpit/api/overview`, `GET /sharpit/api/threads`, and `GET /sharpit/api/config` requests, and asserts all return `200` within 0.35 s while `threading.active_count()` does not grow on `/threads`.

---

### Decision 2: The Stream Form (One Async Source Run on a Private Loop on WSGI vs. a Thread-Safe Blocking Form)

**Decision:**
Keep **one async event source** (`EventSource = Callable[[], AsyncIterator[SseEvent]]`) and one engine SSE framer (`stream_frames(source, max_seconds=...)` in `src/sharpit/engine/console/sse.py`) shared by both adapters:
- `ChangeStream.subscribe()` (`src/sharpit/engine/capture/streams.py:194-203`) and `LineStream.subscribe()` (`streams.py:213-219`) remain unchanged async generators backed by `_Ticker` (`streams.py:48-97`), which already stores `(asyncio.AbstractEventLoop, asyncio.Event)` per waiter and wakes subscribers from any OS thread via `self._loop.call_soon_threadsafe(self._wake)` (`streams.py:66`).
- **On FastAPI (ASGI):** The ASGI adapter sends `http.response.start` and iterates `async for chunk in stream_frames(stream.source, max_seconds=stream.max_seconds):` directly on the request's event loop, calling `stream.close()` in a `finally:` block.
- **On Flask (WSGI):** The WSGI adapter wraps `ConsoleStream` in a PEP 3333 response iterator class `WsgiEventStream` that creates a private `loop = asyncio.new_event_loop()` on the serving WSGI worker thread (spawning **zero** extra threads) and advances `loop.run_until_complete(anext(agen))` on each `__next__()` call until `StopAsyncIteration` (when `stream_max_seconds` expires and yields `b"retry: 1000\n\n"`). `WsgiEventStream.close()` runs `loop.run_until_complete(agen.aclose())`, closes `loop`, and calls `stream.close()`.

**Reason:**
- Maintaining a second `threading.Condition`-based blocking stream implementation alongside `_Ticker` would duplicate the watermark coalescing, ring-buffer overflow signaling (`overflow: True`), and 250 ms heartbeat ticker (`TICK_SECONDS = 0.25`, `src/sharpit/engine/capture/streams.py:21`) across three stream producers (`ChangeStream`, `LineStream`, and `agent_sessions_events` in `src/sharpit/fastapi/routes/agent_sessions.py:55-99`).
- `_Ticker._Waiter` (`src/sharpit/engine/capture/streams.py:49-68`) is already multi-loop and cross-thread safe: it captures the loop that called `await ticker.wait(after)` and uses `loop.call_soon_threadsafe(self._wake)` whenever `bump()` or `publish()` runs on any other WSGI worker thread or background daemon thread.
- Running a private `asyncio.new_event_loop()` synchronously on the serving WSGI worker thread during `__next__()` adds zero threads, avoids cross-thread queue handoffs, and bounds every `run_until_complete` call to at most `TICK_SECONDS` (0.25 s) or the remaining `stream_max_seconds` window.

**Proving Test:**
- `tests/engine/test_console_streams.py::test_wsgi_private_loop_stream_yields_initial_and_live_change_events_and_retry_frame` — drives `WsgiEventStream` on a synchronous worker thread while a second thread calls `ctx.capture.exceptions_stream.bump()`, asserting the iterator yields the initial `event: change` frame, the bumped `event: change` frame within 50 ms, and the closing `b"retry: 1000\n\n"` frame at `max_seconds`, with `threading.active_count()` unchanged.

---

### Decision 3: The WSGI Capacity Rule (Stream Slots Against Worker Count, Overload Response, Cleanup on Disconnect)

**Decision:**
1. **Slot limit calculation (`wsgi_stream_limit`):**
   - FastAPI keeps `MAX_STREAMS = 20` (`src/sharpit/engine/capture/streams.py:23`).
   - Flask configures `ctx.capture.stream_slots = StreamSlots(limit=wsgi_stream_limit(sys.argv, os.environ))`, where `WSGI_DEFAULT_MAX_STREAMS = 4`:
     - If an explicit thread count `W` is present in `sys.argv` or `os.environ.get("GUNICORN_CMD_ARGS", "")` (`--threads N`, `--threads=N`, `-t N` on `gunicorn`, or `W = 1` when `--without-threads` is passed to `flask run`), `limit = max(1, min(WSGI_DEFAULT_MAX_STREAMS, W - 1))`.
     - If `gunicorn` is detected without `--threads` and without an async/threaded worker class (`-k gthread` / `--worker-class gthread`), `W = 1`, so `limit = 1` and a startup warning is recorded on `ctx.activation.warnings`: `"WSGI server is running with a single synchronous worker thread; sharpit limits concurrent SSE streams to 1. Pass --threads 4 or higher for full live-stream concurrency."`
     - Otherwise (`flask run` default `ThreadedWSGIServer`, which spawns a thread per request, or `Flask.test_client()`), `limit = WSGI_DEFAULT_MAX_STREAMS = 4`.
     - Note: `environ.get("wsgi.multithread")` is **not** used to disable streaming because Werkzeug's `EnvironBuilder` sets `wsgi.multithread = False` in `Flask.test_client()`.
2. **Overload response:**
   - Before constructing a `ConsoleStream`, the stream route handler calls `ctx.capture.stream_slots.acquire()`.
   - When `acquire()` returns `False`, the handler immediately returns `ConsoleResponse(status=503, headers=(("content-type", "application/json"), ("cache-control", "no-store, must-revalidate")), body=b'{"error":"Too many concurrent sharpit streams"}')` (matching `src/sharpit/fastapi/sse.py:26-29` and BootUI's 503 stream rejection).
3. **Cleanup on disconnect and normal exit:**
   - Each WSGI stream response runs up to `ctx.settings.stream_max_seconds` (default `3.0` s, `src/sharpit/settings.py:104`), after which `stream_frames` yields `b"retry: 1000\n\n"` and terminates normally so the WSGI worker thread is freed every 3 seconds even if no client disconnects.
   - PEP 3333 requires every WSGI server (Werkzeug, Gunicorn, uWSGI, Waitress) and `werkzeug.test.Client` to call `iterable.close()` when the HTTP response finishes or the socket disconnects. `WsgiEventStream` calls `self.close()` both when `__next__()` reaches `StopAsyncIteration` and when the WSGI server calls `WsgiEventStream.close()`.
   - `WsgiEventStream.close()` is idempotent: it runs `loop.run_until_complete(agen.aclose())` (which executes the `finally:` block in `_Ticker.wait`, `src/sharpit/engine/capture/streams.py:96`, removing the `_Waiter` from `self._subs` and resetting `SSE_TASK`), calls `loop.close()` (so `_Ticker._signal()`'s `self._loop.is_closed()` check at `streams.py:61` also prunes on any concurrent race), and calls `ConsoleStream.close()`, which calls `slots.release()` (`streams.py:42-45`) exactly once.

**Reason:**
- On WSGI, every active SSE response occupies a worker thread for the duration of the stream window (`3.0` s). Capping Flask stream slots at `max(1, min(4, W - 1))` guarantees that on any multi-threaded WSGI server (`W >= 2`), at least one worker thread always remains free to serve `GET /sharpit/api/*` REST reads while streams are open.
- Keeping at least `1` stream slot on single-threaded servers (and under `Flask.test_client()`) preserves full contract parity for every `/stream` endpoint while the 3-second `stream_max_seconds` window plus `retry: 1000` bounds how long that single thread can be held.

**Proving Test:**
- `tests/engine/test_console_streams.py::test_wsgi_stream_limit_and_disconnect_cleanup` — verifies `wsgi_stream_limit` across `flask run`, `flask run --without-threads`, `gunicorn --reload`, and `gunicorn --reload --threads 3`; opens `limit` concurrent `WsgiEventStream` instances, asserts the `(limit + 1)`th stream returns `503 {"error": "Too many concurrent sharpit streams"}`, aborts one stream early via `.close()`, and asserts `_Ticker._subs` is empty and the next stream request succeeds with `200`.

---

### Decision 4: Route Order, Including the `SharpitMount` Bare-Path Match

**Decision:**
1. **Mount prefix ownership (`under(path, settings.path)`):**
   - Both `SharpitMount` on FastAPI (`src/sharpit/fastapi/adapter.py:84-138`, inserted at `app.router.routes.insert(0, mount)` in `src/sharpit/fastapi/install.py:274`) and `SharpitWsgiMiddleware` on Flask intercept a request if and only if `under(path, settings.path)` (`path == settings.path or path.startswith(settings.path + "/")`, `src/sharpit/engine/capture/__init__.py:112-114`) is `True`.
   - Any sibling path such as `/sharpit-other` has `under("/sharpit-other", "/sharpit") == False` and passes straight through to the host application without invoking `Console.handle`.
2. **Bare-path match (`request.path == ""` for `/sharpit`):**
   - Unlike Starlette's `Mount`, which only matches `/sharpit` after redirect or sub-dispatch, `Console.handle` owns `request.path == ""` directly.
   - A request to bare `/sharpit` runs step 1 (activation: `404` when inactive), step 2 (duplicate security-critical headers: `400`), and step 3 (`evaluate_guard`: `401` / `403` when untrusted or unauthenticated) **before** step 4 emits `307 Temporary Redirect` to `{request.root_path}{settings.path}/` (with `?{raw_query}` preserved) for `GET`/`HEAD` or `404 {"error": "Not Found"}` for any other verb.
3. **Deterministic route table order in `ROUTES`:**
   - Every route template in `ROUTES` is pre-compiled into segment matchers: literal segment (`"stream"`), single-segment parameter (`"{id}"`), or greedy tail parameter (`"{name:path}"`).
   - Within `ROUTES`, literal routes and longer multi-segment routes precede parameterized siblings under the same prefix. Specifically:
     1. UI routes under `settings.path`: `GET /`, `GET /index.html`, `GET /assets/{file}`.
     2. Core & control routes under `settings.api_path`: `GET /panels`, `GET /overview`, `GET /dismissed-rules`, `POST /dismissed-rules/{rule_id}`, `DELETE /dismissed-rules/{rule_id}`, `GET /dismissed-findings`, `POST /dismissed-findings`, `DELETE /dismissed-findings`, `GET /mcp-server`, `POST /mcp-server/toggle`, `POST /mcp`, `GET /cli`, `POST /cli/tools/{tool}`.
     3. Literal sub-paths before `{id}` / `{name:path}` catch-alls:
        - `GET /activity/stream`, `GET /activity/journal`, `GET /activity/resources`, `GET /activity/request/{id}`, `GET /activity`
        - `GET /log-tail/recent`, `GET /log-tail/stream`
        - `GET /sql-trace/stream`, `GET /sql-trace/{id}`, `GET /sql-trace`
        - `GET /http-exchanges/stream`, `GET /http-exchanges/{id}`, `GET /http-exchanges`
        - `GET /exceptions/stream`, `GET /exceptions/caught`, `GET /exceptions/{id}`, `GET /exceptions`
        - `GET /data/repositories`, `GET /data/repositories/{name:path}`, `GET /data/entities`, `GET /data/entities/{name:path}`, `GET /data/flyway`, `GET /data/caches`, `GET /data/summary`
        - `GET /traces/{trace_id}`, `GET /traces`
        - `GET /code-paths/probes`, `POST /code-paths/probes`, `POST /code-paths/probes/{id}/stop`, `DELETE /code-paths/probes/{id}`, `GET /code-paths/executions/{id}`, `GET /code-paths`
        - `GET /email/{id}/eml`, `GET /email/{id}`, `GET /email`, `DELETE /email`
        - `GET /runtime-insights/history`, `GET /runtime-insights/{id}`, `GET /runtime-insights`, `DELETE /runtime-insights`
        - `GET /copilot/stream`, `GET /copilot/projects`, `GET /copilot/sessions`, `GET /copilot/sessions/{id}`, `GET /claude-code/stream`, `GET /claude-code/projects`, `GET /claude-code/sessions`, `GET /claude-code/sessions/{id}`
        - `GET /loggers`, `POST /loggers/{name:path}`
        - `GET /config`, `POST /config/overrides`, `DELETE /config/overrides/{name:path}`, `GET /profile-diff`
   - Ordering `ROUTES` explicitly in one tuple retires both `_with_drift_routes` and the `dismissed_findings` route-splicing helper in `src/sharpit/fastapi/adapter.py:245-284`.

**Reason:**
- In BootUI's `RequestMappingHandlerMapping`, literal path mappings always beat `{id}` template variables regardless of registration order, whereas Starlette scans `Router.routes` linearly (`src/sharpit/fastapi/adapter.py:245-284` had to splice `/exceptions/caught` ahead of `/exceptions/{id}`). Encoding literal-first precedence in `ROUTES` guarantees identical matching on FastAPI and Flask without runtime route-list surgery.
- Running the guard on bare `/sharpit` before the `307` redirect preserves `SharpitMount.__call__` (`src/sharpit/fastapi/adapter.py:100-125`) and ensures an untrusted request never receives a redirect or reveals the mount structure.

**Proving Test:**
- `tests/engine/test_console_contract.py::test_route_table_precedence_and_bare_mount_guard` — tests bare `/sharpit` with untrusted `Host` (`403`), trusted `GET /sharpit?x=1` under `root_path="/app"` (`307` to `/app/sharpit/?x=1`), `POST /sharpit` (`404`), `/sharpit-other` (not matched by mount), and every literal-vs-parameter sibling (`/exceptions/stream`, `/exceptions/caught`, `/exceptions/exc-1`, `/code-paths/probes/p1/stop`, `/email/m1/eml`, `/data/repositories/pkg/Repo`).

---

### Decision 5: The Request ID Header (`X-Sharpit-Request-Id`)

**Decision:**
1. **Console responses (`Console.handle`) never emit `X-Sharpit-Request-Id`.** Even on FastAPI today, `CaptureMiddleware` bypasses all paths under `settings.path` (`if under(path, self._ctx.settings.path): await self.app(scope, receive, send); return` at `src/sharpit/fastapi/capture.py:423-425`), so responses from `/sharpit/*` never carry `X-Sharpit-Request-Id`.
2. **Host application responses on FastAPI (ASGI):** `CaptureMiddleware` (`src/sharpit/fastapi/capture.py:506-509, 606-611`) and `should_append_request_id_header` (`src/sharpit/fastapi/request_id_header.py:18-51`) continue to append `x-sharpit-request-id: <exchange_id>` to host responses when all five conditions hold:
   - `ctx.capture.exchanges is not None` (an HTTP exchange was recorded in `HttpExchangeBuffer`),
   - `is_panel_enabled(ctx.settings, "http-exchanges")` is `True`,
   - `ctx.settings.http_exchanges_expose_request_id_header` is `True`,
   - the host response does not already include an `x-sharpit-request-id` header, and
   - `is_trusted_source(client_host=..., headers=..., trusted_subnets=...)` is `True`.
3. **Host application responses on Flask (WSGI) in 0.9.0:** `X-Sharpit-Request-Id` is **not emitted on Flask in 0.9.0** (recorded as unavailable in F0b).

**Reason:**
- The value of `X-Sharpit-Request-Id` is the captured `HttpExchangeBuffer` exchange ID (`exchange_id` generated at `src/sharpit/fastapi/capture.py:466`), which clients and tests use to look up `GET /sharpit/api/http-exchanges/{id}` and `GET /sharpit/api/activity/request/{id}`.
- Track F Decision 7 (`PLAN.md` lines 88–90) scopes Flask request correlation in F4 to generating a per-request correlation ID for SQL statements (`sql-trace`) and unhandled exceptions (`exceptions`), while HTTP exchange capture (`HttpExchangeBuffer`) remains ASGI-only in 0.9.0. Emitting an `X-Sharpit-Request-Id` header on Flask host responses whose ID does not resolve in `GET /sharpit/api/http-exchanges/{id}` would violate the BootUI contract for that header.

**Proving Test:**
- `tests/engine/test_console_contract.py::test_console_responses_never_emit_request_id_header` — asserts that `Console.handle` responses for `/sharpit/api/overview` and `/sharpit/` never contain `x-sharpit-request-id` even when `http_exchanges_expose_request_id_header=True`.

---

## 3. The Joined-Header Rule

### 3.1 Why WSGI Joins Duplicate Headers

In ASGI, `scope["headers"]` is an iterable of raw `(name_bytes, value_bytes)` pairs directly from the HTTP parser, so two incoming `Host` headers arrive as two distinct `(b"host", ...)` tuples. In PEP 3333 WSGI (and RFC 7230 §3.2.2), HTTP servers such as Werkzeug, Gunicorn, and Waitress fold duplicate incoming headers with the same field name into a single `environ["HTTP_<NAME>"]` (or `HTTP_HOST`) entry whose value is joined with `", "` (for example, `"localhost:5000, evil.example"`).

### 3.2 Rule in `src/sharpit/engine/guard.py`

None of the three security-critical single-value headers in `SECURITY_CRITICAL_SINGLE_HEADERS` (`src/sharpit/engine/guard.py:48-52`: `b"host"`, `b"origin"`, `b"sec-fetch-site"`) can legitimately contain a comma `,` (`0x2c`) in a valid single header value (RFC 3986 §3.2.2 forbids `,` in a valid hostname or IP literal in `Host` and `Origin`, and `Sec-Fetch-Site` is one token from `{"same-origin", "same-site", "cross-site", "none"}`).

Therefore, `has_duplicate_security_headers(raw_headers)` in `src/sharpit/engine/guard.py:218-226` enforces both checks on every `(raw_name, raw_value)` pair in `request.raw_headers`:
1. **Multi-tuple duplicate check:** A lowercase header name in `SECURITY_CRITICAL_SINGLE_HEADERS` appears in more than one tuple of `request.raw_headers`.
2. **Comma-joined duplicate check:** Any tuple whose lowercase header name is in `SECURITY_CRITICAL_SINGLE_HEADERS` contains `b","` in `raw_value`.

Either condition causes `has_duplicate_security_headers` to return `True`, and step 2 of `Console.handle` immediately refuses the request with `400 Bad Request` and `DUPLICATE_HEADER_REASON` (`"Duplicate security-critical HTTP headers are not allowed"`).

### 3.3 How Each Adapter Builds `request.raw_headers`

- **FastAPI (ASGI adapter):**
  Passes `tuple((bytes(k).lower(), bytes(v)) for k, v in scope.get("headers") or ())` into `ConsoleRequest.raw_headers` without deduplicating or splitting on commas.
- **Flask (WSGI adapter):**
  Constructs `ConsoleRequest.raw_headers` from the PEP 3333 `environ` dict without splitting on commas:
  1. If `environ.get("CONTENT_TYPE")` is present, append `(b"content-type", environ["CONTENT_TYPE"].encode("latin-1"))`.
  2. If `environ.get("CONTENT_LENGTH")` is present and non-empty, append `(b"content-length", environ["CONTENT_LENGTH"].encode("latin-1"))`.
  3. For every `(key, value)` in `environ.items()` where `key.startswith("HTTP_")` and `isinstance(value, str)`: convert `key[5:].replace("_", "-").lower().encode("latin-1")` and `value.encode("latin-1")` into a `(name_bytes, value_bytes)` pair.
  4. When testing with Werkzeug directly (`environ.get("werkzeug.request")` or `Headers` list passed to a test helper with unjoined duplicate tuples), if raw unjoined header pairs are explicitly supplied to the WSGI test harness, preserve them verbatim; otherwise use the standard PEP 3333 `environ` extraction above.

---

## 4. Activation on Flask

### 4.1 Current Signal Behavior

Today `src/sharpit/fastapi/signals.py:1-19` inspects `sys.argv` and `os.environ`:
- If `"--reload"` is in `sys.argv`, it returns `"uvicorn --reload"` (line 13) regardless of which CLI was invoked.
- If `"fastapi"` is in `os.path.basename(sys.argv[0]).lower()` and `"dev"` is in `sys.argv[1:]`, it returns `"fastapi dev"` (line 16).
- If `os.environ.get("UVICORN_RELOAD", "").lower() in {"1", "true", "yes"}`, it returns `"UVICORN_RELOAD"` (line 18).

### 4.2 New Unified `dev_server_signal()` in `src/sharpit/engine/activation.py`

`dev_server_signal(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> str | None` moves to `src/sharpit/engine/activation.py` (with `src/sharpit/fastapi/signals.py` re-exporting it for backward compatibility) and recognizes the actual server launcher:

1. **Flask CLI (`flask run` / `python -m flask run`):**
   - Detected when `"flask"` is in `{os.path.basename(a).lower().removesuffix(".exe") for a in argv}` and `"run"` is in `argv[1:]`, or when `environ.get("WERKZEUG_RUN_MAIN", "").lower() == "true"`:
     - If `"--reload"` is in `argv` and `"--no-reload"` is not in `argv`: returns `"flask run --reload"`.
     - If `"--debug"` is in `argv` and `"--no-reload"` is not in `argv`: returns `"flask run --debug"`.
     - If `environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}` and `"--no-reload"` is not in `argv`: returns `"flask run --debug"`.
     - If `environ.get("WERKZEUG_RUN_MAIN", "").lower() == "true"` and `"--no-reload"` is not in `argv`: returns `"flask run --reload"`.
     - Otherwise (bare `flask run`, or `flask run --debug --no-reload`): returns `None`.
2. **Gunicorn (`gunicorn --reload`):**
   - Detected when `"gunicorn"` is in `{os.path.basename(a).lower().removesuffix(".exe") for a in argv}` or `shlex.split(environ.get("GUNICORN_CMD_ARGS", ""))`:
     - If `"--reload"` is in `argv` or in `shlex.split(environ.get("GUNICORN_CMD_ARGS", ""))`: returns `"gunicorn --reload"`.
     - Otherwise: returns `None`.
3. **FastAPI / Uvicorn (`uvicorn --reload`, `fastapi dev`, `UVICORN_RELOAD`):**
   - If `"fastapi"` is in `os.path.basename(argv[0]).lower()` and `"dev"` is in `argv[1:]`: returns `"fastapi dev"`.
   - If `"--reload"` is in `argv`: returns `"uvicorn --reload"`.
   - If `environ.get("UVICORN_RELOAD", "").lower() in {"1", "true", "yes"}`: returns `"UVICORN_RELOAD"`.

### 4.3 Activation Matrix for Flask and Gunicorn

| Command / Environment | `SHARPIT_ENABLED` | Profiles (`SHARPIT_PROFILES`) | `dev_server_signal()` | `active` | Reason (`ActivationResult.reason`) |
|---|---|---|---|---|---|
| `flask run` | unset (`AUTO`) | none | `None` | `False` | `"no activation signal present; failing closed"` |
| `flask run --debug` | unset (`AUTO`) | none | `"flask run --debug"` | `True` | `"dev-server signal detected (flask run --debug)"` |
| `flask run --reload` | unset (`AUTO`) | none | `"flask run --reload"` | `True` | `"dev-server signal detected (flask run --reload)"` |
| `flask run --debug --no-reload` | unset (`AUTO`) | none | `None` | `False` | `"no activation signal present; failing closed"` |
| `FLASK_DEBUG=1 flask run` | unset (`AUTO`) | none | `"flask run --debug"` | `True` | `"dev-server signal detected (flask run --debug)"` |
| `WERKZEUG_RUN_MAIN=true` (reloader child) | unset (`AUTO`) | none | `"flask run --reload"` | `True` | `"dev-server signal detected (flask run --reload)"` |
| `gunicorn app:app` | unset (`AUTO`) | none | `None` | `False` | `"no activation signal present; failing closed"` |
| `gunicorn --reload app:app` | unset (`AUTO`) | none | `"gunicorn --reload"` | `True` | `"dev-server signal detected (gunicorn --reload)"` |
| `GUNICORN_CMD_ARGS="--reload" gunicorn app:app` | unset (`AUTO`) | none | `"gunicorn --reload"` | `True` | `"dev-server signal detected (gunicorn --reload)"` |
| Any of the above | `OFF` | any | any | `False` | `"SHARPIT_ENABLED=OFF"` |
| Any of the above | `ON` | `prod` (disabled profile) | any | `True` (with warning) | `"SHARPIT_ENABLED=ON (overriding disabled profile)"` |
| `flask run` | unset (`AUTO`) | `dev` (`local`, `development`) | `None` | `True` | `"enabled profile active ('dev')"` |

### 4.4 Proposed Wording Change to Safety Rule 1 in `AGENTS.md`

*(Proposal for council and maintainer review only; `AGENTS.md` is not modified by F0.)*

Current wording in `AGENTS.md` (Safety model, rule 1):
> 1. **Fails closed.** Activation order: a disabled profile disables (unless `SHARPIT_ENABLED=ON`, with a warning) →
>    `OFF` disables → `ON` enables → an enabled profile enables → a reloading dev server (`uvicorn --reload`,
>    `fastapi dev`) enables → otherwise disabled. Inactive means every path under the mount answers 404.

Proposed wording:
> 1. **Fails closed.** Activation order: a disabled profile disables (unless `SHARPIT_ENABLED=ON`, with a warning) →
>    `OFF` disables → `ON` enables → an enabled profile enables → a reloading dev server (`uvicorn --reload`,
>    `fastapi dev`, `flask run --reload`, `flask run --debug`, `gunicorn --reload`) enables → otherwise disabled (bare
>    `flask run` and `gunicorn` without `--reload` stay disabled). Inactive means every path under the mount answers 404.

---

## 5. Order of F2's Panel Batches and Route Modules Moved

F2 migrates every route from `src/sharpit/fastapi/routes/__init__.py` and its 38 sibling modules under `src/sharpit/fastapi/routes/` into framework-free handlers under `src/sharpit/engine/console/routes/` registered in `ROUTES`. Each batch leaves `src/sharpit/fastapi/` green against the existing FastAPI test suite before the next batch begins.

| Batch | Focus | Source Modules Moved from `src/sharpit/fastapi/routes/` | Engine Target under `src/sharpit/engine/console/` | Routes Covered |
|---|---|---|---|---|
| **Batch 1** | UI static entry, panel discovery, overview, config, mappings, loggers, beans | `routes/__init__.py` (`index`, `index_html`, `asset`, `panels`, `overview`, `config`, `mappings_flat`, `loggers`, `set_logger`, `beans`), `config_overrides.py`, `profile_diff.py` | `routes/ui.py`, `routes/core.py`, `routes/config.py` | `GET /`, `GET /index.html`, `GET /assets/{file}`, `GET /panels`, `GET /overview`, `GET /config`, `POST /config/overrides`, `DELETE /config/overrides/{name:path}`, `GET /profile-diff`, `GET /mappings/flat`, `GET /loggers`, `POST /loggers/{name:path}`, `GET /beans` |
| **Batch 2** | Live buffers, streams, log tail, SQL trace, HTTP exchanges, exceptions, activity | `routes/__init__.py` (`activity*`, `log_tail*`, `sql_trace*`, `http_exchanges*`, `exceptions*`), `exceptions_caught.py`, `src/sharpit/fastapi/sse.py` | `sse.py`, `routes/capture.py` | `GET /activity`, `GET /activity/resources`, `GET /activity/journal`, `GET /activity/request/{id}`, `GET /activity/stream`, `GET /log-tail/recent`, `GET /log-tail/stream`, `GET /sql-trace`, `GET /sql-trace/stream`, `GET /sql-trace/{id}`, `GET /http-exchanges`, `GET /http-exchanges/stream`, `GET /http-exchanges/{id}`, `GET /exceptions`, `GET /exceptions/caught`, `GET /exceptions/stream`, `GET /exceptions/{id}` |
| **Batch 3** | Database, SQLAlchemy, Alembic, pools, health, transactions, cache | `routes/__init__.py` (`alembic_migrations`, `alembic_refresh`, `health*`, `pools*`), `alembic_actions.py`, `data.py`, `transactions.py`, `db_dialects.py`, `database_advisor.py`, `sqlastats.py`, `cache.py` | `routes/database.py` | `GET /alembic/migrations`, `POST /alembic/refresh`, `POST /alembic/migrate`, `POST /alembic/clean`, `GET /health`, `POST /health/check`, `GET /database-connection-pools/active`, `GET /database-connection-pools/history`, `GET /data/summary`, `GET /data/repositories`, `GET /data/repositories/{name:path}`, `GET /data/entities`, `GET /data/entities/{name:path}`, `GET /data/flyway`, `GET /data/caches`, `GET /transactions`, `GET /postgresql`, `POST /postgresql/read`, `GET /mysql`, `POST /mysql/read`, `GET /database-advisor`, `POST /database-advisor/scan`, `GET /database-advisor/rules/{rule_id}/violations`, `GET /sqlalchemy-statistics`, `POST /cache/clear` |
| **Batch 4** | Advisors, rule/finding dismissals, vulnerabilities, REST API, HTTP probe, pentesting, app security, security logs | `routes/__init__.py` (`vulnerabilities*`, `rest_api*`, `http_probe`, `architecture*`, `security*`, `fastapi*`, `dismissed_rules*`), `dismissed_findings.py`, `error_contract.py`, `appsecurity.py`, `securitylogs.py`, `pentesting.py` | `routes/advisors.py`, `routes/security.py` | `GET /vulnerabilities`, `POST /vulnerabilities/scan`, `GET /rest-api`, `POST /rest-api/scan`, `GET /rest-api/rules/{rule_id}/violations`, `GET /rest-api/error-contract`, `POST /http-probe`, `GET /architecture`, `POST /architecture/scan`, `GET /architecture/rules/{rule_id}/violations`, `GET /security`, `POST /security/scan`, `GET /security/rules/{rule_id}/violations`, `GET /fastapi`, `POST /fastapi/scan`, `GET /fastapi/rules/{rule_id}/violations`, `GET /dismissed-rules`, `POST /dismissed-rules/{rule_id}`, `DELETE /dismissed-rules/{rule_id}`, `GET /dismissed-findings`, `POST /dismissed-findings`, `DELETE /dismissed-findings`, `GET /fastapi-security`, `GET /fastapi-security/routes`, `GET /security-logs`, `GET /pentesting`, `POST /pentesting/scan` |
| **Batch 5** | Runtime observability, metrics, traces, threads, startup, scheduled tasks, mail, code sensors, runtime insights, live memory | `routes/__init__.py` (`threads`), `metrics.py`, `traces.py`, `startup.py`, `scheduled.py`, `mail.py`, `javaagent.py`, `code_inventory.py`, `code_paths.py`, `side_effects.py`, `insights.py`, `live_memory.py` | `routes/observability.py`, `routes/sensors.py` | `GET /threads`, `GET /metrics`, `GET /metrics/detail`, `GET /traces`, `GET /traces/{trace_id}`, `GET /startup`, `GET /scheduled`, `GET /email`, `GET /email/{id}`, `GET /email/{id}/eml`, `DELETE /email`, `GET /java-agent`, `GET /code-inventory`, `GET /code-inventory/classes`, `GET /code-paths`, `GET /code-paths/probes`, `POST /code-paths/probes`, `POST /code-paths/probes/{id}/stop`, `DELETE /code-paths/probes/{id}`, `GET /code-paths/executions/{id}`, `GET /side-effects`, `GET /side-effects/files`, `GET /side-effects/sockets`, `GET /side-effects/subprocesses`, `GET /runtime-insights`, `DELETE /runtime-insights`, `GET /runtime-insights/history`, `GET /runtime-insights/{id}`, `GET /live-memory/footprint` |
| **Batch 6** | External integrations, AI, agent sessions, MCP server, and CLI gateway | `github.py`, `ai.py`, `agent_sessions.py`, `mcp.py`, `mcp_server.py`, `cli.py` | `routes/integrations.py`, `routes/tooling.py` | `GET /github`, `POST /github/refresh`, `GET /ai/summary`, `GET /ai/calls`, `GET /copilot/projects`, `GET /copilot/sessions`, `GET /copilot/sessions/{id}`, `GET /copilot/stream`, `GET /claude-code/projects`, `GET /claude-code/sessions`, `GET /claude-code/sessions/{id}`, `GET /claude-code/stream`, `GET /mcp-server`, `POST /mcp-server/toggle`, `POST /mcp`, `GET /cli`, `POST /cli/tools/{tool}` |
