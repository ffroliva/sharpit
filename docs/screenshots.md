# Screenshot catalog

Every sharpit panel at 0.4.0, in the light and the dark theme, grouped as the rail groups them. **New in 0.4.0**
marks the panels added in that release. A panel marked *unavailable here* is shown as it renders when its
prerequisite is missing: that page is the real UI, with the server's own reason.

The images come from the Playwright suites in `ui/`, at a 1280x800 viewport, against the example apps with fake
secrets. Panels that need SQLAlchemy, a database or live requests come from the SQLAlchemy sample
(`examples/fastapi_sqla`); the rest come from the plain example app (`examples/fastapi_sample`).

## Overview

### Scorecard

App, Python and package versions, active profiles, activation reason and warnings.

| Light | Dark |
|---|---|
| ![Scorecard, light](../ui/tests/e2e/screenshots/overview-light.png) | ![Scorecard, dark](../ui/tests/e2e/screenshots/overview-dark.png) |

### Live Activity

Correlated timeline of requests, SQL queries and exceptions, with N+1 query detection.

| Light | Dark |
|---|---|
| ![Live Activity, light](../ui/tests/e2e/screenshots/activity-light.png) | ![Live Activity, dark](../ui/tests/e2e/screenshots/activity-dark.png) |

## Runtime

### Health

Status of registered database engines and custom health checks.

| Light | Dark |
|---|---|
| ![Health, light](../ui/tests/e2e/screenshots/health-light.png) | ![Health, dark](../ui/tests/e2e/screenshots/health-dark.png) |

### Threads

Thread dump and running asyncio tasks with request correlation.

| Light | Dark |
|---|---|
| ![Threads, light](../ui/tests/e2e/screenshots/threads-light.png) | ![Threads, dark](../ui/tests/e2e/screenshots/threads-dark.png) |

### Log Tail

Recent log records and a live SSE feed with a resumption token.

| Light | Dark |
|---|---|
| ![Log Tail, light](../ui/tests/e2e/screenshots/log-tail-light.png) | ![Log Tail, dark](../ui/tests/e2e/screenshots/log-tail-dark.png) |

### Exceptions

Unhandled errors grouped by exception class and innermost application frame.

| Light | Dark |
|---|---|
| ![Exceptions, light](../ui/tests/e2e/screenshots/exceptions-light.png) | ![Exceptions, dark](../ui/tests/e2e/screenshots/exceptions-dark.png) |

### HTTP Exchanges

Ring buffer of recent HTTP requests with duration, headers, status code and path masking.

| Light | Dark |
|---|---|
| ![HTTP Exchanges, light](../ui/tests/e2e/screenshots/http-exchanges-light.png) | ![HTTP Exchanges, dark](../ui/tests/e2e/screenshots/http-exchanges-dark.png) |

### HTTP Probe

In-process HTTP request execution against local routes, without external network calls.

| Light | Dark |
|---|---|
| ![HTTP Probe, light](../ui/tests/e2e/screenshots/http-probe-light.png) | ![HTTP Probe, dark](../ui/tests/e2e/screenshots/http-probe-dark.png) |

### Traces (new in 0.4.0, unavailable here)

OpenTelemetry spans from the application's own SDK `TracerProvider`, with SQL literals in `db.statement` normalised
and masked. Shown unavailable: the OpenTelemetry SDK is not installed in the dev environment.

| Light | Dark |
|---|---|
| ![Traces, light](../ui/tests/e2e/screenshots/traces-light.png) | ![Traces, dark](../ui/tests/e2e/screenshots/traces-dark.png) |

## Database

### SQL Trace

Executed SQL statements, execution durations, slow query alerts and a live SSE feed.

| Light | Dark |
|---|---|
| ![SQL Trace, light](../ui/tests/e2e/screenshots/sql-trace-light.png) | ![SQL Trace, dark](../ui/tests/e2e/screenshots/sql-trace-dark.png) |

### Database Connection Pools

SQLAlchemy engine connection pool sizes, checkouts and overflow status.

| Light | Dark |
|---|---|
| ![Database Connection Pools, light](../ui/tests/e2e/screenshots/database-connection-pools-light.png) | ![Database Connection Pools, dark](../ui/tests/e2e/screenshots/database-connection-pools-dark.png) |

### Alembic

Read-only database migration status and pending versions.

| Light | Dark |
|---|---|
| ![Alembic, light](../ui/tests/e2e/screenshots/alembic-light.png) | ![Alembic, dark](../ui/tests/e2e/screenshots/alembic-dark.png) |

### Data (new in 0.4.0)

