---
name: sharpit
version: "0.1"
description: >
  Use when adding sharpit to a FastAPI app, configuring it with SHARPIT_* environment variables, working out why
  /sharpit answers 404, reading the sharpit JSON API, or connecting an AI agent to sharpit's read-only MCP endpoint.
  sharpit is a local developer console and pytest gate for FastAPI apps, a Python port of BootUI by Julien Dubois.
---

# sharpit: the local developer console for FastAPI apps

> **0.7.0.** APIs, panels and settings can still change before 1.0.
> The design source is `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md`; when this file and the code
> disagree, the code wins.

sharpit is a Python port of [BootUI](https://github.com/jdubois/boot-ui), the Spring Boot dev console. One call mounts
a console at `/sharpit` and a BootUI-compatible JSON API at `/sharpit/api` inside your own app. It is for **local
development only**: it switches itself off unless it has a reason to be on, and it refuses non-loopback callers.

## Playbooks

For a guided investigation, load the [shared playbook contract](references/playbooks/README.md) and **one** guide:

| User goal | Playbook |
|---|---|
| Assess the application; what should I fix first? | [Application checkup](references/playbooks/application-checkup.md) |
| Reduce SQL work or investigate transactions | [Database efficiency](references/playbooks/database-efficiency.md) |
| Explain a slow route | [Slow endpoint](references/playbooks/slow-endpoint.md) |
| Diagnose exceptions or errors behind successful responses | [Errors and hidden failures](references/playbooks/errors-and-hidden-failures.md) |
| Check that a fix ran and changed the intended behavior | [Verify my changes](references/playbooks/verify-my-changes.md) |
| Investigate CPU, memory, thread growth, or event loop stalls | [Python performance and memory](references/playbooks/python-performance-and-memory.md) |

These are instructions for the external coding agent, not new sharpit tools. Load only the playbook that matches the goal.

## Install

Python 3.12+. Runtime dependencies are only `starlette` and `packaging`; FastAPI 0.115+ is the supported host.

```bash
uv add "sharpit[fastapi]"           # or: pip install "sharpit[fastapi]"
```

The extras are `fastapi`, `settings` (pydantic-settings, for Config provenance) and `test`. SQLAlchemy, a database driver
and OpenTelemetry have no extra: sharpit reads them from your app if it imported them. The panel to library to extra
table is in `website/docs/installation.md`.

## Add it to an app

```python
from fastapi import FastAPI
import sharpit

app = FastAPI()
sharpit.install(app)  # mounts /sharpit and /sharpit/api
```

`install(app, *, settings=(), **options)`:

- `**options` are the settings below in snake case, e.g. `sharpit.install(app, read_only=True)`. An unknown name raises
  `TypeError`.
- `settings=` takes your app's own settings objects (for example a pydantic-settings instance) so the Config panel can
  show where each value came from. pydantic-settings is read only if it is installed.
- `models=` takes SQLAlchemy 2.0 mapped classes for the Data panel: a declarative base, a registry, or a list of them
  or of mapped classes (`sharpit.install(app, models=Base)`). sharpit never configures mappers or runs SQL for it.
- `install()` reads settings once, decides activation once, and inserts its mount first in `app.router.routes`, so a
  catch-all route of yours cannot shadow it. It does no I/O at install time; expensive work runs on the first GET that
  needs it.

Open `http://127.0.0.1:8000/sharpit/` while the app runs.

## Activation: why /sharpit is on or off

sharpit decides once, in `install()`, in this order (first match wins):

1. An active profile is in `SHARPIT_DISABLED_PROFILES` (default `prod,production`) → **disabled**, unless
   `SHARPIT_ENABLED=ON` (then enabled with a warning).
2. `SHARPIT_ENABLED=OFF` → disabled. 3. `SHARPIT_ENABLED=ON` → enabled.
4. An active profile is in `SHARPIT_ENABLED_PROFILES` (default `dev,local,development`) → enabled.
5. A reloading dev server is detected: `uvicorn --reload` or `fastapi dev` → enabled.
6. Otherwise → **disabled**.

Active profiles are the union of the variables named in `SHARPIT_PROFILE_VARS` (default
`SHARPIT_PROFILES,APP_ENV,ENVIRONMENT`), split on commas, trimmed and lower-cased, so `Production`, ` prod ` and
`prod,dev` all count as production. Plain `ENV` is deliberately not read. `uvicorn.run(..., reload=True)` from a script
is **not** detected: set `APP_ENV=dev` or `SHARPIT_ENABLED=ON`.

**When disabled, every path and method under `/sharpit` answers 404**, so nothing reveals that sharpit is installed,
and a log line gives the reason (WARNING when sharpit was asked for but is still off, INFO otherwise). That is the usual answer to "why is /sharpit 404": you are in a production
profile, or nothing enabled it. The reason text is BootUI's, e.g. `Disabled by SHARPIT_ENABLED=OFF` or
`Disabled because active profile 'prod' is in SHARPIT_DISABLED_PROFILES`; when enabled, `GET /sharpit/api/overview`
reports it under `activation`.

## Settings (`SHARPIT_*`)

Every setting is an env var and an `install()` keyword. **The env var overrides the keyword**, so production can always
force `SHARPIT_ENABLED=OFF`. An empty value counts as unset. Booleans accept `true/false/yes/no/on/off/1/0`. An invalid
value never raises: that setting takes its fail-safe value (disabled, read-only, masked) and a warning is recorded.
Naming rule: `SHARPIT_` + the BootUI property without `bootui.`, with `.` and `-` turned into `_`, upper case; the
keyword is the same name in lower case.

| Env var | Keyword | Default | Meaning |
|---|---|---|---|
| `SHARPIT_ENABLED` | `enabled` | `AUTO` | `ON` / `OFF` / `AUTO` (use the rules above) |
| `SHARPIT_ENABLED_PROFILES` | `enabled_profiles` | `dev,local,development` | profiles that turn it on |
| `SHARPIT_DISABLED_PROFILES` | `disabled_profiles` | `prod,production` | profiles that turn it off |
| `SHARPIT_PROFILE_VARS` | `profile_vars` | `SHARPIT_PROFILES,APP_ENV,ENVIRONMENT` | where profiles are read |
| `SHARPIT_PATH` | `path` | `/sharpit` | console mount |
| `SHARPIT_API_PATH` | `api_path` | `/sharpit/api` | must start with `path`, else `ValueError` |
| `SHARPIT_READ_ONLY` | `read_only` | `false` | refuse every write action |
| `SHARPIT_ALLOW_NON_LOCALHOST` | `allow_non_localhost` | `false` | allow remote callers (token required) |
| `SHARPIT_ALLOWED_HOSTS` | `allowed_hosts` | empty | extra `Host` names to accept |
| `SHARPIT_TRUSTED_PROXIES` | `trusted_proxies` | empty | proxies whose forwarded headers are accepted |
| `SHARPIT_AUTHENTICATION_TOKEN` | `authentication_token` | generated | bearer token for untrusted sources |
| `SHARPIT_EXPOSE_VALUES` | `expose_values` | `MASKED` | `MASKED`, `METADATA_ONLY` or `FULL` (logs a warning) |
| `SHARPIT_MASK_SECRETS` | `mask_secrets` | `true` | mask secret-looking names and values |
| `SHARPIT_SHOW_BANNER` | `show_banner` | `true` | print the startup banner to stderr |
| `SHARPIT_STATE_DIR` | `state_dir` | `.sharpit` | holds `sharpit.yml` (dismissals, created on first write) and `identity.key` (created by an active `install()` or `pytest --sharpit`, with a `.gitignore` naming it) |
| `SHARPIT_IDENTITY_KEY` | `identity_key` | unset | optional shared UTF-8 key (at least 32 bytes) for stable SQLite statement identities, overriding `identity.key`; masked by value in every exposure, `FULL` included. One repeated character warns |
| `SHARPIT_VULNERABILITIES_OSV_ENABLED` | `vulnerabilities_osv_enabled` | `true` | allow the OSV scan |
| `SHARPIT_MCP_ENABLED` | `mcp_enabled` | `OFF` | turn on the read-only MCP endpoint |
| `SHARPIT_FREE_ON_IDLE_ENABLED` / `SHARPIT_FREE_ON_IDLE_TIMEOUT` | `free_on_idle_enabled` / `free_on_idle_timeout` | `true` / `300` | suspend capture hooks after API inactivity |
| `SHARPIT_PANELS_<ID>_ENABLED` / `_READ_ONLY` | `panels={"<id>": {...}}` | on / off | per-panel switches, e.g. `SHARPIT_PANELS_LOGGERS_READ_ONLY=true` |

The full list (`SHARPIT_MCP_*`, `SHARPIT_CLI_*`, `SHARPIT_VULNERABILITIES_*`, `SHARPIT_TRUST_CONTAINER_GATEWAY`,
`SHARPIT_CONFIG_SCAN`, ...) is in `website/docs/settings.md` and `src/sharpit/settings.py`. Durations accept `10s`, `500ms` or a bare number of seconds.

## Safety model

- **Local only.** Requests must come from loopback with a loopback or allow-listed `Host`. If `Forwarded`,
  `X-Forwarded-For` or `X-Real-IP` is present and no trusted proxy is configured, the caller is treated as remote.
- **Cross-site reads are refused** on every method (`Sec-Fetch-Site: cross-site`, or an `Origin` whose host differs),
  even if your app has `CORSMiddleware(allow_origins=["*"])`.
- **Remote access needs a token.** With `SHARPIT_ALLOW_NON_LOCALHOST=true`, untrusted callers must send
  `Authorization: Bearer <token>`; a generated token is printed once to stderr. A browser exchanges it with
  `POST /sharpit/api/auth/session` for an `HttpOnly; SameSite=Strict` cookie. Multi-worker deployments must set
  `SHARPIT_AUTHENTICATION_TOKEN` themselves.
- **Secrets are masked** (`******`) in values, defaults, errors and MCP output, including pydantic `SecretStr`.
- **GET never has side effects**: no network call, no file write, no logger change. The vulnerability scan (OSV and
  EPSS) runs only on an explicit POST.

## Panels and API

`GET /sharpit/api/panels` lists what this build offers and why a panel is unavailable or read-only. The MVP targets
the panels below; trust `/panels` over this table if they ever disagree:

| Panel | API | Notes |
|---|---|---|
| Overview | `GET {api}/overview` | app, Python, activation status and warnings |
| Configuration | `GET {api}/config` | env, `.env`, pydantic-settings and `os.getenv` keys, winning source, masked |
| Mappings | `GET {api}/mappings/flat` | every route of the host app |
| Loggers | `GET {api}/loggers`, `POST {api}/loggers/{name}` | change a level at runtime (write action) |
| Beans | `GET {api}/beans` | dependency providers and their `dependencies` |
| Vulnerabilities | `GET {api}/vulnerabilities`, `POST {api}/vulnerabilities/scan` | installed distributions against OSV, scored with EPSS |
| Live Memory | `GET {api}/live-memory/footprint`, `POST {api}/live-memory/footprint` (`{"enabled": bool}`) | inspect or pause sharpit's capture hooks; status is available over MCP and CLI, while enable/disable are CLI and route actions only |
| MCP server | `GET {api}/mcp-server`, `POST {api}/mcp` | read-only MCP for agents |
| CLI | `GET {api}/cli`, `POST {api}/cli/tools/{tool}` | the same tool catalogue as MCP, plus the 22 action tools (see Actions below), over plain HTTP. The `sharpit` command-line client runs against this endpoint: it supports the advertised tools plus `tools` and `mcp status|enable|disable` (see Command-line client below; `sharpit --help` for usage) |
| Data | `GET {api}/data/repositories`, `GET {api}/data/repositories/{name}` | SQLAlchemy mapped classes: table, primary-key type, relationships. Needs `install(app, models=Base)` and SQLAlchemy 2.0+. MCP: `get_data_repositories` |
| PostgreSQL | `GET {api}/postgresql`, `POST {api}/postgresql/read` | vital signs, sessions, statements, indexes, tables, vacuum, replication, settings. Read only on the POST, in one read-only transaction with statement and lock timeouts, a read budget and row limits; GET returns the last read. MCP: `get_postgresql_report` |
| Java Agent, Code Inventory, Code Paths, Side Effects | `GET {api}/java-agent`, `POST {api}/java-agent/sensors/{id}`, `GET {api}/code-inventory[/changes\|/methods\|/dependencies]`, `GET {api}/code-paths[/route\|/beans\|/requests/{id}\|/probes]`, `POST {api}/code-paths/probes[/{id}/stop]`, `DELETE {api}/code-paths/probes/{id}`, `GET {api}/side-effects[/sensor]` | agent-sensor panels: BootUI's shape, `available: false` with the reason. The `processes` and `files` sensors (`SHARPIT_AGENT_SENSORS`, off by default) feed the runtime journal, not these panels; with them on, `POST {api}/java-agent/sensors/files` switches the files sensor, otherwise it is refused (409) as BootUI refuses it without the agent. MCP: `get_agent_status` |
| Metrics | `GET {api}/metrics`, `GET {api}/metrics/detail` | host Prometheus registry, collected on each read (every host collector runs once); label values and HELP text are masked. MCP and CLI: `get_metrics` / `metrics` |
| AI Framework | `GET {api}/ai/overview`, `GET {api}/ai/chats`, `GET {api}/ai/chats/{spanId}`, `GET {api}/ai/tokens` | GenAI usage from the app's OpenTelemetry span ring. Prompt/completion content is hidden unless `SHARPIT_EXPOSE_VALUES=FULL`. MCP: `get_ai_overview`; CLI: `ai overview` |
| Email | `GET {api}/email`, `GET {api}/email/{id}`, `GET {api}/email/{id}/eml`, `DELETE {api}/email` | outgoing mail captured at `smtplib`/`aiosmtplib` `sendmail`, bounded; secret-shaped text masked unless `SHARPIT_EXPOSE_VALUES=FULL`; DELETE clears (refused on a read-only panel). `SHARPIT_EMAIL_DEV_TRAP=true` captures without connecting or sending. MCP: `get_emails`; CLI: `mail` |

The `sqlalchemy-statistics` panel (BootUI's `hibernate-statistics`; `GET {api}/sqlalchemy-statistics`, MCP
`get_sqlalchemy_statistics`) shows statement counts from SQL Trace's lifetime totals, the slowest statement and N+1
candidates per route. SQLAlchemy reports SQL statements, not ORM sessions or entities, so the Hibernate-only counters
(sessions, flushes, transactions, entity and collection counts) are `null`, each with a reason. It needs SQL Trace, and
reports `statistics.warnings` when SQL Trace recording is paused.

Data rows are listed with `relationships: null` and the reason "Mappers are not configured yet: the app has not run a
query" until the app's first query has configured the mappers. PostgreSQL query text is masked (string, dollar-quoted
and numeric literals; comments dropped) unless `SHARPIT_EXPOSE_VALUES=FULL`. If `pg_stat_statements` is not preloaded,
the statements section is `SKIPPED`. sharpit's own PostgreSQL tests run only against a leased database
(`SHARPIT_TEST_POSTGRES_URL`) and skip without one.

