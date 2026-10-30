# sharpit MVP — design (REA + Replica port of BootUI to Python/FastAPI)

Status: draft for LLM-council review · 2026-10-30 · owner: Flavio Oliva · coordinator: Claude

## 1. Intent

sharpit is a **port, not a new product**. BootUI (github.com/jdubois/boot-ui, Apache-2.0) already works for Spring
Boot and Quarkus: an embedded, local-only developer console that makes a running application understandable in
minutes, for humans (browser) and AI agents (MCP, CLI). sharpit reverse-engineers that proven design and adapts it
to Python, FastAPI first, framework-neutral underneath.

**Method.** The owner named two tools:
- **REA** (Reverse Engineer Anything, `C:\development\github\rea`) supplies runtime evidence. BootUI's sample app was
  run locally, its UI walked with Playwright, the traffic recorded as a HAR and inspected with REA. The golden
  responses become sharpit's conformance fixtures.
- **Replica** (`C:\development\github\replica-skill`) supplies the process: recon (`replica/recon.md`,
  `replica/features.csv`), architect (this spec), build, test, and diff (`parity.py`, score in the final report).
  Its brand/launch/deploy/entrepreneur steps are out of scope.

**Rule for every builder: when in doubt, do what BootUI does.** Sources of truth, in order:
1. `docs/reference/BOOTUI-CONTRACT-MVP.md`: the contract extracted from BootUI's DTOs, engine, Vue client and
   conformance catalog, with source citations.
2. Golden runtime responses (sanitised fixtures under `tests/fixtures/bootui/`).
3. BootUI source at `C:\development\github\boot-ui` (read-only).

Any deviation goes in the deviation log (§13) with a reason. Unlogged deviations are bugs.

Why: the owner's main projects (KliperMedia, gflow-cli) are Python, and nothing in the Python ecosystem combines the
whole-app runtime view, advisors and a safe agent surface (`docs/reference/BOOTUI-PYTHON-MAPPING.md`). The closest,
Tidewave, gives agents code `eval`; sharpit never will.

## 2. Goals (MVP), each traced to features.csv

| # | Goal | Contract § |
|---|---|---|
| G1 | Activation and request guard chain, identical semantics, Python signals | §10, §1 |
| G2 | Panel registry `GET {api}/panels`, `platform: "fastapi"` | §1 |
| G3 | Overview `GET {api}/overview` incl. `activation` | §2 |
| G4 | Config `GET {api}/config` with sources in precedence order, winning source, masking, filters, paging | §3 |
| G5 | Mappings `GET {api}/mappings/flat` with paging | §4 |
| G6 | Loggers `GET {api}/loggers` and `POST {api}/loggers/{name}` | §5 |
| G7 | Beans `GET {api}/beans` incl. `dependencies` so the UI builds the dependency graph | §6 |
| G8 | Vulnerabilities: GET inventory/cached report (no network), POST scan (OSV, EPSS, caps, single-flight), dismissal | §8 |
| G9 | MCP server, opt-in, JSON-RPC at `{api}/mcp`, MVP tool set, caps and error codes; `{api}/mcp-server` status | §9 |
| G10 | CLI endpoint `{api}/cli`, `{api}/cli/tools/{tool}` + `sharpit` console script | §11 |
| G11 | New web UI at `/sharpit` consuming the contract | — |
| G12 | `pip install sharpit` + `sharpit.install(app)` | — |
| G13 | Dogfood: KliperMedia runs locally with sharpit enabled | — |

Defaults: `path=/sharpit`, `api_path=/sharpit/api` (`{api}` above).

## 3. Non-goals (MVP)

Django/Flask adapters (the engine is built for them; next), gflow-cli "run and report" mode, config overrides
(they write files), health, profile diff, conditions, every other BootUI panel, a PyPI release (0.0.1 placeholder
already reserves the name), Trusted Publishing setup.

## 4. Anti-goals

- A secret leaves the process unmasked via API, UI, MCP, CLI, logs or error text.
- sharpit is reachable in production or from a non-loopback source without an explicit override.
- Any GET performs a network call, a scan or a mutation.
- Any code execution surface (`eval`, `exec`, dynamic import from input, shell).
- Work done on requests that are not under sharpit's mounts; more than ~50 ms added to app startup.
- The UI looks like BootUI's.

## 5. Constraints

- Python ≥ 3.12 (KliperMedia is 3.14; CI matrix 3.12–3.14). Host: FastAPI ≥ 0.115 / Starlette.
- Core engine: **no hard third-party dependency**; OSV/EPSS through stdlib `urllib` in a worker thread with
  timeouts; `packaging` is allowed (already in every pip environment) for version comparison. MCP is implemented
  directly on the JSON-RPC contract in §9 (no `mcp` SDK dependency, so the shapes and caps match BootUI exactly).
