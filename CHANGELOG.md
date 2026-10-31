# Changelog

All notable changes to sharpit are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-31

### Added

- F1 (HTTP Exchanges): `http-exchanges` panel and endpoint with a ring buffer of recent HTTP requests, duration, headers, status code, and path masking.
- F2 (Exceptions): `exceptions` panel and endpoints capturing unhandled errors from middleware, wrapped handlers, and log records, grouped by class and innermost application frame.
- F3 (SQL Trace): `sql-trace` panel, endpoints, and live SSE stream capturing SQLAlchemy queries via class-level events with statement categorization, normalized SQL, and slow query alerts.
- F4 (Live Activity): `activity` panel and live SSE stream correlating HTTP requests, SQL queries, and exceptions with N+1 query detection.
- F5 (Log Tail): `log-tail` panel, endpoints, and live SSE stream buffering recent logs with a 1 MiB memory cap and resume token support.
- F6 (Migrations): `alembic` panel inspecting Alembic migrations in Flyway-compatible format, with database versions read on POST `alembic/refresh`.
- F7 (Database Connection Pools): `database-connection-pools` panel and endpoint reporting SQLAlchemy pool sizes, active checkouts, and overflow status.
- F8 (Health): `health` panel and endpoint checking registered database engines via dialect ping and running custom checks on POST `health/check`.
- F9 (Threads and asyncio tasks): `threads` panel and endpoint dumping active threads and running asyncio tasks with request correlation.
- F10 (REST API advisor): `rest-api` advisor panel and endpoints running static analysis checks over FastAPI routes with severity scoring and violation paging.
- F11 (Shared advisor plumbing): shared rule definitions, single-flight scans, violation retention endpoint, and per-panel dismissal gates.
- F12 (HTTP Probe): `http-probe` panel and endpoint executing in-process ASGI calls against local routes with loopback protection and response masking.

### Changed

- Rule dismissals now check the owning panel's enabled and read-only state (`RAPI-` for `rest-api`, `::pypi:` for `vulnerabilities`), returning 403 when the panel is read-only or disabled.
- Client disconnect before response completion records status 499 in HTTP exchanges.
- Exception fingerprints group by exception class and innermost application frame rather than top stack frames.
- SQL trace uses SQLAlchemy class-level listeners rather than JDBC proxies; SQL literals are normalized and masked when parameter capture is disabled.
- Live streams (SSE) close every 3 seconds (`SHARPIT_STREAM_MAX_SECONDS`) with a retry hint to prevent blocking uvicorn reload or lifespan shutdown.
- Total concurrent live streams across all panels are capped at 20, returning HTTP 503 when full.
- Alembic database-version reads and database health checks run on POST requests (`alembic/refresh`, `health/check`) and serve cached results on GET to ensure GET requests have no side effects.
- Database connection pool reports strip query strings from database connection URLs (emitted in `jdbcUrl` for BootUI parity) to prevent secret leakage.
- Threads panel includes asyncio tasks with request correlation; OS thread states are inferred as RUNNABLE or WAITING without JVM CPU or lock metrics.
- HTTP probe executes directly via in-process ASGI calls without opening network sockets, refusing paths under the sharpit mount.
- Release workflow uploads only `.whl` and `.tar.gz` assets to GitHub Releases.
- Releases publish from CI: pushing a signed `v<version>` tag runs `.github/workflows/release.yml`, which
  publishes to PyPI with Trusted Publishing and creates the GitHub Release. `/sharpit:release` drives it.

## [0.1.0] - 2026-10-31

First release: an embedded, local-only developer console for FastAPI apps, ported from
[BootUI](https://github.com/jdubois/boot-ui) (Julien Dubois, Apache-2.0).

### Added

- `sharpit.install(app, settings=..., **options)` mounts the console at `/sharpit` and a BootUI-compatible JSON API at
  `/sharpit/api`. `settings=` takes pydantic-settings instances so the Config panel can show each value's source.
- Panels: Overview, Configuration (environment, `.env`, pydantic-settings and `os.getenv` keys, masked), Mappings,
  Loggers (runtime level changes), Beans (dependency providers, middleware, lifespan), Vulnerabilities (OSV scan with
  EPSS scores, on explicit request; dismissable rules in `.sharpit/sharpit.yml`), MCP Server and CLI.
- Read-only MCP endpoint (`POST /sharpit/api/mcp`, off by default; `SHARPIT_MCP_ENABLED=ON`) with the tools
  `get_overview`, `get_config`, `get_mappings`, `get_loggers`, `get_beans` and `get_vulnerabilities_report`; the CLI
  HTTP endpoint (`/sharpit/api/cli`) offers the same catalogue plus the vulnerability scan.
- Configuration through `SHARPIT_*` environment variables and `install()` keywords; the environment wins. Invalid values
  fall back to a fail-safe value and record a warning.
- Fail-closed activation: on for `SHARPIT_ENABLED=ON`, a dev profile, `uvicorn --reload` or `fastapi dev`; a `prod`
  profile switches it off unless `SHARPIT_ENABLED=ON` forces it. When off, the mount stays in place (as in BootUI) and
  every path under it answers a plain 404 from the host's 404 handler; a host with a catch-all or authenticate-first
  route answers those paths differently, so the mount can be told apart. `path="/"` and a trailing slash are refused.
- Request guard: loopback-only by default, `Host` allow-list, full-origin (API paths) and `Sec-Fetch-Site` cross-site checks on
  every method, bearer token with `HttpOnly` session cookie for untrusted sources.
- Secret masking of values, defaults and suggestions in API, MCP and CLI output, including pydantic `SecretStr` and any URL with userinfo.
- Extras `sharpit[fastapi]` and `sharpit[settings]`; typed package (`py.typed`); prebuilt UI in the wheel, so end users
  never need Node.

### Deviations from BootUI

Listed in section 14 of the design spec. The main ones:

- FastAPI only; Django and Flask are out of scope.
- A new Svelte UI instead of BootUI's Vue UI, over the same JSON contract.
- Activation uses profile variables and a dev-server signal read from the command line (no DevTools equivalent);
  `uvicorn.run(..., reload=True)` from a script is not detected.
- The cross-site check applies to every method, compares the full origin on API paths, and any forwarded header makes a caller
  untrusted unless a trusted proxy is configured.
- `defaultValue` is masked as well, because Python defaults come from code.
- Beans are dependency providers, middleware and lifespan rather than an IoC container.
- Deferred: config overrides, health, profile diff and the `sharpit` command-line client (the HTTP endpoint ships).

### Known limitations

- State (token, MCP switch, logger levels, scan cache) is per process under `--workers` and `--reload`.
- Behind a TLS-terminating proxy, uvicorn needs `--proxy-headers` for the Origin check to pass.
- Masking is name- and shape-based: vendor-prefixed tokens under harmless names (`sk_live_...`, `ghp_...`) can show.

[Unreleased]: https://github.com/ffroliva/sharpit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.2.0
[0.1.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.1.0
