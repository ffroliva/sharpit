# MCP for AI agents

sharpit can serve the same data as its panels to an AI agent over [MCP](https://modelcontextprotocol.io), the protocol
coding agents use to call tools. Every tool is read-only, and the same guard chain and masking apply as in the UI.

## Turn it on

The MCP endpoint is **off by default**. Enable it in one of three ways:

- the environment variable `SHARPIT_MCP_ENABLED=ON`
- the keyword `sharpit.install(app, mcp_enabled="ON")`
- the switch in the MCP Server panel

Then point a streamable-HTTP MCP client at `http://127.0.0.1:8000/sharpit/api/mcp` (POST only).

## Tools

18 tools, grouped by what they answer. Search tools take a query and a `limit`; every result is capped by
`SHARPIT_MCP_MAX_RESULTS`.

### The app

- `get_overview`: app identity, Python and package versions, active profiles and sharpit's status. Call it first.
- `get_config`: search the effective configuration by name or value, with the source each value came from. Secrets are masked.
- `get_mappings`: search routes and their handlers by path, HTTP method or handler name.
- `get_beans`: search dependency providers, middleware and the lifespan handler, to check how the app is wired.
- `get_loggers`: search loggers and read their configured and effective levels.

### Requests and errors

- `get_live_activity`: newest requests, SQL statements and exceptions on one timeline, linked by request id. Start here to diagnose one request.
- `get_http_exchanges`: recent HTTP requests with status, duration, size and masked headers.
- `get_exceptions`: recent exception groups, newest first.
- `get_exception_detail`: stack frames, causes and occurrences for one group id from `get_exceptions`.
- `get_log_tail`: the latest buffered log lines, masked when captured.

### Database

- `get_sql_traces`: recent SQL statements with timings.
- `get_database_connection_pools`: each SQLAlchemy engine's pool settings and live counters. Never borrows a connection.
- `get_alembic_migrations`: migration history from the revision files and each database's last read version. Never connects to a database.

### Runtime

- `get_health`: the cached health tree (database pings and your own checks). Never runs a check.
- `get_threads`: threads and asyncio tasks with their stacks, and the request each task serves. No variable values.

### Advisors

- `get_vulnerabilities_report`: the cached vulnerability report, or the package inventory before the first scan. No network call.
- `get_rest_api_report`: the last REST API advisor report. Does not start a scan.
- `get_rest_api_rule_violations`: one page of violations for one rule of that report.

## What an agent cannot do

There is no action tool. Over MCP an agent cannot change a logger level, clear a buffer, pause SQL recording or start
a vulnerability or REST API scan. Those stay in the UI and the CLI endpoint (`POST /sharpit/api/cli/tools/<tool>`),
so anything that changes state or sends data off the machine needs a person.

## Agent skill

An agent skill that teaches an AI assistant to install and use sharpit is in
[`skills/sharpit`](https://github.com/ffroliva/sharpit/tree/main/skills/sharpit). The `sharpit` command-line client
is planned and not shipped yet.