- License Apache-2.0; `NOTICE` credits BootUI for the ported design and contract.
- Tooling: uv, ruff, pyright (strict for `src/sharpit`), pytest. Branch `mvp` on `ffroliva/sharpit`; never merged
  or published by the agents.
- UI is prebuilt into `src/sharpit/ui/static/` and shipped in the wheel. End users never need Node.

## 6. Architecture (BootUI's engine/adapter seam)

```
src/sharpit/
  __init__.py        install(app, **options), __version__
  settings.py        SharpitSettings: every option, read from kwargs then SHARPIT_* env vars (BootUI property 1:1)
  engine/
    activation.py    ActivationDecision (contract §10) — pure function of settings + signals
    guard.py         LocalhostGuard.decide, token check, panel access — pure, framework-free
    headers.py       security headers
    masking.py       name patterns, value detectors, URL redaction, exposure modes
    paging.py        PagedList / PageMetadata semantics
    panels.py        panel registry
    singleflight.py  single-flight actions → 409 body
    collectors/      overview, config (sources), loggers, vulnerabilities (OSV/EPSS clients, cache, dismissals)
    spi.py           AppIntrospector protocol: routes(), beans(), app_info(), server_info(), dev_signal()
    tools.py         the tool catalogue shared by MCP and CLI (name, schema, panel, action, handler)
    mcp.py           JSON-RPC dispatcher (transport-free)
  fastapi/
    adapter.py       install(): mount Starlette sub-app at path; guard chain as the sub-app's middleware only
    introspector.py  FastAPI AppIntrospector (routes, dependant tree, middleware, routers, dependency_overrides)
    signals.py       dev-server signal detection
  cli/main.py        `sharpit` console script (stdlib urllib client)
  ui/static/         built UI
ui/                  UI source (Svelte 5 + Vite + TypeScript)
```

`install(app)` decides activation once at call time. Inactive: mounts a sub-app that answers 404 for every path
under `path` (contract: nothing reveals sharpit exists) and logs one line. Active: mounts the console and API, and
prints the banner (`show_banner`). The guard runs only inside the mounted sub-app, never as global middleware.

## 7. Activation and safety (G1) — contract §10 mapped to Python

