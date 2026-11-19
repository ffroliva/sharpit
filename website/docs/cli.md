# Command-Line Client

The `sharpit` command-line client lets developers, automated pipelines, and coding agents inspect and control a running application directly from the shell without an active browser session.

Built with Python standard library modules only (`urllib.request`, `argparse`, and `json`), the client adds no extra runtime dependencies and communicates with the host application over HTTP.

## Installation

Installing sharpit with the FastAPI host extra puts the `sharpit` console script on your `PATH`:

```bash
pip install "sharpit[fastapi]"
# or
uv add "sharpit[fastapi]"
```

## Connecting to an Application

By default, `sharpit` connects to a local development server at `http://localhost:8000/sharpit/api`:

```bash
sharpit overview
```

### Connection Options

Configure target location and authentication using command-line options or environment variables:

| Option | Environment Variable | Default | Description |
|---|---|---|---|
| `--url <url>` | `SHARPIT_URL` | `http://localhost:8000` | Application base URL. A bare `host:port` is normalized with `http://`. |
| `--api-path <path>` | `SHARPIT_API_PATH` | `/sharpit/api` | API mount path. |
| `--token <token>` | `SHARPIT_TOKEN` | (none) | Bearer authentication token when the console is protected. |
| `--timeout <seconds>` | (none) | `60` | Request timeout in seconds. Accepts bare numbers, `Ns`, or `Nms` (e.g. `10s`, `500ms`). |

> [!TIP]
> Use the `SHARPIT_TOKEN` environment variable rather than `--token` in shell sessions and scripts. Command-line flags are visible to other users on the machine via process listings (`ps`).

### Token Redaction Guarantee

Authentication tokens are never leaked into console output or stored files. The client redacts configured token values in place across terminal text, raw JSON bodies, usage errors, and verbose failure traces.

## Global Options

Global options apply to every command and may appear before or after the command name:

- `--json`: Print the application's JSON response verbatim. When stdout is redirected to a pipe or file, JSON output is enabled automatically.
- `--no-color`: Disable ANSI color codes in terminal output (honors the `NO_COLOR` standard).
- `-v`, `--verbose`: Print detailed error output and server causes when a request fails.
- `-V`, `--version`: Print program version and exit.
- `-h`, `--help`: Display available commands and options.

## Command Groups

The command hierarchy mirrors the sharpit tool catalog (`tools.json`). The client exposes all read diagnostics and every action tool:

### Application Overview and Wiring

- `sharpit overview`: Return stable application identity, active profiles, Python/package versions, and sharpit status.
- `sharpit config [-q <query>]`: Search effective configuration values and their sources (secrets masked).
- `sharpit beans [-q <query>]`: Search dependency providers, middleware, and lifespan handlers.
- `sharpit mappings [-q <query>]`: Search registered route paths and handler functions.
- `sharpit health`: Return component health status trees and database ping results.
- `sharpit startup`: Return the host startup timeline.

### Runtime Activity and Diagnostics

- `sharpit activity`: Correlated timeline of recent HTTP requests, SQL statements, and exceptions.
- `sharpit request-profile --id <request-id>`: Deep dive into a single request: SQL statements grouped by shape, N+1 suspects, and timing.
- `sharpit http exchanges [-n <limit>]`: Recent HTTP requests with status, duration, size, and masked headers.
- `sharpit http routes`: Route template statistics, error rates, and duration percentiles.
- `sharpit exceptions list`: Recent captured exception groups.
- `sharpit exceptions show --id <group-id>`: Stack frames, occurrences, and cause chains for an exception group.
- `sharpit exceptions clear`: Clear recorded exception history (action).
- `sharpit sql traces [-n <limit>]`: Captured SQL queries with execution time, parameters masked, and call sites.
- `sharpit sql pause`: Temporarily pause SQL query capture (action).
- `sharpit sql resume`: Resume SQL query capture (action).
- `sharpit sql clear`: Clear recorded SQL statement traces (action).
- `sharpit sql-trace insights`: Summary of SQL execution patterns and query performance insights.
- `sharpit tx list`: Transaction boundaries, status, and duration.
- `sharpit tx pause`: Pause transaction recording (action).
- `sharpit tx resume`: Resume transaction recording (action).
- `sharpit tx clear`: Clear recorded transaction events (action).
- `sharpit traces list`: Distributed trace summaries (requires OpenTelemetry SDK in host).
- `sharpit traces clear`: Clear captured distributed traces (action).
- `sharpit logs tail [-n <limit>]`: Recent log records at or above configured thresholds.
- `sharpit threads`: Active OS threads with inferred states and event-loop asyncio tasks with await chains.

### Advisor Scans and Reports

Advisors assess application configuration, architecture, and code. Each provides a cached report read, an active scan action, and a rule violations query:

| Advisor | Scan Command | Report Command | Violations Command |
|---|---|---|---|
| Architecture | `sharpit architecture scan` | `sharpit architecture report` | `sharpit architecture violations` |
| Database | `sharpit db scan` | `sharpit db report` | `sharpit db violations` |
| FastAPI | `sharpit fastapi scan` | `sharpit fastapi report` | `sharpit fastapi violations` |
| REST API | `sharpit rest-api scan` | `sharpit rest-api report` | `sharpit rest-api violations` |
| Security | `sharpit security scan` | `sharpit security report` | `sharpit security violations` |
| Vulnerabilities | `sharpit vulnerabilities scan` | `sharpit vulnerabilities report` | (in report) |