JSON follows BootUI's contract: camelCase keys, every key present (nulls included), epoch milliseconds, no envelope.
Lists page with `offset` and `limit` (clamped to 1000). Errors are `{"error": "..."}`.

## MCP endpoint (for AI agents)

Off by default. Enable with `SHARPIT_MCP_ENABLED=ON`, then point an MCP client that speaks streamable HTTP at
`http://127.0.0.1:8000/sharpit/api/mcp` (POST only). It exposes 51 **read-only** tools and no action tool: an agent cannot change a logger, clear a buffer or start a scan through MCP. The same guard chain applies, so remote agents need the bearer token. Search tools take
`query` and `limit` (capped by `SHARPIT_MCP_MAX_RESULTS`). The names and the read or action split match BootUI 2.3.0
where BootUI has the same tool; the descriptions are in `website/docs/mcp.md`.

- The app: `get_overview` (call it first), `get_config`, `get_profile_diff`, `get_mappings`, `get_beans`, `get_loggers`,
  `get_data_repositories`.
- Requests and errors: `get_live_activity`, `get_request_profile`, `get_http_exchanges`, `get_http_routes`,
  `get_exceptions`, `get_exception_detail`, `get_log_tail`, `get_security_logs`.
- Database: `get_sql_traces`, `get_sql_trace_insights`, `get_sqlalchemy_statistics`, `get_transactions`,
  `get_database_connection_pools`, `get_alembic_migrations`, `get_postgresql_report`, `get_mysql_report`.
