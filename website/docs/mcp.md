# MCP for AI agents

sharpit can serve the same data as its panels to an AI agent over [MCP](https://modelcontextprotocol.io), the protocol
coding agents use to call tools. The MCP endpoint serves read tools only, and the same guard chain and masking apply
as in the UI.

## Turn it on

The MCP endpoint is **off by default**. Enable it in one of three ways:

- the environment variable `SHARPIT_MCP_ENABLED=ON`
- the keyword `sharpit.install(app, mcp_enabled="ON")`
- the switch in the MCP Server panel

Then point a streamable-HTTP MCP client at `http://127.0.0.1:8000/sharpit/api/mcp` (POST only).

## Tools

44 read tools, grouped by what they answer. Search tools take a `query` and a `limit`; every result is capped by
`SHARPIT_MCP_MAX_RESULTS`. The names and the read or action split match BootUI 2.3.0 wherever BootUI has the same
tool.

### The app

- `get_overview`: app identity, Python and package versions, active profiles and sharpit's status. Call it first.
- `get_config`: search the effective configuration by name or value, with the source each value came from. Secrets are masked.
- `get_profile_diff`: compare configuration across active profiles using masked local data.
- `get_mappings`: search routes and their handlers by path, HTTP method or handler name.
- `get_beans`: search dependency providers, middleware and the lifespan handler, to check how the app is wired.
- `get_loggers`: search loggers and read their configured and effective levels.
- `get_data_repositories`: the SQLAlchemy mapped classes passed to `install(models=...)`, with table, primary-key type and relationships. Never configures mappers or runs SQL.

### Requests and errors

- `get_live_activity`: newest requests, SQL statements and exceptions on one timeline, linked by request id. Start here to diagnose one request.
- `get_request_profile`: what one request did, by request id: its SQL statements grouped by shape with N+1 suspects, its exceptions and the time spent in SQL.
- `get_http_exchanges`: recent HTTP requests with status, duration, size and masked headers.
- `get_http_routes`: the routes the app served, grouped by method and route template, with request counts, errors and duration percentiles.
- `get_exceptions`: recent exception groups, newest first.
- `get_exception_detail`: stack frames, causes and occurrences for one group id from `get_exceptions`.
- `get_log_tail`: the latest buffered log lines, masked when captured.
- `get_security_logs`: newest authentication and authorization audit events (401 and 403 responses, and events from `sharpit.record_security_event`).

### Database

- `get_sql_traces`: recent SQL statements with timings.
- `get_sql_trace_insights`: the retained statements ranked by total, max, average, p95 and p99 duration, executions and errors, attributed to the routes that issued them. Statements are normalised: no literal or bound value is shown.
- `get_sqlalchemy_statistics`: lifetime statement counts, the slowest statement and N+1 candidates per route, from the SQL Trace recorder.
- `get_transactions`: recent SQLAlchemy transactions with status, duration, savepoint depth and connection hold time.
- `get_database_connection_pools`: each SQLAlchemy engine's pool settings and live counters. Never borrows a connection.
- `get_alembic_migrations`: migration history from the revision files and each database's last read version. Never connects to a database.
- `get_postgresql_report`: the last completed PostgreSQL runtime view. Before the first read its `status` is `NOT_READ`, which means nothing has been looked at. Does not query the server.
- `get_mysql_report`: the same for MySQL and MariaDB.

### GitHub

- `get_github_dashboard` (`github` on the CLI endpoint): local repository identity and the last cached dashboard report. This passive read never calls GitHub.

### Runtime

- `get_health`: the cached health tree (database pings and your own checks). Never runs a check.
- `get_threads`: threads and asyncio tasks with their stacks, and the request each task serves. No variable values.
- `get_startup_timeline`: the host's startup steps in order, with their durations; search by `query`, capped by `limit`.
- `get_traces`: the OpenTelemetry traces the app recorded, newest first, with masked span attributes. Needs the app's own SDK `TracerProvider`.
- `get_low_footprint`: low-footprint mode status and capture hook outcomes.

### Agent sessions

- `get_copilot_sessions`: the bounded, sanitized Copilot CLI session inventory read from local session files; search by `query`, capped by `limit`. Raw prompts, tool arguments, command output and diffs are left out.
- `get_claude_code_sessions`: the same for Claude Code sessions.

### AI Framework

- `get_ai_overview`: GenAI usage from the app's recorded OpenTelemetry spans; CLI alias `ai overview`.

### Advisors and security

Each advisor has a cached report tool and a tool that pages the retained violations of one rule
(`id` and `scanId` from the report, plus `offset` and `limit`). None of them starts a scan.

- `get_vulnerabilities_report`: the cached vulnerability report, or the package inventory before the first scan. No network call.
- `get_rest_api_report`, `get_rest_api_rule_violations`: the REST API advisor.
- `get_security_report`, `get_security_rule_violations`: the security advisor.
- `get_database_advisor_report`, `get_database_advisor_rule_violations`: the database advisor.
- `get_architecture_report`, `get_architecture_rule_violations`: the architecture advisor.
- `get_fastapi_report`, `get_fastapi_rule_violations`: the FastAPI advisor.
- `get_fastapi_security`: the FastAPI security configuration: routes, their security dependencies and scopes. Sends no request through any of them.

## Actions

19 action tools change state, send data off the machine, or start a scan. **They are not served over MCP**: the
`tools/list` answer holds the 44 read tools above and nothing else. They are listed here because each is part of the
tool catalogue. Actions are available through the CLI endpoint,
`POST /sharpit/api/cli/tools/<tool>` (`SHARPIT_CLI_ENABLED`, on by default), behind the same guard chain.
An action is refused when sharpit is read-only (`SHARPIT_READ_ONLY=true`: "sharpit is read-only via SHARPIT_READ_ONLY=true") or its panel is read-only (`SHARPIT_PANELS_<ID>_READ_ONLY=true`: "Panel is read-only via SHARPIT_PANELS_<ID>_READ_ONLY=true"), and when its panel is disabled; a read tool still answers on a read-only panel.

Scans and reads that call out:

- `vulnerabilities_scan`: query OSV.dev (and FIRST for EPSS scores) for known vulnerabilities in the dependencies. Sends package names and versions off the machine.
- `rest_api_scan`: inspect the routes and API design.
- `security_scan`: review the security configuration.
- `database_advisor_scan`: introspect the schema of every registered engine through a verified read-only connection.
- `architecture_scan`: inspect the import graph and package structure.
- `fastapi_scan`: inspect route handlers and source for FastAPI risks.
- `postgresql_read`: read PostgreSQL's own `pg_stat_*` and catalog views and record what the server reports.
- `mysql_read`: read MySQL's `performance_schema` and `information_schema` views.

Buffers and recording, which only touch sharpit's own bounded in-memory capture:

- `clear_exceptions`: clear the exception groups and occurrences.
- `clear_sql_traces`: clear the SQL trace buffer.
- `pause_sql_trace_recording`, `resume_sql_trace_recording`: stop and restart SQL trace recording.
- `clear_transactions`: clear the retained transactions.
- `pause_transaction_recording`, `resume_transaction_recording`: stop and restart transaction recording.
- `clear_traces`: clear the span buffer. The app's tracer provider and exporters are untouched.
- `enable_low_footprint`, `disable_low_footprint`: pause/resume sharpit's capture hooks; enabling also discards retained buffers. These are CLI and guarded API actions, not MCP tools.
- `enable_sqlalchemy_statistics`: acknowledge statistics collection. Statistics are always on while SQL Trace records, so nothing changes.

## What an agent cannot do

Over MCP an agent cannot change a logger level, clear a buffer, pause SQL recording, operate Live Memory controls or start a scan of any kind. Those
stay in the UI, or a plain HTTP call to `POST /sharpit/api/cli/tools/<tool>`, so anything that changes state or sends
data off the machine needs a person.

## Agent skill

An agent skill that teaches an AI assistant to install and use sharpit is in
[`skills/sharpit`](https://github.com/ffroliva/sharpit/tree/main/skills/sharpit). There is no `sharpit` command-line tool yet.
The HTTP endpoint above is what a future command would call.