Additional database utilities:

- `sharpit db pools`: Inspect active database connection pool settings and metrics.
- `sharpit db alembic`: Show Alembic migration revisions and heads.

### Runtime Insights

- `sharpit insights list [-q <query>]`: Evaluated runtime checks (`repeated-selects`, `unbatched-write-loop`, `safe-method-dml`), coverage, and request counts.
- `sharpit insights show --id <kind-id>`: Detailed evidence and observation status for a specific insight kind.

### System, Integrations, and MCP

- `sharpit agent status`: Inspect resident background sensors.
- `sharpit agent sensor enable --id <sensor-id>`: Enable an agent sensor (action).
- `sharpit agent sensor disable --id <sensor-id>`: Disable an agent sensor (action).
- `sharpit low-footprint status`: Check low-footprint mode state.
- `sharpit low-footprint enable`: Enable low-footprint mode (action).
- `sharpit low-footprint disable`: Disable low-footprint mode (action).
- `sharpit mail`: Captured outbound emails from `smtplib` and `aiosmtplib` (dev trap).
- `sharpit metrics`: Local application meters and Prometheus metric gauges.
- `sharpit scheduled`: In-memory APScheduler jobs, Celery beat schedules, and arq cron entries.
- `sharpit github`: Local Git repository identity and cached GitHub summary.
- `sharpit data repositories`: SQLAlchemy models passed to `install(models=...)`.
- `sharpit fastapi-security`: Security dependencies and authentication filter chains.
- `sharpit sessions claude`: Claude Code integration session status.
- `sharpit sessions copilot`: GitHub Copilot integration session status.
- `sharpit sqlalchemy-statistics list`: SQLAlchemy engine and pool execution totals.
- `sharpit sqlalchemy-statistics enable`: Enable SQLAlchemy statistics collection (action).
- `sharpit tools`: List tools advertised by the target application catalog.
- `sharpit mcp status`: Display MCP server status and endpoint URL.
- `sharpit mcp enable`: Enable the application's MCP endpoint (action).
- `sharpit mcp disable`: Disable the application's MCP endpoint (action).

## Automated Gates: `--fail-on`

The `--fail-on` option turns CLI queries into CI/CD pass/fail gates.

### Finding Severity Thresholds

Advisor tools accept finding severity thresholds:

```bash
sharpit security scan --fail-on high
sharpit db report --fail-on medium
```

Supported advisor tools:

- `architecture scan`, `architecture report`
- `db scan`, `db report`
- `fastapi scan`, `fastapi report`
- `rest-api scan`, `rest-api report`
- `security scan`, `security report`
- `vulnerabilities scan`, `vulnerabilities report`

Accepted severities (case-insensitive): `critical`, `high`, `medium`, `low`, `info`.

- If findings exist at or above the chosen threshold, the client outputs findings and exits with status **3**.
- Findings below the threshold pass (exit **0**).
- When a scan status is `PARTIAL` (incomplete evidence), findings at or above threshold still exit 3; zero findings exit 0 with a note that partial coverage is not proof of absence.
- If a scan encountered errors or has no usable evidence, the gate cannot be evaluated and exits **1**.

### Evidence Sufficiency Gating

Runtime insights tools support gating on evidence completeness:

```bash
sharpit insights list --fail-on insufficient
sharpit insights show --id repeated-selects --fail-on insufficient
```

Supported tools: `insights list` and `insights show`.

- For `insights show`: Exits **3** if observation status is `INSUFFICIENT` or `PARTIAL`; exits **0** if `OBSERVED` or `FINDING`; exits **1** if `UNAVAILABLE` or `NOT_APPLICABLE`.
- For `insights list`: Exits **3** if any matching observation has `INSUFFICIENT` or `PARTIAL` evidence (`insufficient > 0` or `partial > 0`); exits **0** if all evidence is complete. If no query is provided, `--fail-on insufficient` defaults to querying `all`.

Tools without severities (such as runtime activity or thread lists) or lacking evidence sensors reject `--fail-on` with a usage error.

## Exit Codes

Exit codes follow BootUI 2.4.0 conventions (`ExitCodes`):

| Code | Label | Meaning |
|---|---|---|
| `0` | `SUCCESS` | The command completed successfully and any `--fail-on` gate passed. |
| `1` | `ERROR` | Command failed: invalid syntax or options, transport error, authentication failure, server 500 error, or unevaluable gate condition. MCP action toggle refusals also exit 1. |
| `2` | `REFUSED` | Target application policy refused the tool invocation: the panel is disabled, the endpoint is turned off, or a mutating action was denied by a read-only policy (`PANEL_ACCESS_DENIED`). Sharpit confirms the refusal against the target's `/sharpit/api/cli` catalog before exiting with status 2. |
| `3` | `THRESHOLD` | Findings met or exceeded the `--fail-on` severity threshold, or runtime evidence was insufficient. |