- GitHub: `get_github_dashboard` (`github` on the CLI endpoint; local repository identity and cached data; the read never calls GitHub).
- Runtime: `get_health`, `get_threads`, `get_startup_timeline`, `get_scheduled_tasks`, `get_traces`, `get_low_footprint`, `get_metrics`, `get_runtime_insights`, `get_runtime_insight`.
- Agent sessions: `get_copilot_sessions`, `get_claude_code_sessions`.
- AI Framework: `get_ai_overview` (CLI: `ai overview`).
- Email: `get_emails` (CLI: `mail`).
- Pentesting: `get_pentest_report` (CLI: `pentest report`; cached report, never probes).
- Agent sensors: `get_agent_status` (CLI: `agent status`): `NOT_ATTACHED` in this version, which has no agent; the
  `processes` and `files` sensors (`SHARPIT_AGENT_SENSORS`) feed the runtime journal instead. BootUI's code inventory, method probe, and side-effect sensor tools are not
  advertised and answer "Tool not available in this application".
- Advisors and security (a report tool and a per-rule violations tool each, neither starts a scan):
  `get_vulnerabilities_report`; `get_rest_api_report`, `get_rest_api_rule_violations`; `get_security_report`,
  `get_security_rule_violations`; `get_database_advisor_report`, `get_database_advisor_rule_violations`;
  `get_architecture_report`, `get_architecture_rule_violations`; `get_fastapi_report`,
  `get_fastapi_rule_violations`; `get_fastapi_security`.

