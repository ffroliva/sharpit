# sharpit

An embedded, local-only developer console for FastAPI apps. One call mounts a web console at `/sharpit` and a
JSON API at `/sharpit/api` inside your own app, so a running service becomes understandable in minutes: its
configuration and where each value came from, every route, the dependency providers, loggers you can retune live,
and a vulnerability scan of the installed packages.

sharpit is a Python/FastAPI port of [BootUI](https://github.com/jdubois/boot-ui) by Julien Dubois (Apache-2.0), the
Spring Boot developer console. It ports BootUI's design goals, JSON contract and test cases; the UI is new.

![sharpit overview](https://raw.githubusercontent.com/ffroliva/sharpit/master/ui/tests/e2e/screenshots/overview-light.png)

> **Status: alpha (0.1.0, FastAPI only).** Django and Flask are not supported. See [CHANGELOG.md](https://github.com/ffroliva/sharpit/blob/master/CHANGELOG.md).

## Install

sharpit is not on PyPI yet. Until 0.1.0 is published, install it from git:

```bash
pip install "sharpit @ git+https://github.com/ffroliva/sharpit.git"
# or
uv add "sharpit @ git+https://github.com/ffroliva/sharpit.git"
```

Once published, it is `pip install sharpit` or `uv add sharpit`.

Python 3.12+. Runtime dependencies are only `starlette>=0.40` and `packaging>=23`. Optional extras:

| Extra | Adds | Why |
|---|---|---|
| `sharpit[fastapi]` | `fastapi>=0.115` | the supported host |
| `sharpit[settings]` | `pydantic-settings>=2.4` | the Config panel shows which source each value came from |

## Quickstart

```python
from fastapi import FastAPI
import sharpit

app = FastAPI()
sharpit.install(app)  # mounts /sharpit and /sharpit/api
```

Run it **with a dev signal** and open <http://127.0.0.1:8000/sharpit/>:

```bash
fastapi dev app.py          # or: uvicorn app:app --reload
```

To show where your own settings values come from, pass the pydantic-settings instance (or a list of them):
`sharpit.install(app, settings=Settings())`. Other options are keyword arguments, see the table below.

### Why does a plain `uvicorn app:app` give 404?

sharpit is a development tool, so it fails closed. With no reason to be on, every path under `/sharpit` answers the
host app's own 404 and nothing reveals that sharpit is installed. It switches on when the first of these applies:

1. `SHARPIT_ENABLED=ON` (always on; `OFF` always off).
2. An active profile is in `SHARPIT_ENABLED_PROFILES` (default `dev,local,development`). Profiles are read from the
   variables in `SHARPIT_PROFILE_VARS` (default `SHARPIT_PROFILES,APP_ENV,ENVIRONMENT`), so `APP_ENV=dev` works.
3. A reloading dev server is detected from the command line: `uvicorn ... --reload` or `fastapi dev`.

A profile in `SHARPIT_DISABLED_PROFILES` (default `prod,production`) wins over 2 and 3 and switches it off.
`uvicorn.run(..., reload=True)` from a script is not detected: set `APP_ENV=dev` or `SHARPIT_ENABLED=ON`.

When sharpit was asked for but ended up off, it logs the reason at WARNING; an explicit `OFF` or nothing asking for it
logs at INFO. When on, it prints a banner on stderr and `GET /sharpit/api/overview` reports the reason under
`activation`.

## Panels

| Panel | What it shows |
|---|---|
| Overview | app, Python and package versions, active profiles, activation reason and warnings |
| Configuration | environment, `.env` files, pydantic-settings and `os.getenv` keys, the winning source of each value, masked |
| Mappings | every route of the host app |
| Loggers | logger tree with levels you can change at runtime |
| Beans | dependency providers, middleware and lifespan, with their dependencies |
| Vulnerabilities | installed distributions checked against [OSV](https://osv.dev) and scored with EPSS, on explicit request |
| MCP server | status and switch for the read-only MCP endpoint |
| CLI | the same tool catalogue over plain HTTP |

`GET /sharpit/api/panels` lists what this build offers and why a panel is unavailable or read-only.

![sharpit configuration panel](https://raw.githubusercontent.com/ffroliva/sharpit/master/ui/tests/e2e/screenshots/config-light.png)

## MCP for AI agents

The MCP endpoint is **off by default**. Enable it with `SHARPIT_MCP_ENABLED=ON` (or `install(app, mcp_enabled="ON")`,
or the switch in the MCP Server panel), then point a streamable-HTTP MCP client at
`http://127.0.0.1:8000/sharpit/api/mcp` (POST only). It exposes read-only tools: `get_overview`, `get_config`,
`get_mappings`, `get_loggers`, `get_beans`, `get_vulnerabilities_report`. There is no action tool, so an agent cannot
change a logger or start a scan through MCP. The same guard chain and masking apply to it as to the UI.

An agent skill that teaches an AI assistant to install and use sharpit is in
[`skills/sharpit`](https://github.com/ffroliva/sharpit/tree/master/skills/sharpit). The `sharpit` command-line client
is planned and not shipped; the `/sharpit/api/cli` HTTP endpoint is.

## Settings

Every setting is an environment variable and an `install()` keyword. **The environment variable wins over the
keyword**, so a deployment can always force `SHARPIT_ENABLED=OFF`. An empty value counts as unset. The name rule is
`SHARPIT_` + the keyword in upper case. An invalid value never raises: that setting takes its fail-safe value
(disabled, read-only, masked) and a warning is recorded and shown on the Overview panel. Only an unusable `path` or
`api_path` raises `ValueError`, and an unknown keyword raises `TypeError` with a suggestion. Booleans accept
`true/false/yes/no/on/off/1/0`; durations accept `10s`, `500ms` or a bare number of seconds.

| Env var | Keyword | Default | Meaning |
|---|---|---|---|
| `SHARPIT_ENABLED` | `enabled` | `AUTO` | `ON`, `OFF` or `AUTO` (use the rules above) |
| `SHARPIT_ENABLED_PROFILES` | `enabled_profiles` | `dev,local,development` | profiles that turn it on |
| `SHARPIT_DISABLED_PROFILES` | `disabled_profiles` | `prod,production` | profiles that turn it off |
| `SHARPIT_PROFILE_VARS` | `profile_vars` | `SHARPIT_PROFILES,APP_ENV,ENVIRONMENT` | variables the profiles are read from |
| `SHARPIT_PATH` | `path` | `/sharpit` | console mount point |
| `SHARPIT_API_PATH` | `api_path` | `/sharpit/api` | must sit under `path` |
| `SHARPIT_ALLOW_NON_LOCALHOST` | `allow_non_localhost` | `false` | accept non-loopback callers (token required) |
| `SHARPIT_ALLOWED_HOSTS` | `allowed_hosts` | empty | extra `Host` names to accept |
| `SHARPIT_TRUSTED_PROXIES` | `trusted_proxies` | empty | proxy addresses or ranges whose forwarded headers are accepted |
| `SHARPIT_TRUST_CONTAINER_GATEWAY` | `trust_container_gateway` | `OFF` | `AUTO` trusts the detected container gateway |
| `SHARPIT_AUTHENTICATION_TOKEN` | `authentication_token` | generated | bearer token for untrusted sources |
| `SHARPIT_READ_ONLY` | `read_only` | `false` | refuse every write action |
| `SHARPIT_PANELS_<ID>_ENABLED` | `panels={"<id>": {"enabled": ...}}` | `true` | per-panel switch |
| `SHARPIT_PANELS_<ID>_READ_ONLY` | `panels={"<id>": {"read_only": ...}}` | `false` | per-panel read-only; `<ID>` is the panel id in capitals with `-` as `_`: `OVERVIEW`, `CONFIG`, `MAPPINGS`, `LOGGERS`, `BEANS`, `VULNERABILITIES`, `MCP_SERVER`, `CLI` |
| `SHARPIT_EXPOSE_VALUES` | `expose_values` | `MASKED` | `MASKED`, `METADATA_ONLY` or `FULL` (FULL logs a warning) |
| `SHARPIT_MASK_SECRETS` | `mask_secrets` | `true` | mask secret-looking names and values |
| `SHARPIT_SHOW_BANNER` | `show_banner` | `true` | print the startup banner to stderr |
| `SHARPIT_STATE_DIR` | `state_dir` | `.sharpit` | where dismissed vulnerability rules are stored (`sharpit.yml`, created on first write) |
| `SHARPIT_CONFIG_SCAN` | `config_scan` | `true` | `true` scans your top-level package for `os.getenv` keys, `false` disables, or a list of package names |
| `SHARPIT_VULNERABILITIES_OSV_ENABLED` | `vulnerabilities_osv_enabled` | `true` | allow the OSV scan |
| `SHARPIT_VULNERABILITIES_OSV_BASE_URI` | `vulnerabilities_osv_base_uri` | `https://api.osv.dev` | OSV endpoint |
| `SHARPIT_VULNERABILITIES_EPSS_ENABLED` | `vulnerabilities_epss_enabled` | `true` | enrich findings with EPSS scores |
| `SHARPIT_VULNERABILITIES_EPSS_BASE_URI` | `vulnerabilities_epss_base_uri` | `https://api.first.org` | EPSS endpoint |
| `SHARPIT_VULNERABILITIES_REQUEST_TIMEOUT` | `vulnerabilities_request_timeout` | `10s` | per-request timeout |
| `SHARPIT_VULNERABILITIES_MAX_PACKAGES` | `vulnerabilities_max_packages` | `500` | packages sent to OSV |
| `SHARPIT_VULNERABILITIES_MAX_ADVISORIES` | `vulnerabilities_max_advisories` | `200` | advisories kept per scan |
| `SHARPIT_MCP_ENABLED` | `mcp_enabled` | `OFF` | `ON` enables the MCP endpoint |
| `SHARPIT_MCP_MAX_RESULTS` | `mcp_max_results` | `200` | cap on items per tool call |
| `SHARPIT_MCP_MAX_PAYLOAD_BYTES` | `mcp_max_payload_bytes` | `1048576` | largest request body |
| `SHARPIT_MCP_MAX_CONCURRENT_CALLS` | `mcp_max_concurrent_calls` | `20` | parallel tool calls |
| `SHARPIT_MCP_EXECUTION_TIMEOUT` | `mcp_execution_timeout` | `30s` | per tool call |
| `SHARPIT_MCP_MAX_RESPONSE_BYTES` | `mcp_max_response_bytes` | `4194304` | largest response body |
| `SHARPIT_CLI_ENABLED` | `cli_enabled` | `true` | enable the `/sharpit/api/cli` endpoint |
| `SHARPIT_CLI_MAX_RESULTS` | `cli_max_results` | `200` | cap on items per call |
| `SHARPIT_CLI_MAX_CONCURRENT_CALLS` | `cli_max_concurrent_calls` | `20` | parallel calls |
| `SHARPIT_CLI_EXECUTION_TIMEOUT` | `cli_execution_timeout` | `30s` | per call |

## Safety model

- **Local only.** Requests must come from a loopback address with a loopback or allow-listed `Host`. If `Forwarded`,
  `X-Forwarded-For` or `X-Real-IP` is present and no trusted proxy is configured, the caller counts as remote.
- **Cross-site requests are refused** on every method (`Sec-Fetch-Site: cross-site`, or, on API paths, an `Origin` that differs from
  the request's full origin: scheme, host and port; other paths compare the host), even when your app has `CORSMiddleware(allow_origins=["*"])`.
- **Remote access needs a token.** `SHARPIT_ALLOW_NON_LOCALHOST=true`,
  `SHARPIT_TRUST_CONTAINER_GATEWAY=AUTO` or a trusted proxy admits untrusted sources, and
  those must present the token as `Authorization: Bearer <token>`. Set `SHARPIT_AUTHENTICATION_TOKEN`; otherwise a
  token is generated per process and printed once to stderr. A browser trades it for an `HttpOnly; SameSite=Strict`
  cookie through `POST /sharpit/api/auth/session`.
- **Secrets are masked** (`******`) in names, values, defaults, errors and MCP output, including pydantic `SecretStr`.
  sharpit masks any URL that carries userinfo, including a user name with no password
  (`https://<key>@o1.ingest.sentry.io/1`, `redis://admin@cache:6379`), because DSN-style keys sit in that slot. A
  harmless user name in a URL is shown as `******` too. That is intentional: sharpit errs towards hiding.
- **GET has no side effects.** No network call, no file write, no logger change. The vulnerability scan (OSV and EPSS)
  runs only on an explicit POST.
- **Fails closed.** When off, or in a `prod`/`production` profile (unless `SHARPIT_ENABLED=ON` forces it on, with a warning), the whole mount answers 404.

### Behind a TLS-terminating proxy

The Origin check compares scheme, host and port. If a proxy terminates TLS and forwards plain HTTP, uvicorn must see
the original scheme or browser POSTs from the UI are rejected. Start uvicorn with `--proxy-headers` and
`--forwarded-allow-ips` (or set `FORWARDED_ALLOW_IPS`) to the proxy's address, and add that address to
`SHARPIT_TRUSTED_PROXIES`.

### Multiple workers and `--reload`

sharpit keeps its state in the process that serves the request. With `uvicorn --workers N`, gunicorn or `--reload`:

- **Token.** When `SHARPIT_ALLOW_NON_LOCALHOST=true` and no token is configured, each process generates its own token,
  so a token printed by one worker is rejected by the others and a reload invalidates the browser session. Set
  `SHARPIT_AUTHENTICATION_TOKEN` to a fixed value in these setups.
- **MCP switch, logger levels, scan cache.** The MCP on/off switch, the last scan result and logger levels changed in
  the panel live in memory per process, so each worker has its own. Dismissed vulnerability rules are shared because
  they live in `sharpit.yml`.

For a dev tool, the simplest setup is one worker.

## Deviations from BootUI

sharpit follows BootUI's JSON contract and keeps its guard and masking rules, with deliberate differences (a stricter
cross-site check, Python-specific activation, a new UI, deferred features). The log is section 14 of the
[design spec](https://github.com/ffroliva/sharpit/blob/master/docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md).

## License

Apache License 2.0. See [LICENSE](https://github.com/ffroliva/sharpit/blob/master/LICENSE) and [NOTICE](https://github.com/ffroliva/sharpit/blob/master/NOTICE). sharpit is derived from
[BootUI](https://github.com/jdubois/boot-ui), Copyright Julien Dubois.
