# How sharpit works

sharpit is a developer console that runs inside your FastAPI app while you develop it. You add one line:

```python
import sharpit

sharpit.install(app)
```

Then open `http://127.0.0.1:8000/sharpit` and you see what your app is really running with: its configuration, its
routes, its loggers, its dependency graph and the known vulnerabilities in its packages. It also provides live runtime
diagnostics: HTTP exchanges, exceptions, database queries, logs, thread and task state, health, and advisors. An AI
agent can ask the same questions over MCP, the protocol coding agents use to call tools. sharpit is a Python port of
[BootUI](https://github.com/jdubois/boot-ui), the console for Spring Boot. It speaks BootUI's JSON contract and has
a UI of its own.

## The parts

```
your FastAPI app
 └─ sharpit.install(app)                  src/sharpit/fastapi/adapter.py
     ├─ settings  (env > kwargs > defaults) src/sharpit/settings.py
     ├─ activation: on or off?             src/sharpit/engine/activation.py + fastapi/signals.py
     ├─ capture hooks (active only)        fastapi/capture.py + engine/capture/
     └─ mounts /sharpit, a small Starlette sub-app
         ├─ guard middleware (every request) src/sharpit/engine/guard.py
         ├─ /sharpit/            the UI (Svelte 5 bundle)   src/sharpit/ui/static/
         ├─ /sharpit/api/...     JSON panels               engine/collectors/*
         ├─ /sharpit/api/cli/tools/<tool>  CLI tools over HTTP engine/tools.py
         └─ /sharpit/mcp         MCP server (off by default) engine/mcp.py
```

There are two layers:

- **The engine** (`src/sharpit/engine/`) knows nothing about FastAPI or Starlette. It holds the rules: activation,
  the guard, masking, collectors, live streams, and the MCP server. Each collector takes plain data and returns BootUI's JSON
  shapes.
- **The FastAPI adapter** (`src/sharpit/fastapi/`) is the only code that touches the web framework. It reads your
  app's routes, dependencies and lifespan (`introspector.py`), mounts the sub-app, attaches runtime capture hooks, and turns
  HTTP requests into engine calls. A Django or Flask adapter would replace only this layer.

## When it turns on

`install()` decides once, at startup, in this order. The first rule that matches wins:

1. An invalid `SHARPIT_ENABLED` value → **off**.
2. An active profile is `prod` or `production` → **off**. Only `SHARPIT_ENABLED=ON` overrides this, with a warning.
3. `SHARPIT_ENABLED=OFF` → **off**. `SHARPIT_ENABLED=ON` → **on**.
4. An active profile is `dev`, `local` or `development` → **on**. The profile comes from `SHARPIT_PROFILES`, `APP_ENV`
   or `ENVIRONMENT`.
5. The process was started by a reloading dev server, `uvicorn --reload` or `fastapi dev` → **on**.
6. Otherwise → **off**.

When it is off, every path under `/sharpit` answers 404 and none of sharpit's code runs for those requests.
When it is off, capture hooks are not registered and runtime monitoring is completely skipped.

## The capture model and per-panel hooks

When active, `install()` wires runtime capture hooks. Each hook is installed only if its associated panels are enabled:

1. **ASGI capture middleware (`CaptureMiddleware`).**
   Placed as the outermost middleware inside Starlette's `ServerErrorMiddleware`.
   It records request method, masked path, status code, duration, and error flag.
   If a client disconnects before the app finishes, it records status 499.
   It creates a `ContextVar[RequestInfo | None]` token (`REQUEST`) so SQL statements and exceptions correlate with the HTTP request.
   This middleware is skipped when `http-exchanges`, `exceptions`, `sql-trace`, and `activity` are all disabled.

2. **Exception handler wrapping.**
   Wraps exception handlers in `app.exception_handlers` (unhandled exceptions and status code 500).
   It replaces `app.exception_handlers` with a dict subclass that wraps handlers added after `install()`.
   Exceptions are recorded, fingerprinted, and deduped with log records.
   This step is skipped when `exceptions` is disabled.

3. **Logging handler (`SharpitLogHandler`).**
   Attaches to non-propagating loggers (`propagate=False`, such as uvicorn loggers) and attaches to the root logger at lifespan startup.
   It collects log lines into a bounded buffer and captures `exc_info` records for exceptions.
   This step is skipped when both `log-tail` and `exceptions` are disabled.

4. **SQLAlchemy listeners.**
   Attaches class-level listeners to SQLAlchemy `Engine` if SQLAlchemy is imported.
   An `engine_connect` listener discovers active engines for connection pools and health checks.
   Statement listeners (`before_cursor_execute`, `after_cursor_execute`, `handle_error`) record SQL text, durations, and bind parameter lengths.
   Statements executed during internal sharpit checks set an `INTERNAL` context variable and are ignored.
   This step is skipped when `sql-trace` is disabled.

If a panel is disabled (`SHARPIT_PANELS_<ID>_ENABLED=false`), its hooks are skipped.
A disabled panel adds zero overhead to your app.

## Live streams (SSE) and worker processes

sharpit provides live Server-Sent Events (SSE) streams for activity, exceptions, SQL trace, and log tail.

- **Stream lifetime.**
  Each SSE stream ends after `SHARPIT_STREAM_MAX_SECONDS` (default 3 seconds) with a `retry: 1000` comment.
  The browser reconnects automatically.
  uvicorn reload and lifespan shutdown wait for open HTTP connections to finish.
  A short stream lifetime prevents live streams from blocking reload or shutdown.
- **Stream limit.**
  A global cap allows at most 20 concurrent streams across all panels.
  If the cap is reached, new stream requests receive HTTP 503 `{"error":"Too many concurrent sharpit streams"}`.
  When a browser tab closes or disconnects, the stream counter decrements immediately.
- **Rotation in the UI.**
  The UI client treats a 3-second server close as a normal rotation.
  It reconnects without displaying error banners or flickering.
- **Multiple workers.**
  In-memory buffers live inside each worker process.
  Under `uvicorn --workers N`, each request, stream, and POST is handled by whichever worker accepts the connection.
  Generated authentication tokens are created per process.
  If you allow non-loopback access with multiple workers, configure a shared `SHARPIT_AUTHENTICATION_TOKEN`.

## The guard

Every request to `/sharpit` passes these checks in order. Any failure stops it with a 403 (or a 401 for a missing
token):

1. **Who is asking.** Only loopback (`127.0.0.1`, `::1`) by default. A request carrying a forwarding header
   (`X-Forwarded-For`, `Forwarded`, `X-Real-IP`) never counts as loopback.
2. **Host header.** It must be `localhost`, a loopback address or a name in `SHARPIT_ALLOWED_HOSTS`. This blocks DNS
   rebinding, where a web page tricks your browser into calling your local server.
3. **Cross-site.** An `Origin` or `Sec-Fetch-Site` from another site is rejected, for every method. On API paths the
   full origin (scheme, host and port) must match.
4. **Token.** A caller you have allowed from outside loopback (a container gateway, a proxy range or
   `SHARPIT_ALLOW_NON_LOCALHOST`) must send the sharpit token: `Authorization: Bearer …`, or the session cookie the UI
   gets. The token is generated per process and printed at startup, unless you set one.
5. **Panel access.** Each panel can be disabled or made read-only (`SHARPIT_PANELS_<PANEL>_ENABLED`, `…_READ_ONLY`).
   Writes such as setting a logger level, clearing traces, or dismissing rules are refused on a read-only panel.

## The panels

| Panel | What it shows | How it gets it |
|---|---|---|
| Overview | App name, Python and package versions, activation reason, warnings | `install()` facts, the Python runtime and the host app |
| Configuration | Every setting with its value and where it came from (`.env:12`, env var, pydantic default, `os.getenv` in `app.py:40`) | Reads env and `.env` files, walks pydantic-settings classes and scans your source for `os.getenv` calls (AST only, never executes it) |
| Mappings | Every route: method, path, handler `module:function`, including mounts and included routers | Walks the router tree |
| Loggers | Every logger with its configured and effective level; you can change a level at runtime | The `logging` module; changes are in memory only |
| Dependency graph | Providers: your `Depends(...)` functions, lifespans and middleware, labelled app or framework | Walks FastAPI's dependency tree |
| Vulnerabilities | Known advisories for every installed package, with severity, EPSS exploit probability and the fixed version | Queries [OSV.dev](https://osv.dev) and FIRST EPSS on demand; you can dismiss findings (kept in a local file) |
| HTTP Exchanges | Ring buffer of recent HTTP requests with duration, headers, status code, and client info | ASGI capture middleware |
| Exceptions | Unhandled errors grouped by exception class and innermost application frame, with status management | Middleware, wrapped exception handlers, and `exc_info` log records |
| SQL Trace | Executed SQL statements, execution durations, slow query alerts, and live SSE feed | SQLAlchemy cursor event listeners |
| Live Activity | Correlated timeline of requests, SQL queries, and exceptions, with N+1 query detection | `ContextVar` request correlation and event streams |
| Log Tail | Recent log records and live SSE feed with resumption token | `SharpitLogHandler` ring buffer (capped at 1 MiB) |
| Alembic | Read-only database migration status, current revision, and unapplied scripts | Alembic environment inspection (refreshed on POST `alembic/refresh`) |
| Database Pools | SQLAlchemy engine connection pool sizes, active checkouts, and overflow status | SQLAlchemy pool inspection |
| Health | Status of registered database engines and custom health checks | Database dialect ping and registered health callables (POST `health/check`) |
| Threads | Thread dump and running asyncio tasks with request correlation | `threading.enumerate()` and `asyncio.all_tasks()` |
| REST API Advisor | Static inspection of FastAPI route signatures for API design violations | Route analysis with severity scoring and rule dismissals |
| HTTP Probe | In-process HTTP request execution against local routes without external network calls | Direct ASGI call using in-process client |
| CLI | The same tools callable with curl (`POST /sharpit/api/cli/tools/<tool>`) | `engine/tools.py`, shared with MCP |

## Secrets and masking

Values that look secret are masked (`******`) across the UI, JSON API, live streams, MCP, and CLI.

- **Text masking (`Masker.mask_text`).**
  Masks userinfo in URLs (`https://user:pass@host`).
  Masks value portions of sensitive `key=value`, `key: value`, and `"key": "value"` patterns.
  Masks secret-shaped tokens identified by heuristic scanners.
  Replaces SQLAlchemy query parameter blocks `[parameters: ...]` with `[parameters: ******]` when parameter capture is disabled or exposure is `METADATA_ONLY`.
- **Path masking (`Masker.mask_path`).**
  Replaces sensitive segments in URL paths with `******`.
- **Header filtering.**
  Exchanges and HTTP probe allow-list safe headers and mask sensitive values.
- **Always masked.**
  sharpit's own token is always masked, even when `SHARPIT_EXPOSE_VALUES=FULL`.
  `SHARPIT_EXPOSE_VALUES` can hide values entirely (`METADATA_ONLY`) or expose them (`FULL`, which logs a warning).
  Masking runs at capture time so raw secrets are not stored in memory buffers.

## MCP

MCP is off until you set `SHARPIT_MCP_ENABLED=true`. It then serves JSON-RPC at `/sharpit/mcp`, behind the same guard.
Its tools are read-only: overview, config, mappings, loggers, providers, vulnerabilities, and database migrations.
A vulnerability scan can only be started from the CLI endpoint or the UI.
The tools never execute arbitrary code or evaluate expressions.

## How it was tested

- **pytest suite.** Safety matrix over every guard rule and endpoint, BootUI JSON contract conformance tests, masking corpus tests, and no-side-effects tests on GET requests.
- **UI:** vitest unit tests and Playwright browser tests, with axe accessibility checks.
- **CI on GitHub:** Python 3.12 to 3.14 on Linux, Python 3.14 on Windows, the oldest supported dependency versions, a check that the committed UI bundle matches its source, and a smoke test of the built wheel.
- **Parity:** Follows BootUI's feature set and contract. Deliberate differences are documented in spec §17.
- **Dogfood:** Verified against sample and real-world applications.
