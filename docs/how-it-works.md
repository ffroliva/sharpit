# How sharpit works

sharpit is a developer console that runs inside your FastAPI app while you develop it. You add one line:

```python
import sharpit

sharpit.install(app)
```

Then open `http://127.0.0.1:8000/sharpit` and you see what your app is really running with: its configuration, its
routes, its loggers, its dependency graph and the known vulnerabilities in its packages. An AI agent can ask the same
questions over MCP, the protocol coding agents use to call tools. sharpit is a Python port of
[BootUI](https://github.com/jdubois/boot-ui), the console for Spring Boot. It speaks BootUI's JSON contract and has
a new UI of its own.

## The parts

```
your FastAPI app
 └─ sharpit.install(app)                  src/sharpit/fastapi/adapter.py
     ├─ settings  (env > kwargs > defaults) src/sharpit/settings.py
     ├─ activation: on or off?             src/sharpit/engine/activation.py + fastapi/signals.py
     └─ mounts /sharpit, a small Starlette sub-app
         ├─ guard middleware (every request) src/sharpit/engine/guard.py
         ├─ /sharpit/            the UI (Svelte 5 bundle)   src/sharpit/ui/static/
         ├─ /sharpit/api/...     JSON panels               engine/collectors/*
         ├─ /sharpit/api/cli     the same tools over HTTP   engine/tools.py
         └─ /sharpit/mcp         MCP server (off by default) engine/mcp.py
```

There are two layers:

- **The engine** (`src/sharpit/engine/`) knows nothing about FastAPI or Starlette. It holds the rules: activation,
  the guard, masking, the collectors and the MCP server. Each collector takes plain data and returns BootUI's JSON
  shapes.
- **The FastAPI adapter** (`src/sharpit/fastapi/`) is the only code that touches the web framework. It reads your
  app's routes, dependencies and lifespan (`introspector.py`), mounts the sub-app and turns HTTP requests into engine
  calls. A Django or Flask adapter would replace only this layer.

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
   Writes such as setting a logger level or starting a scan are refused on a read-only panel.

## The panels

| Panel | What it shows | How it gets it |
|---|---|---|
| Overview | App name, Python and package versions, activation reason, warnings | `install()` facts, the Python runtime and the host app |
| Configuration | Every setting with its value and where it came from (`.env:12`, env var, pydantic default, `os.getenv` in `app.py:40`) | Reads env and `.env` files, walks pydantic-settings classes and scans your source for `os.getenv` calls (AST only, never executes it) |
| Mappings | Every route: method, path, handler `module:function`, including mounts and included routers | Walks the router tree |
| Loggers | Every logger with its configured and effective level; you can change a level at runtime | The `logging` module; changes are in memory only |
| Dependency graph | Providers: your `Depends(...)` functions, lifespans and middleware, labelled app or framework | Walks FastAPI's dependency tree |
| Vulnerabilities | Known advisories for every installed package, with severity, EPSS exploit probability and the fixed version | Queries [OSV.dev](https://osv.dev) and FIRST EPSS on demand; you can dismiss findings (kept in a local file) |
| CLI | The same tools callable with `curl` (`POST /sharpit/api/cli/<tool>`) | `engine/tools.py`, shared with MCP |

## Secrets

Values that look secret are shown as `******` everywhere: the UI, the JSON API, MCP and the CLI. That covers names
containing `password`, `secret`, `token`, `key` and similar, pydantic `SecretStr`, and any URL that carries a user name
or password. sharpit's own token is always masked, even when you turn masking off. `SHARPIT_EXPOSE_VALUES` can hide
values entirely (`METADATA_ONLY`) or show them unmasked (`FULL`, which logs a warning).

## MCP

MCP is off until you set `SHARPIT_MCP_ENABLED=true`. It then serves JSON-RPC at `/sharpit/mcp`, behind the same guard.
Its six tools are read-only: overview, config, mappings, loggers, providers and vulnerabilities. A vulnerability scan
can only be started from the CLI endpoint. The tools never execute code or evaluate expressions. This is the main
difference from Tidewave-style consoles, which do run code.

## How it was tested

- **pytest: 1579 tests.** They include a safety matrix over every guard rule, conformance tests against BootUI's JSON
  contract, and a test that installing sharpit has no side effects on the host app.
- **UI:** vitest has 90 unit tests and Playwright 16 browser tests, with axe accessibility checks.
- **CI on GitHub:** Python 3.12 to 3.14 on Linux, Python 3.14 on Windows, the oldest supported dependency versions, a
  check that the committed UI bundle matches its source, and a smoke test of the built wheel.
- **Parity:** `replica/features.csv` lists 100 BootUI features, all covered. The places sharpit deliberately differs
  are in spec §14.
- **Dogfood:** it ran on KliperMedia (358 routes, 143 packages). The report is in
  `docs/reports/2026-10-31-dogfood-klipermedia.md`.