Settings (env var ← BootUI property), defaults identical:
`SHARPIT_ENABLED` (AUTO|ON|OFF, also true/yes/false/no; anything else → disabled with BootUI's reason text),
`SHARPIT_ENABLED_PROFILES` (`dev,local`), `SHARPIT_DISABLED_PROFILES` (`prod,production`), `SHARPIT_PATH`,
`SHARPIT_API_PATH`, `SHARPIT_ALLOW_NON_LOCALHOST`, `SHARPIT_ALLOWED_HOSTS`, `SHARPIT_TRUSTED_PROXIES`,
`SHARPIT_TRUST_CONTAINER_GATEWAY`, `SHARPIT_AUTHENTICATION_TOKEN`, `SHARPIT_READ_ONLY`,
`SHARPIT_PANELS_<ID>_ENABLED` / `_READ_ONLY`, `SHARPIT_EXPOSE_VALUES`, `SHARPIT_MASK_SECRETS`,
`SHARPIT_SHOW_BANNER`, `SHARPIT_VULNERABILITIES_*`, `SHARPIT_MCP_*`, `SHARPIT_CLI_*`, `SHARPIT_STATE_DIR`
(overrides-file dir equivalent, default `.sharpit/`). The same names are accepted as `install()` keyword arguments.

**Active profiles** (Spring's concept, adapted): `SHARPIT_PROFILES` if set, else the first of `APP_ENV`, `ENV`,
`ENVIRONMENT` that is set (comma-separated allowed). There is no fallback default profile: the runtime capture
proved BootUI ignores Spring's fallback `default` profile, so sharpit has none.

**Decision order** (first match wins, reasons verbatim with "BootUI"→"sharpit" and property→env names):
disabled-profile (ON → enabled with warning) → OFF → ON → enabled-profile → **dev-server signal** → disabled.

**Dev-server signal** (DevTools equivalent): true only for a reloading development server. uvicorn's reload child
(started by `--reload` or `uvicorn.run(..., reload=True)`, distinguishable from `--workers N`) or `fastapi dev`.
The detection must be **conservative**: if it cannot tell reload from workers, it says no. The builder writes a
test per case. Reason text: `"Enabled because a reloading development server was detected (<which>)"`.

**Request guard chain** on every request under the mounts, in BootUI's order: security headers → source check
(loopback, trusted proxies CIDR, container gateway rules) → Host check (always on) → cross-site write check
(always on) → token check (only for untrusted sources; `POST {api}/auth/session` sets `SHARPIT_SESSION` cookie) →
panel access (global read-only, per-panel enabled/read-only). Error bodies, status codes and messages exactly as
contract §1. No XSRF cookie (JVM-only).

**Masking**: BootUI's name patterns and value detectors verbatim (contract §3), exposure modes
MASKED/METADATA_ONLY/FULL, applied in one place (`engine/masking.py`) and used by config, MCP, CLI and error paths.

## 8. Panels (G2–G8): Python sources for each contract field

The JSON shapes are the contract's. Field-name changes are not allowed. Java-specific keys keep their names and carry
the nearest Python value (logged in §13).

- **Registry**: MVP panels `overview, config, mappings, loggers, beans, vulnerabilities, mcp-server, cli`, with
  titles and actionCapable flags as in the contract. Deferred panels are not listed.
- **Overview**: `bootUiVersion` → sharpit version; `applicationName` ← FastAPI `title` (BootUI default
  `"application"`); `frameworkName` `"FastAPI"`, `frameworkVersion` ← installed fastapi; `javaVersion` ← Python
  version string; `javaVendor` ← implementation (+ " (free-threaded)" when applicable); `activeProfiles`;
  `defaultProfiles` `[]`; `webApplicationType` `"ASGI"`; `serverPort` ← the bound port when known, else `null`;
  `contextPath` ← ASGI `root_path` or null; `startupTimeMillis` ← time from process start to `install()`/lifespan
  start; `activation`; `openApiUrl` ← `app.docs_url` when enabled.
- **Config** sources, in precedence order (first defining source wins, as in Spring):
  1. each registered pydantic-settings instance (`install(app, settings=[...])`): one source per instance,
     values from the instance, `description`/`defaultValue` from `Field` metadata;
  2. `systemEnvironment` (`os.environ`; the name kept for parity);
  3. each `.env` file loaded or present in the working directory (`dotenv: <path>`);
  4. `getenv defaults (static)`: an AST scan of the app's own package (the module that defines the app, its top
     package) for `os.getenv`/`os.environ.get`/`os.environ[...]` with literal keys, giving each key's in-code
     default and `file:line` as `description`. This is what makes the panel useful on KliperMedia (79 keys).
  `propertySuggestions` = keys known from sources 1 and 4 that no source sets. `overrideCount` = 0. `q` relaxed
  matching as BootUI (`MY_PROP` ≡ `my-prop` ≡ `myProp`).
- **Mappings flat**: every route in `app.routes`, recursing into mounts and routers: method(s), path, handler
  `module:qualname`, plus the remaining contract fields from the nearest FastAPI attribute.
- **Loggers**: `logging.root.manager.loggerDict` + root; configured and effective levels; levels list as the
  contract; POST validates the level name with BootUI's 400 behaviour; runtime only.
- **Beans**: one entry per dependency provider: every callable in any route's `dependant` tree, plus each router,
  middleware class, lifespan handler and `dependency_overrides` entry. `dependencies` = names of the sub-dependencies
  (names must match other beans' names, because the UI builds the graph client-side). `classification`
  follows the contract enum (application vs framework, by module origin).
- **Vulnerabilities**: inventory ← `importlib.metadata.distributions()`. GET returns the cached report or the
  inventory, with no network. POST `{api}/vulnerabilities/scan` runs single-flight: OSV `querybatch` (ecosystem
  `PyPI`, normalised names) with `max_packages` / `max_advisories` / timeouts, detail fetch, severity from CVSS as
  in BootUI, EPSS enrichment (failure never drops OSV results), fix availability via `packaging` versions, BootUI's
  ordering. Dismissals persist to `{state_dir}/sharpit.yml` with the same semantics as BootUI's `boot-ui.yml`.
  The cache lives in memory and is reset at restart, as in BootUI.

## 9. MCP and CLI (G9, G10)

One shared tool catalogue (`engine/tools.py`): `get_overview, get_config, get_mappings, get_loggers, get_beans,
get_vulnerabilities_report, vulnerabilities_scan` with BootUI's names, input schemas, caps (`max_results`,
`max_payload_bytes`, `max_concurrent_calls`, `execution_timeout`, `max_response_bytes`) and error codes
(-32001/-32002/-32003, 413). MCP: JSON-RPC 2.0 over streamable HTTP at `{api}/mcp`, POST-only, methods and
`MCP-Protocol-Version` handling as contract §9, `SHARPIT_MCP_ENABLED` default OFF (only ON exposes it).
`get_*` tools never scan. `vulnerabilities_scan` is the only action tool and is refused when read-only. CLI endpoint and console
script: commands, options (`--url` default `http://localhost:8000` or `$SHARPIT_URL`, `--token`/`$SHARPIT_TOKEN`,
`--json`, `--timeout`, `--no-color`, `--verbose`, `--query/--limit/--offset/--scan-id`), status mapping and exit
codes 0/1/2/3 exactly as contract §11. No update check.

## 10. UI (G11)

The contract and the flows (recon S00–S07, F01–F05) come from BootUI. The **look and feel is new**. Coordinator's
direction: a calm, dense, keyboard-first console. Command palette (Ctrl/Cmd+K) jumps to any panel, logger or config
key; a left rail built from the registry (unavailable and read-only states shown with reasons); tables with instant
filter and server paging (page 200, like BootUI); config grouped by source with the winning source highlighted;
dependency graph as an interactive node-link view with focus mode; light and dark themes; one accent colour,
monospace for values; no marketing chrome. Stack: Svelte 5 + Vite + TypeScript, CSP-compatible (no inline script,
no eval), relative `api/...` URLs as BootUI does. Built with the `impeccable`/`frontend-design` skills. Accessibility:
keyboard-reachable, WCAG AA contrast, reduced motion. Verified in a real browser with screenshots for the report.

## 11. Testing

- **Conformance**: sanitised golden responses captured from BootUI (env-specific values stripped) → per-endpoint
  shape tests (keys, types, enums, nullability) that sharpit must pass, minus logged deviations.
- **Safe mode**: one test per decision-table row and per guard rule, including fail-closed and the
  "inactive → 404 everywhere" rule.
- **No-side-effect rule**: every GET endpoint and every `get_*` tool runs under a socket/urllib block and a mutation
  spy, and must pass without a network call.
- **Masking corpus** asserted across API, MCP and CLI outputs.
- OSV/EPSS with recorded responses (no live network in tests).
- Example app `examples/fastapi_sample/` exercising every panel; Starlette `TestClient` end to end.
- UI: vitest for logic, Playwright smoke over the example app.
- CI: GitHub Actions, Python 3.12–3.14, ruff + pyright + pytest + UI build + check that the built UI is committed.
- **Parity**: `replica/features.csv` updated as features land; `parity.py` score in the morning report.

## 12. Dogfooding (G13)

KliperMedia (`C:\development\github\klipermedia`, FastAPI, 3.14, uv): a **local-only** worktree and branch, with sharpit
installed editable from the sharpit worktree and `sharpit.install(app)` added in
`kliper.adapters.web.fastapi_app`. Never pushed. Coexists with its `TrustedHostMiddleware`. Done = it starts with
its normal local command (`uvicorn ... reload=True` → dev signal), `/sharpit` shows real data in every MVP panel, a
secret-bearing variable is masked, and a vulnerability scan runs on demand. Findings go in the morning report.

## 13. Deviation log

| BootUI | sharpit | Reason |
|---|---|---|
| `/bootui`, `/bootui/api`, `bootui.*` properties | `/sharpit`, `/sharpit/api`, `SHARPIT_*` env + `install()` kwargs | product name; Python configures through env |
| Spring profiles incl. fallback default | `SHARPIT_PROFILES` / `APP_ENV`/`ENV`/`ENVIRONMENT`; no fallback | no profile concept in Python |
| DevTools on classpath | reloading dev-server signal (conservative) | no DevTools |
| XSRF cookie priming | dropped; Origin/Sec-Fetch-Site check kept | JVM/Spring Security only |
| `platform` spring-boot/quarkus | `fastapi` | framework |
| `javaVersion`, `javaVendor`, `webApplicationType` | same keys, Python values, `ASGI` | keep contract keys |
| Spring property sources | pydantic-settings, environ, .env, static getenv discovery | no single Environment in Python |
| config metadata json | pydantic `Field` metadata + getenv defaults | Python equivalent |
| beans / application context | FastAPI dependency providers, routers, middleware | no IoC container |
| Maven coordinates and ordering | PyPI distributions, `packaging` | packaging ecosystem |
| `.bootui/` and `boot-ui.yml` | `.sharpit/` and `sharpit.yml` | product name |
| Vue UI | Svelte UI, same contract | owner wants a new look |
| uncaught validation → host 500 | `400 {"error"}` everywhere | contract ambiguity #1, consistency |

## 14. Left to the builder

Internal structure inside each module, caching details, UI component structure and visual details within §10, CLI
table formatting, fixture sanitisation tooling.

## 15. Coordinator's calls (owner to check in the morning)

1. "REA" = the REA tool for runtime evidence + Replica for the process (owner pointed at both repos).
2. Python ≥ 3.12; zero hard deps in core (+`packaging`); MCP implemented on the contract, no SDK.
3. Active profiles from `SHARPIT_PROFILES` → `APP_ENV`/`ENV`/`ENVIRONMENT`.
4. Static `os.getenv` discovery as a config source.
5. Svelte 5 + Vite UI with the §10 direction.
6. Config overrides deferred (they write files).