SQLAlchemy 2.0 mapped classes (table, primary-key type, relationships) from `install(models=...)`.

| Light | Dark |
|---|---|
| ![Data, light](../ui/tests/e2e/screenshots/data-light.png) | ![Data, dark](../ui/tests/e2e/screenshots/data-dark.png) |

### PostgreSQL (new in 0.4.0, unavailable here)

Vital signs, sessions, statements, indexes, tables, vacuum, replication and settings, read on explicit request in one
read-only transaction. Shown before a read: the sample runs on SQLite, so there is no PostgreSQL server to read.

| Light | Dark |
|---|---|
| ![PostgreSQL, light](../ui/tests/e2e/screenshots/postgresql-light.png) | ![PostgreSQL, dark](../ui/tests/e2e/screenshots/postgresql-dark.png) |

### SQLAlchemy Statistics (new in 0.4.0)

Statement counts from SQL Trace's lifetime totals, the slowest statement and N+1 candidates per route.

| Light | Dark |
|---|---|
| ![SQLAlchemy Statistics, light](../ui/tests/e2e/screenshots/sqlalchemy-statistics-light.png) | ![SQLAlchemy Statistics, dark](../ui/tests/e2e/screenshots/sqlalchemy-statistics-dark.png) |

## Configuration

### Configuration

Environment, `.env` files, pydantic-settings and `os.getenv` keys, the winning source of each value, masked.

| Light | Dark |
|---|---|
| ![Configuration, light](../ui/tests/e2e/screenshots/config-light.png) | ![Configuration, dark](../ui/tests/e2e/screenshots/config-dark.png) |

### Mappings

Every route of the host app.

| Light | Dark |
|---|---|
| ![Mappings, light](../ui/tests/e2e/screenshots/mappings-light.png) | ![Mappings, dark](../ui/tests/e2e/screenshots/mappings-dark.png) |

### Loggers

Logger tree with levels you can change at runtime.

| Light | Dark |
|---|---|
| ![Loggers, light](../ui/tests/e2e/screenshots/loggers-light.png) | ![Loggers, dark](../ui/tests/e2e/screenshots/loggers-dark.png) |

### Providers

Dependency providers, middleware and lifespan, with their dependencies; the Graph view draws them.

| Light | Dark |
|---|---|
| ![Providers, light](../ui/tests/e2e/screenshots/beans-light.png) | ![Providers, dark](../ui/tests/e2e/screenshots/beans-dark.png) |
| ![Providers graph, light](../ui/tests/e2e/screenshots/beans-graph-light.png) | ![Providers graph, dark](../ui/tests/e2e/screenshots/beans-graph-dark.png) |

### MCP Server

Status and switch for the read-only MCP endpoint (here made read-only by `SHARPIT_PANELS_MCP_SERVER_READ_ONLY=true`).

| Light | Dark |
|---|---|
| ![MCP Server, light](../ui/tests/e2e/screenshots/mcp-server-light.png) | ![MCP Server, dark](../ui/tests/e2e/screenshots/mcp-server-dark.png) |

### CLI

The same tool catalogue over plain HTTP (`POST /sharpit/api/cli/tools/<tool>`).

| Light | Dark |
|---|---|
| ![CLI, light](../ui/tests/e2e/screenshots/cli-light.png) | ![CLI, dark](../ui/tests/e2e/screenshots/cli-dark.png) |

## Advisors

### REST API

Static inspection of FastAPI route signatures for API design violations.

| Light | Dark |
|---|---|
| ![REST API, light](../ui/tests/e2e/screenshots/rest-api-light.png) | ![REST API, dark](../ui/tests/e2e/screenshots/rest-api-dark.png) |

### Vulnerabilities

Installed distributions checked against OSV and scored with EPSS, on explicit request. Shown before a scan, with the
package inventory: the e2e run never calls OSV.dev.

| Light | Dark |
|---|---|
| ![Vulnerabilities, light](../ui/tests/e2e/screenshots/vulnerabilities-light.png) | ![Vulnerabilities, dark](../ui/tests/e2e/screenshots/vulnerabilities-dark.png) |

## Regenerating

From `ui/`, with `SHARPIT_E2E_PORT` set to a port leased through `agentctl` (see
[ci.md](development/ci.md)), run the plain app first and the SQLAlchemy sample second, so its images replace the
plain app's for the panels it covers:

```bash
SHOTS=1 SHARPIT_E2E_PORT=<port> npx playwright test tests/e2e/a11y.spec.ts
SHOTS=1 SHARPIT_E2E_PORT=<port> npx playwright test -c playwright.sqla.config.ts
```
