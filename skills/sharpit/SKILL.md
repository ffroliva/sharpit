---
name: sharpit
version: "0.1"
description: >
  Use when adding sharpit to a FastAPI app, configuring it with SHARPIT_* environment variables, working out why
  /sharpit answers 404, reading the sharpit JSON API, or connecting an AI agent to sharpit's read-only MCP endpoint.
  sharpit is a pre-release MVP: an embedded, local-only developer console for Python apps, ported from BootUI.
---

# sharpit: the local developer console for FastAPI apps

> **0.2.0.** APIs, panels and settings can still change before 1.0.
> The design source is `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md`; when this file and the code
> disagree, the code wins.

sharpit is a Python port of [BootUI](https://github.com/jdubois/boot-ui), the Spring Boot dev console. One call mounts
a console at `/sharpit` and a BootUI-compatible JSON API at `/sharpit/api` inside your own app. It is for **local
development only**: it switches itself off unless it has a reason to be on, and it refuses non-loopback callers.

## Install

Python 3.12+. Runtime dependencies are only `starlette` and `packaging`; FastAPI 0.115+ is the supported host.

```bash
# from a local checkout (no PyPI release yet)
uv add --editable ../sharpit        # or: pip install -e ../sharpit
```

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
| `SHARPIT_STATE_DIR` | `state_dir` | `.sharpit` | where dismissals are stored (created on first write) |
| `SHARPIT_VULNERABILITIES_OSV_ENABLED` | `vulnerabilities_osv_enabled` | `true` | allow the OSV scan |
| `SHARPIT_MCP_ENABLED` | `mcp_enabled` | `OFF` | turn on the read-only MCP endpoint |
| `SHARPIT_PANELS_<ID>_ENABLED` / `_READ_ONLY` | `panels={"<id>": {...}}` | on / off | per-panel switches, e.g. `SHARPIT_PANELS_LOGGERS_READ_ONLY=true` |

The full list (`SHARPIT_MCP_*`, `SHARPIT_CLI_*`, `SHARPIT_VULNERABILITIES_*`, `SHARPIT_TRUST_CONTAINER_GATEWAY`,
`SHARPIT_CONFIG_SCAN`, ...) is in the README settings table and `src/sharpit/settings.py`. Durations accept `10s`, `500ms` or a bare number of seconds.

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
| MCP server | `GET {api}/mcp-server`, `POST {api}/mcp` | read-only MCP for agents |
| CLI | `GET {api}/cli`, `POST {api}/cli/tools/{tool}` | the same tool catalogue as MCP, plus the scan, over plain HTTP. The `sharpit` command-line binary is planned, not shipped |

JSON follows BootUI's contract: camelCase keys, every key present (nulls included), epoch milliseconds, no envelope.
Lists page with `offset` and `limit` (clamped to 1000). Errors are `{"error": "..."}`.

## MCP endpoint (for AI agents)

Off by default. Enable with `SHARPIT_MCP_ENABLED=ON`, then point an MCP client that speaks streamable HTTP at
`http://127.0.0.1:8000/sharpit/api/mcp` (POST only). It exposes **read-only** tools: `get_overview`, `get_config`,
`get_mappings`, `get_loggers`, `get_beans`, `get_vulnerabilities_report`. There is no action tool: an agent cannot
change a logger or start a scan through MCP. The same guard chain applies, so remote agents need the bearer token.

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

### Reading the report and statuses

The JSON report (`sharpit-report.json`) yields one of three statuses in `.status`:
- `pass`: All gates passed and advisors completed with full coverage.
- `fail`: One or more tests violated a count gate (budget, N+1, swallowed exception), or an advisor failed.
- `unknown`: Capture was incomplete or compromised. By default, this fails the session (exit code 1).

When inspecting an `unknown` or `fail` result, check:
- `.statusReasons`: Explains why the status was assigned.
- `.severityCounts`: Array of counts per severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`).
- `.totals`: Check `unattributedShare` (must be <= 10%) and `queries`.
- `.sources`: Verify that expected sources (`sqlalchemy`, `sqlite3`, `exceptions`) show `attached: true`.
- `.tests[]`: Lists per-test query counts across `setup`, `call`, and `teardown`, detected N+1 queries, and finding fingerprints.
- `.findings[]`: Flat list of all findings with their `fingerprint`, `ruleId`, `target`, and `message`.

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
- Committing `sharpit.yml` to version control establishes the accepted baseline for CI gates.

## Common mistakes

| Mistake | Fix |
|---|---|
| Expecting it on under plain `uvicorn app:app` | Add `--reload`, or set `APP_ENV=dev` / `SHARPIT_ENABLED=ON` |
| `SHARPIT_ENABLED=ON` in a deployed environment | Never. Production should set `SHARPIT_ENABLED=OFF` or a `prod` profile |
| `api_path` outside `path` (e.g. `/api/sharpit`) | `install()` raises `ValueError`; keep the API under the console path |
| Reading `/sharpit/api/mcp` with GET | The MCP transport is POST only |
| Setting a keyword and wondering why it is ignored | An env var with the same name wins |