### Actions (CLI endpoint only, never MCP)

22 action tools change state, call out or scan. They are reachable through `POST {api}/cli/tools/<tool>`
(`SHARPIT_CLI_ENABLED`, on by default), behind the same guard chain; Live Memory controls are also available through its guarded API route, and the CLI endpoint serves every read tool above.
An action is refused when sharpit is read-only (`SHARPIT_READ_ONLY=true`: "sharpit is read-only via SHARPIT_READ_ONLY=true") or its panel is read-only (`SHARPIT_PANELS_<ID>_READ_ONLY=true`: "Panel is read-only via SHARPIT_PANELS_<ID>_READ_ONLY=true"), and when its panel is disabled; a read tool still answers on a read-only panel.

- Scans and reads that call out: `vulnerabilities_scan` (sends package names and versions to OSV.dev), `rest_api_scan`,
  `security_scan`, `database_advisor_scan`, `architecture_scan`, `fastapi_scan`, `postgresql_read`, `mysql_read`, `pentest_scan` (CLI: `pentest scan`; one bounded in-process GET and OPTIONS probe of the host app; the cookie checks read the names and flags of that GET's `Set-Cookie` headers, never their values, and the session checks read the host's `SessionMiddleware` options statically; the evidence is ASGI-only, with no TLS edge, and the Capture panel shows the probe exchange as it shows any host response, the probe's cookie under `FULL`).
- Buffers and recording (sharpit's own in-memory capture only): `clear_exceptions`, `clear_sql_traces`,
  `pause_sql_trace_recording`, `resume_sql_trace_recording`, `clear_transactions`, `pause_transaction_recording`,
  `resume_transaction_recording`, `clear_traces`, `enable_sqlalchemy_statistics`, `enable_low_footprint`,
  `disable_low_footprint` (CLI and guarded API only).
- Agent sensors: `enable_agent_sensor`, `disable_agent_sensor` (switch the `files` sensor when `SHARPIT_AGENT_SENSORS` arms
  one; refused otherwise);
  `start_method_probe` is not advertised.

Live Memory also accepts `POST {api}/live-memory/footprint` with `{"enabled": bool}`; its `get_low_footprint` status tool is on MCP and CLI, while the two action tools are CLI and route only. `SHARPIT_FREE_ON_IDLE_ENABLED` defaults to `true`; `SHARPIT_FREE_ON_IDLE_TIMEOUT` defaults to 300 seconds.

## Command-line client (`sharpit`)

The `sharpit` console script queries a running sharpit application over HTTP from a shell or terminal session without adding dependencies. It is included in the base `sharpit` package.

### Global options

- `--url <url>`: application base URL (default `http://localhost:8000`, env `SHARPIT_URL`).
- `--api-path <path>`: sharpit API path (default `/sharpit/api`, env `SHARPIT_API_PATH`).
- `--token <token>`: bearer token for authentication. While `--token` overrides `SHARPIT_TOKEN`, using `SHARPIT_TOKEN` is recommended to avoid exposing credentials in host process listings (`ps`, Task Manager).
- `--timeout <seconds>`: request timeout in seconds (default `60.0`, accepts `Ns` or `Nms`).
- `--json`: emit raw JSON instead of human-readable text, preserving server bytes except where the token is redacted for safety (recommended for agent consumption).
- `--fail-on <severity>`: gate command exit code on finding severity (`critical`, `high`, `medium`, `low`, `info`) or `insufficient` evidence.

### Command discovery and MCP control

- `sharpit tools`: lists the tools advertised by the running target application.
- `sharpit mcp status`: inspects the current MCP server status and revision.
- `sharpit mcp enable` / `sharpit mcp disable`: switches the MCP server on or off (action; refused on a read-only panel).

### Tool commands and examples

Commands are derived from the tool catalogue:

```bash
# Read application overview
sharpit overview

# Filter configuration
sharpit config -q database

# Run a security scan and fail if high or critical findings exist
sharpit security scan --fail-on high

# Inspect runtime insights and fail if evidence is insufficient
sharpit insights list --fail-on insufficient
```

### Exit codes

Exit codes follow BootUI 2.5.0 (`sharpit.cli.exit_codes.ExitCodes`):

- `0` (`SUCCESS`): command succeeded and findings are below the gate threshold.
- `1` (`ERROR`): client or connection error, HTTP 500, invalid arguments, or gate could not be evaluated; a refused MCP toggle exits 1.
- `2` (`REFUSED`): refused tool action because the endpoint or panel is disabled or the action is denied by a read-only policy (`PANEL_ACCESS_DENIED`). Tool refusals are confirmed by checking the target application before exiting 2.
- `3` (`THRESHOLD`): findings met or exceeded the `--fail-on` severity threshold, or runtime insights evidence was insufficient.

## Running test gates (`pytest --sharpit`)

In addition to running inside the dev console, sharpit provides a pytest plugin to gate CI on runtime findings.

### Running the test plugin

Run tests with `--sharpit`:

```bash
pytest --sharpit --sharpit-report=sharpit-report.json --sharpit-junit=sharpit-junit.xml
```

Key CLI flags:
- `--sharpit-app=module:app`: Point to the ASGI app instance or factory for offline advisors (e.g. `rest-api`).
- `--sharpit-max-queries=N`: Default per-test query budget for the `call` phase.
- `--sharpit-fail-on=SEV`: Minimum advisor severity that fails the run (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`; default `HIGH`).
- `--sharpit-allow-unknown`: Prevent `unknown` status from failing the session.
- `--sharpit-no-advisors`: Run count gates only and skip advisor scans.
- `--sharpit-require-app`: No application found (or several, or one without routes) makes the run `unknown`, as in
  0.3.0. Without it, the `rest-api` advisor is `SKIPPED` and a clean suite passes.
- `--sharpit-verbose` (or `-vv`): List every finding in the terminal `gate counts:`; by default only failing ones are
  listed and advisor notes below the gate are summarised in one line.
- The terminal `swallowed exceptions:` block groups findings by `except` clause and includes a note when a test double
  raised the swallowed exception.
- `--sharpit-report-only`: Run every gate and write the report, but findings fail nothing. Unknown reasons still exit 1.
- `--sharpit-baseline=PATH` / `--sharpit-write-baseline=PATH`: Compare findings with a baseline, or write one.

Every flag except `--sharpit-write-baseline` also has an ini option (`sharpit_require_app`, `sharpit_verbose`,
`sharpit_report_only`, `sharpit_baseline`, ...).

### Finding the application

When no app was installed with `sharpit.install(...)` and no `--sharpit-app` is given, sharpit picks the FastAPI or
Starlette app defined in the project modules the tests already imported. It never imports a module or runs module code
to do this, and ignores installed packages, the standard library, `conftest` and test modules. The summary says which:

```
sharpit: using app myproject.main:app, detected from the modules the tests imported (pass --sharpit-app to choose)
sharpit: several apps found in the modules the tests imported (myproject.admin:app, myproject.main:app); pass --sharpit-app module:attr
sharpit: no application found among the modules the tests imported (conftest, test modules and installed packages are not searched); rest-api skipped (pass --sharpit-app module:attr to assess the same app on any selection; --sharpit-require-app makes a missing app an error instead of a skip)
```

A skipped advisor does not make the session `unknown`; a database driver sharpit cannot trace still does.

An advisor that read the routes it could and met an opaque `app.mount(...)` is `PARTIAL`: the run passes with a
warning that names what was not read and says no finding is not proof there is none; a finding at or above
`--sharpit-fail-on` still fails. Everything else stays `UNKNOWN`: no usable routes plus a limitation, a router or
exception handler sharpit could not read, an errored scan or a rule that threw. An app with no routes and no limitation
is confirmed empty and passes. Lost capture stays `unknown`.

### Report-only mode and baselines

For complete gate behavior, exit statuses and the adoption workflow, see [The safety gate](https://github.com/ffroliva/sharpit/blob/main/docs/pytest-safety-gate.md).

- `--sharpit-report-only`: findings do not fail tests, JUnit cases or the session. The terminal ends with
  a summary of failing tests and status. Report-only relaxes findings, never blindness: any unknown
  reason (including a broken baseline) still exits 1 unless `--sharpit-allow-unknown`.
- With `--sharpit-baseline=PATH` each finding gets `baselineState`: `existing` (listed; never fails), `new` (unlisted;
  gates as usual) or `fixed` (listed, not seen). A count gate above its baselined `observed` count is `new`. On a
  partial run `fixed` is `null` with `fixedReason: "partial run"`. Vulnerability findings are not baselined.
- `--sharpit-write-baseline=PATH` refuses (file not written) a partial run (`-k`, `-m`, node ids, `--lf`, `--deselect`,
  `-x` stopping early, an interrupt, under xdist too) and a run with any unknown reason.
- A missing or malformed baseline is an unknown reason, never sharpit off. Renaming a test makes its findings `new`.
- An explicit dismissal wins over a baseline. INFO findings never fail.

### Reading the report and statuses

The JSON report (`sharpit-report.json`) yields one of three statuses in `.status`:
- `pass`: All gates passed and no advisor was `UNKNOWN`. An advisor with `status: PARTIAL` assessed part of the app; its
  limitation is in `.warnings`.
- `fail`: One or more tests violated a count gate (budget, N+1, swallowed exception), or an advisor failed.
- `unknown`: Capture was incomplete or compromised. By default, this fails the session (exit code 1).

When inspecting an `unknown` or `fail` result, check:
- `.statusReasons`: Explains why the status was assigned.
- `.severityCounts`: Array of counts per severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`).
- `.totals`: Check `unattributedShare` (must be <= 10%) and `queries`.
- `.sources`: Verify that expected sources (`sqlalchemy`, `sqlite3`, `exceptions`) show `attached: true`.
- `.tests[]`: Lists per-test query counts across `setup`, `call`, and `teardown`, detected N+1 queries, and finding fingerprints.
- `.findings[]`: Flat list of all findings with their `fingerprint`, `ruleId`, `target`, and `message`.

### GitHub Action (CI)

The repository root is a composite action (`action.yml`) that runs pytest with sharpit and writes a findings summary to
the job summary. Pin it to a release tag:

```yaml
- uses: ffroliva/sharpit@<release tag>
  with:
    pytest-args: "-q tests/"
    baseline: sharpit-baseline.json
```

Inputs: `pytest-args` (split with Python shlex), `report-only` (default `"true"`: findings are reported, never fail the
build), `baseline`, `fail-on` (lowest severity that fails), `report-path` (default `sharpit-report.json`), `install`
(`pip` installs the pinned sharpit; `none` when your project already depends on it, in which case `python` must be
able to import sharpit) and `runner` (default `python -m pytest`, for example `uv run pytest`). Set `report-only: "false"`
to gate. The pytest exit code is never masked: the summary step runs `if: always()` and only warns if it fails. The
summary is rendered by `python -m sharpit.report summary <report.json>`. On Windows runners `runner` and `pytest-args`
are split in non-POSIX mode so backslashes in paths survive.

### Per-finding dismissal via `sharpit.yml`

Findings have a stable `fingerprint` of the form `<advisor>:<rule_id>:<hash>`.
To dismiss an accepted finding without ignoring the entire rule, add its fingerprint directly to the `dismissedRules:`
list in `<state_dir>/sharpit.yml` (default `.sharpit/sharpit.yml`):

```yaml
dismissedRules:
  - "RAPI-MAP-002"                                            # Dismisses all occurrences of rule RAPI-MAP-002
  - "rest-api:RAPI-MAP-002:a1b2c3d4e5f67890"                  # Dismisses this specific REST API finding
  - "test-runtime:sharpit.n-plus-one:3f9a12c4b5e67890"    # Dismisses this specific N+1 query finding
```

- A rule ID dismisses every finding for that rule.
- A fingerprint dismisses only that exact occurrence.
- The web console UI also provides a "dismiss this finding" action in the REST API details drawer.
- Committing `sharpit.yml` to version control establishes the accepted baseline for CI gates. Commit that file only:
  `identity.key`, beside it, is a local secret and stays out (the `.gitignore` sharpit writes next to it says so). On
  SQLite a fingerprint depends on the key, so a shared baseline needs one `SHARPIT_IDENTITY_KEY` across CI and laptops.

`GET/POST/DELETE {api}/dismissed-findings` keep per-finding dismissals in the same file under `dismissedFindings:`,
next to `dismissedRules:`. POST and DELETE take `{"ruleId": "...", "identity": "...", "note": "optional, at most 200
characters"}` as `application/json`; the identity may contain spaces, and the rule's owning panel must be enabled and
writable. Notes are stored Base64URL-encoded and returned only by `GET` (no MCP tool or CLI command).
`SHARPIT_READ_ONLY=true` refuses the mutations with 403; listing still works. At most 1000 dismissed findings (409
beyond).

A `sharpit.swallowed-exception` finding prints its identity at the end of its message,
`<path>:<scope>:<ExceptionType>#<key>` (the key hashes the clause's `try` body and handler; byte-identical clauses of
one scope end `.<n>/<m>`); paste it as the dismissal's identity. Copy it from the terminal or the JSON report: SARIF
output is masked. It holds no line number, so a line added above the `try` or elsewhere in the function keeps the
dismissal; an edit inside the `try` body or the handler changes the key and brings the finding back, and swapping
clauses or moving a log call between them cannot hand the dismissal to another clause. An identity that cannot be
stored as an entry (over 512 characters) is reported with a fingerprint to list under `dismissedRules`, which covers
one test only. The earlier `<path>:<line>:<ExceptionType>` form no longer dismisses: the finding comes back, and the
report warns with the key of the clause now on that line.

## Common mistakes

| Mistake | Fix |
|---|---|
| Expecting it on under plain `uvicorn app:app` | Add `--reload`, or set `APP_ENV=dev` / `SHARPIT_ENABLED=ON` |
| `SHARPIT_ENABLED=ON` in a deployed environment | Never. Production should set `SHARPIT_ENABLED=OFF` or a `prod` profile |
| `api_path` outside `path` (e.g. `/api/sharpit`) | `install()` raises `ValueError`; keep the API under the console path |
| Reading `/sharpit/api/mcp` with GET | The MCP transport is POST only |
| Setting a keyword and wondering why it is ignored | An env var with the same name wins |
