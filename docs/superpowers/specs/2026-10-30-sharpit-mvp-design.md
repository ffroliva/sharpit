# sharpit MVP — design (REA + Replica port of BootUI to Python/FastAPI)

Status: rev 2, after LLM-council round 1 (Codex gpt-6-luna, Gemini 3.8 Flash, Claude Opus) · 2026-10-30 ·
owner: Flavio Oliva · coordinator: Claude. Council reviews: `docs/superpowers/specs/council/`.

## 1. Intent

sharpit is a **port, not a new product**. BootUI (github.com/jdubois/boot-ui, Apache-2.0) already works for Spring
Boot and Quarkus: an embedded, local-only developer console that makes a running application understandable in
minutes, for humans (browser) and AI agents (MCP). sharpit reverse-engineers that proven design and adapts it to
Python, FastAPI first, framework-neutral underneath.

**Method.** The owner named two tools:
- **REA** (Reverse Engineer Anything, `C:\development\github\rea`) supplies runtime evidence. BootUI's sample app was
  run locally, its UI walked with Playwright, the traffic recorded as a HAR and inspected with REA. The golden
  responses become sharpit's conformance fixtures.
- **Replica** (`C:\development\github\replica-skill`) supplies the process: recon (`replica/recon.md`,
  `replica/features.csv`), architect (this spec), build, test, and diff (`parity.py`, score in the final report).

**Rule for every builder: when in doubt, do what BootUI does.** Sources of truth, in order:
1. This spec where it is explicit (it overrides BootUI only where §14 logs a deviation).
2. `docs/reference/BOOTUI-CONTRACT-MVP.md`: the contract extracted from BootUI's source, with citations.
3. Golden runtime responses (sanitised fixtures under `tests/fixtures/bootui/`).
4. BootUI source and **its unit tests** at `C:\development\github\boot-ui` (read-only). Where §12 names a BootUI test
   class as an oracle, its cases are ported to pytest one for one.

Unlogged deviations are bugs.

## 2. Goals (MVP)

| # | Goal | Contract § |
|---|---|---|
| G1 | Activation and the request guard chain, BootUI semantics, Python signals (§7) | §10, §1 |
| G2 | Panel registry `GET {api}/panels`, `platform: "fastapi"` | §1 |
| G3 | Overview `GET {api}/overview` incl. `activation` | §2 |
| G4 | Config `GET {api}/config`: sources, winning source, masking, filters, paging | §3 |
| G5 | Mappings `GET {api}/mappings/flat` | §4 |
| G6 | Loggers `GET {api}/loggers`, `POST {api}/loggers/{name}` | §5 |
| G7 | Beans `GET {api}/beans` incl. `dependencies` (UI builds the dependency graph) | §6 |
| G8 | Vulnerabilities: GET report (no network), POST scan (OSV + EPSS), dismissed-rules | §8 |
| G9 | **Read-only** MCP server (opt-in) with `get_*` tools only; `{api}/mcp-server` status + toggle | §9 |
| G10 | `{api}/cli` endpoints (dispatcher shared with MCP) | §11 |
| G11 | New web UI at `/sharpit/` consuming the contract | — |
| G12 | Installable wheel (`uv build`) and editable install; `sharpit.install(app)` | — |
| G13 | Dogfood: KliperMedia runs locally with sharpit enabled | — |

Defaults: `path=/sharpit`, `api_path=/sharpit/api` (`{api}` below). `api_path` must start with `path`, or `install()`
raises `ValueError` (the UI uses relative `api/...` URLs).

## 3. Non-goals (MVP)

Django/Flask adapters (the engine is built for them; next), the `sharpit` console script (G10 keeps the endpoint;
the CLI client comes next), gflow-cli mode, config overrides (they write config files), health, profile diff,
conditions, every other BootUI panel, a PyPI release, Trusted Publishing.

## 4. Anti-goals

- A secret leaves the process unmasked via API, UI, MCP, logs or error text. **The only exceptions are explicit
  opt-ins:** `SHARPIT_EXPOSE_VALUES=FULL` (logs a warning at install) and the generated access token, which is
  printed once to stderr in the banner and never through `logging`.
- sharpit is reachable in production or from a non-loopback source without an explicit override.
- Any GET performs a network call, a scan or a mutation. Any cross-site page can read sharpit data.
- Any code execution surface (`eval`, `exec`, dynamic import from input, shell).
- Work on requests that are not under sharpit's mount; `install()` doing more than settings, activation and mounting
  (budget: median of 5 runs ≤ 50 ms on the example app, measured by a test, with sockets blocked).
- The UI does not copy BootUI's visual design: it is a new Svelte look (see §14, "Vue UI"). Only the JSON contract is shared.

## 5. Constraints

- Python ≥ 3.12 (KliperMedia is 3.14; CI 3.12–3.14). Host: FastAPI ≥ 0.115.
- Runtime dependencies: `starlette` (comes with FastAPI) and `packaging`. Nothing else. OSV/EPSS through stdlib
  `urllib` in a worker thread. MCP implemented on the contract (no SDK). `.env` files are read only through
  pydantic-settings' own sources (no built-in dotenv parser). pydantic-settings is read **if installed**, never
  imported otherwise.
- License Apache-2.0; `NOTICE` credits BootUI for the ported design, contract and test cases.
- Tooling: uv, ruff, pyright (strict on `src/sharpit`), pytest. Branch `mvp` on `ffroliva/sharpit`; agents never
  merge or publish. No AI attribution in commits.
- The UI is prebuilt into `src/sharpit/ui/static/` and committed; end users never need Node.

## 6. Architecture (BootUI's engine/adapter seam)

```
src/sharpit/
  __init__.py        install(app, **options), __version__
  settings.py        SharpitSettings: every option; env SHARPIT_* overrides install() kwargs; frozen at install
  engine/
    activation.py    decide(settings, signals) -> ActivationStatus — pure (port of BootUiActivationCondition)
    guard.py         port of LocalhostGuard + ApiAuthenticationFilter + PanelAccessFilter decisions — pure
    headers.py       BootUiSecurityHeaders
    masking.py       `Masker`, `is_sensitive_key`, `is_secret_value`, `Exposure` (KeywordPatternMasker + SecretValueDetector + ValueExposure)
    relaxed.py       RelaxedNames.canonicalize
    paging.py        PagedList / PageMetadata
    panels.py        registry
    singleflight.py  single-flight actions -> 409 body
    collectors/      overview, config, mappings, loggers, beans, vulnerabilities (osv, epss, cache, dismissals)
    spi.py           AppIntrospector protocol: routes(), providers(), app_info(), dev_signal()
    tools.py         tool catalogue shared by MCP and CLI endpoints
    mcp.py           JSON-RPC dispatcher (transport-free)
  fastapi/
    adapter.py       install(): plain Starlette sub-app (not FastAPI: no 422s), Mount inserted at routes[0]
    introspector.py  FastAPI AppIntrospector
    signals.py       dev-server signal
  ui/static/         built UI
ui/                  UI source (Svelte 5 + Vite + TypeScript)
```

`install(app)` reads settings once, decides activation once, and inserts a `Mount(path, sub_app)` at
`app.router.routes[0]` so host catch-all routes cannot shadow it. `path` must not be `/` or end with `/` (install raises
`ValueError`). Inactive → the mount stays, as BootUI's shell guard does, and answers a plain 404 to every path and
method under `path` and one INFO line is logged. The 404 is the host's own handler, but sharpit still owns those paths:
a host route cannot answer under `path`, and a host with a catch-all or authenticate-first route answers `path/*`
differently from its other paths, so sharpit's presence can be inferred. Active → console + API, banner to stderr when
`show_banner`. Everything expensive (AST scan, `distributions()`, gateway detection) runs lazily on the first GET that
needs it and is memoised. Host middleware still wraps the mount (documented); sharpit's own guard is the sub-app's
middleware, so it adds nothing to host requests.

Request handlers parse query parameters by hand with PagedList semantics: numeric out-of-range values are clamped,
non-numeric values give `400 {"error": "..."}`. Logger routes use `{name:path}`.

## 7. Activation and safety (G1)

### 7.1 Settings
Every BootUI property has an env var `SHARPIT_<PROPERTY>` (dots and dashes → `_`, upper case) and an `install()` kwarg
(snake case). **Env overrides kwargs** for every key, so production can always force `SHARPIT_ENABLED=OFF`. Empty
values count as unset. Booleans accept true/false/yes/no/on/off/1/0; anything else is invalid → that setting is treated
as its fail-safe value and a warning is added to `activation.warnings` (for `SHARPIT_ENABLED`, invalid → disabled with
BootUI's reason text). `SHARPIT_STATE_DIR` (default `.sharpit`, relative to the working directory) holds
`sharpit.yml` (dismissals); it is created only on the first dismissal, files written atomically (temp + replace).

### 7.2 Active profiles
Python has no profiles. sharpit reads the **union** of the variables named by `SHARPIT_PROFILE_VARS`
(default `SHARPIT_PROFILES,APP_ENV,ENVIRONMENT`; the bare `ENV` is excluded because POSIX shells set it to a file
path). Values are split on commas, trimmed and lower-cased. There is no fallback default profile: the runtime capture
proved BootUI ignores Spring's fallback `default`, so sharpit has none.
Defaults: enabled profiles `dev,local,development`; disabled profiles `prod,production`.

### 7.3 Decision (port of BootUiActivationCondition.resolve; reasons verbatim, BootUI→sharpit, property→env name)
1. any active profile in disabled profiles → disabled, unless `SHARPIT_ENABLED=ON` (enabled + warning);
2. `OFF` → disabled; 3. `ON` → enabled; 4. any active profile in enabled profiles → enabled;
5. dev-server signal → enabled; 6. otherwise disabled.

### 7.4 Dev-server signal (the DevTools equivalent)
uvicorn starts its reload children and its `--workers` children the same way (spawn), so process shape cannot tell
them apart. Spawned children inherit the parent's `sys.argv` (verified 2026-10-30 on Windows/spawn with uvicorn: the
child of `--reload` and of `--workers 2` both see the full parent argv; a council claim that children see
`--multiprocessing-fork` was checked and is wrong). Activation is decided in `install()`, which for `--factory` and
`module:app` runs inside the child. Algorithm, in order; anything else returns False:
- argv contains `--reload` (uvicorn CLI, incl. `--factory`, incl. `--reload --workers N` where reload wins) →
  `"uvicorn --reload"`;
- the program is the FastAPI CLI (`argv[0]` basename `fastapi`/`fastapi.exe` or `-m fastapi`) and the subcommand is
  `dev` → `"fastapi dev"`;
- programmatic `uvicorn.run(..., reload=True)` is **not** detected (argv shows only the script); users set a profile.
  Logged in §14.
Tests: `--reload`, `--reload --workers 2`, `--workers 2`, `fastapi dev`, `fastapi run`, gunicorn + UvicornWorker,
plain script, programmatic reload (→ False). Reason text: `"Enabled because a reloading development server was
detected (<which>)"`.

### 7.5 Request guard chain (port of LocalhostGuard and friends, applied to every request under `path`)
Order as BootUI: security headers → trusted-source → Host allow-list → cross-site → token → panel access.
- **Trusted source.** The peer is `scope["client"][0]`. uvicorn may already have rewritten it from
  `X-Forwarded-For` (`proxy_headers` defaults on; `FORWARDED_ALLOW_IPS=*` is common in containers). So, **when any of
  `Forwarded`, `X-Forwarded-For`, `X-Real-IP` is present and `SHARPIT_TRUSTED_PROXIES` is empty, the source is
  untrusted** regardless of the peer address. Forwarded headers are never used to *grant* trust. Container gateway:
  port BootUI's rule; detection is lazy and never resolves DNS (read `/proc/net/route` on Linux only).
- **Host allow-list** and **malformed Host** handling: port `LocalhostGuard.extractRequestHost` / `isAllowedHost`
  exactly (authority-form only, IPv6 brackets, lower-case, port ignored, malformed → reject, absent/blank → allow).
- **Cross-site — deviation, stricter than BootUI:** applied to **all methods**, not only writes. Reject when
  `Sec-Fetch-Site: cross-site`, or `Origin` is present and, on API paths, its full origin (scheme, host and port) differs from the request's
  (stricter than BootUI's host-only comparison). Reason: a host app's `CORSMiddleware(allow_origins=["*"])` wraps sharpit's mount, so a cross-origin GET
  would otherwise be readable by any website the developer visits.
- **Token.** Only loopback or the trusted container gateway, with no forwarded header, skip it. Every other admitted
  caller (through `SHARPIT_ALLOW_NON_LOCALHOST` or a `SHARPIT_TRUSTED_PROXIES` peer) must present it. Token from
  `SHARPIT_AUTHENTICATION_TOKEN`, else generated per process with `secrets.token_urlsafe(32)` when remote access is
  enabled, printed once to stderr in the banner. Multi-worker deployments must configure the token (documented).
  `POST {api}/auth/session` with `Authorization: Bearer` → 204 and `SHARPIT_SESSION=<token>; Path=<root_path><api_path>;
  HttpOnly; SameSite=Strict[; Secure on https]`. 401 body and `WWW-Authenticate: Bearer realm="sharpit"` per contract.
- **Panel access.** Global read-only and per-panel enabled/read-only, bodies per contract §1.

### 7.6 Guard matrix
| Path | Source/Host/cross-site | Token | Panel gate |
|---|---|---|---|
| `{path}` → 307 to `{path}/` | yes | no | no |
| `{path}/` shell, `{path}/assets/*` | yes | no (the UI must load to show the token prompt) | no |
| `{api}/auth/session` | yes | bearer in header | no |
| `{api}/panels`, `/overview`, `/cli` | yes | yes | no |
| panel endpoints | yes | yes | panel id from §8 table |
| `{api}/dismissed-rules*` | yes | yes | global read-only only |
| `{api}/mcp` | yes | yes | MCP enabled switch only |
| any path, sharpit inactive | — | — | 404 |

### 7.7 Masking
Port KeywordPatternMasker, SecretValueDetector and ValueExposure (one `engine/masking.py`) with their BootUI
tests. Any URL carrying userinfo is masked, user name included. Additions for Python (logged §14): values whose type is pydantic `SecretStr`/`SecretBytes` are always masked;
**`defaultValue` (properties and suggestions) is masked with the same rules**, because Python defaults come from code
(`os.getenv("JWT_SECRET", "dev-secret")`). Masking happens **before** filtering, so `q` searches only displayed
values. Middleware constructor arguments are never exposed.

## 8. Endpoints and panels

| Method | Path | Panel gate | Notes |
|---|---|---|---|
| GET | `{api}/panels` | — | registry: overview, config, mappings, loggers, beans, vulnerabilities, mcp-server, cli |
| GET | `{api}/overview` | — | |
| GET | `{api}/config` | config | `q, source, overridesOnly, offset, limit`; `overrideCount` 0; panel not action-capable in MVP |
| GET | `{api}/mappings/flat` | mappings | `q, offset, limit` |
| GET | `{api}/loggers` | loggers | `q, offset, limit` |
| POST | `{api}/loggers/{name:path}` | loggers (write) | `{"level": ...}` |
| GET | `{api}/beans` | beans | `q, classification, offset, limit` |
| GET | `{api}/vulnerabilities` | vulnerabilities | cached report or "not scanned" DTO; never network |
| POST | `{api}/vulnerabilities/scan` | vulnerabilities (write) | single-flight, 409 busy |
| GET/POST/DELETE | `{api}/dismissed-rules[/{ruleId}]` | global read-only | `{"dismissed":[...]}` |
| GET | `{api}/mcp-server` | mcp-server | status |
| POST | `{api}/mcp-server/toggle` | mcp-server (write) | in-memory, contract §9 |
| POST | `{api}/mcp` | MCP switch | JSON-RPC; GET → 405 |
| GET | `{api}/cli` · POST `{api}/cli/tools/{tool}` | — | contract §11 |
| POST | `{api}/auth/session` | — | §7.5 |

Shapes, status codes, error bodies and cache headers are the contract's: API `no-store, must-revalidate` + `Pragma:
no-cache`; shell `index.html` `no-cache`; hashed assets `public, max-age=31536000, immutable` (set explicitly; Starlette
`StaticFiles` does not). `GET {api}/mcp` → 405 with `Allow: POST`. Keys are never renamed; Java-named keys carry
the nearest Python value. Every DTO key is emitted, `null` when unknown.

- **Overview.** `bootUiVersion` = sharpit version; `applicationName` = FastAPI `title` or `"application"`;
  `frameworkName` `"FastAPI"`; `frameworkVersion` = installed fastapi; `javaVersion` = `platform.python_version()`;
  `javaVendor` = `platform.python_implementation()` (+ `" (free-threaded)"` when the GIL is disabled);
  `activeProfiles`; `defaultProfiles` `[]`; `webApplicationType` `"ASGI"`; `serverPort` = `scope["server"][1]` of the
  current request or null; `managementPort` null; `contextPath` = `scope["root_path"]` or null; `startupTimeMillis` =
  monotonic ms from `install()` to the first lifespan startup, or null if lifespan never ran; `activation`;
  `openApiUrl` = `app.docs_url` or null.
- **Config.** Every property is keyed by the **environment variable name** it is read from. Sources:
  1. *pydantic-settings instances* passed as `install(app, settings=[...])` (if pydantic-settings is installed). For each
     field, compute the env name from `env_prefix`, `alias`/`validation_alias` and case-sensitivity, and decide the
     winning source in pydantic-settings' own order: `systemEnvironment` (present in `os.environ`) → `dotenv: <path>`
     (the model's own `env_file`, in its order) → `secrets: <dir>` → `default (<ClassName>)`. The value shown is the
     instance's value, serialised with `str()` (JSON scalars kept), then masked. `description`/`defaultValue` from the
     field. Init-kwarg values are reported as source `init (<ClassName>)`. Nested models use `env_nested_delimiter`
     when set, else are shown as one JSON value.
  2. *systemEnvironment*: every other `os.environ` key.
  3. *getenv scan*: an AST scan of the packages in `install(..., config_scan=[...])`, default the top-level package of
     the module that called `install()`, `False` disables it. Supported forms with a literal key: `os.getenv(K[, D])`,
     `os.environ.get(K[, D])`, `os.environ[K]`, `environ.get` after `from os import environ`, `getenv` after
     `from os import getenv`. It contributes keys not set anywhere: they appear in `propertySuggestions` with
     `defaultValue` = the literal default (masked) and `description` = `"<relpath>:<line>"`. Files over 1 MB and
     unparsable files are skipped silently. Fixture corpus with expected findings in tests.
  `sources` lists the sources that contributed, in precedence order. `q` relaxed matching per RelaxedNames.
  `.env` files are reported only when a settings model names them; a file merely present in the working directory is
  never treated as active.
- **Mappings flat.** Walk `app.routes` recursively: `APIRoute`/`Route` (methods minus Starlette's implicit HEAD),
  `WebSocketRoute` (method `WS`), `Mount` with routes (recurse, join paths), `Mount` without routes (e.g.
  `StaticFiles`: one row `ANY <prefix>/{path}`), `Host` (recurse, host recorded). Exclude sharpit's own mount. Handler
  = `module:qualname` (for mounted apps without routes, the class's). `produces` = `route.response_class.media_type`;
  `consumes` = the body field's media type (`application/json`, `multipart/form-data`, `application/x-www-form-urlencoded`)
  or null without a body. Output sorted by path then method.
- **Loggers.** `logging.root.manager.loggerDict` without `PlaceHolder`s, plus root named `ROOT` (POST accepts `ROOT`
  and `root`). Levels list `CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET`. POST level `null` resets: `NOTSET` for
  named loggers, `WARNING` for root. Unknown level → 400 `{"error":"Unknown level 'X'"}`. Changing `sharpit` or
  `sharpit.*` → 400 with BootUI's message, renamed: `"Refusing to change the level of sharpit's own logger '<name>'."`
  Process-local, runtime only.
- **Beans.** One bean per dependency provider: every callable in any route's `dependant` tree (incl. router-level and
  app-level dependencies), each user middleware class, the lifespan handler, each `dependency_overrides` entry.
  `name` = `module:qualname` (for callable instances, the class's; when two distinct objects share a name, the second
  and later get `#2`, `#3` in discovery order), deduplicated by object identity;
  `dependencies` = names of direct sub-dependencies (every one must resolve to a bean `name` — tested);
  `scope` `"request"` for dependencies, `"singleton"` for middleware/lifespan; `resource` =
  `inspect.getsourcefile:line` or null; `classification` per contract, application vs framework by whether the module
  lives under site-packages. Routers are not beans (`include_router` keeps no reference). Overrides: the overriding
  callable is the bean; the original is listed with `overriddenBy`, if the contract has no such field it goes in
  `description`.
- **Vulnerabilities.** Inventory from `importlib.metadata.distributions()`, deduplicated by (normalised name, version)
  keeping the first on `sys.path`, skipping distributions without a version, excluding sharpit. Mapping:
  `groupId="pypi"`, `artifactId` = `packageName` = PEP 503 normalised name, dismissal rule id `<vulnId>::pypi:<name>`,
  `source="importlib.metadata"`, Maven-worded messages rewritten (§14). OSV `querybatch` with ecosystem `PyPI`, caps
  `max_packages`/`max_advisories`/`request_timeout`, details fetched with concurrency 10, severity from CVSS vectors by
  porting BootUI's `CvssV3BaseScore` (pure arithmetic, no dependency) and its tests,
  EPSS enrichment (failure keeps OSV results), fix availability via `packaging.version`, BootUI ordering. Report cached
  in memory until restart. A scan that outlives a caller's timeout keeps running, holds the single-flight lock until it
  finishes, then caches its report.

## 9. MCP (G9) and CLI endpoints (G10)

The tool catalogue: `get_overview, get_config, get_mappings, get_loggers, get_beans, get_vulnerabilities_report` with
BootUI's names, schemas (verbatim from `McpToolSchema`/`BootUiMcpService.schema`) and caps. **MCP exposes no action
tool** (the goal says read-only); `vulnerabilities_scan` exists in the catalogue only for `POST {api}/cli/tools/...`,
gated by the vulnerabilities panel and read-only. MCP transport: BootUI's POST-only subset of streamable HTTP, every
HTTP case in contract §9 ("HTTP-level responses") is one test row. `serverInfo.name` `"sharpit"`; `instructions` and
messages ported from BootUI's `McpGuidance` with names substituted; `prompts/list` returns `[]`. Response-size caps
count UTF-8 bytes of the serialised JSON. Timeout → -32002 and the MCP semaphore is released. Default
`SHARPIT_MCP_ENABLED=OFF`.

## 10. UI (G11)

Flows and states come from BootUI (recon S00–S07, F01–F05); the look is new. Direction: calm, dense, keyboard-first.
Acceptance checks, each verified in a real browser over the example app:
1. Left rail from the registry; unavailable and read-only panels show their reason.
2. Ctrl/Cmd+K palette jumps to any panel, logger or config key; every action reachable by keyboard.
3. Tables filter as you type and page from the server (page size 200).
4. Config grouped by source with the winning source marked; masked values visibly badged.
5. Dependency graph: interactive node-link view with focus on a bean and its neighbours.
6. Vulnerabilities: never-scanned, scanning, busy (409), failed, results and dismissed states.
7. Token prompt for untrusted sources calls `auth/session`.
8. Light and dark themes; WCAG AA contrast (axe check in Playwright); `prefers-reduced-motion` honoured.
9. Runs under sharpit's CSP (no inline script, no eval); the production build is loaded with that CSP in Playwright.
Stack: Svelte 5 + Vite + TypeScript, relative `api/...` URLs. Built with the `impeccable`/`frontend-design` skills.

## 11. Dogfooding (G13)

KliperMedia (`C:\development\github\klipermedia`): a local-only worktree and branch, never pushed. Editable install of
the sharpit worktree; `sharpit.install(app)` inside `kliper.adapters.web.fastapi_app.create_app`; started with its normal
command `uv run uvicorn kliper.adapters.web.fastapi_app:create_app --factory --reload --port 8001` and
`SHARPIT_PROFILE_VARS=KLIPER_ENV,SHARPIT_PROFILES` in the local environment; `localhost` in `KLIPER_ALLOWED_HOSTS`.
Done when: `/sharpit/` loads; each MVP panel returns non-empty `properties`/`mappings`/`loggers`/`beans`/inventory;
a secret-named variable is masked; a scan completes; with `KLIPER_ENV=production` every sharpit path returns 404.

## 12. Testing

- **Oracles ported from BootUI tests:** LocalhostGuardTests, SecretValueDetectorTests, RelaxedNamesTests,
  SensitiveNamesTests, UriMaskingTests, CredentialRedactionTests, BootUiActivationConditionTests (+Additional),
  ConfigServiceTests, LoggersServiceTests, OsvVulnerabilityScannerTests, BootUiMcpServiceTests, AbstractMcpConformanceTest.
  Each ported case cites its source test.
- **Conformance:** golden responses captured from BootUI 1.17.0 (sample app, profile dev, recorded in fixture
  metadata). Sanitisation replaces only an enumerated list of volatile values (paths, versions, hostnames, timings);
  keys, types, nullability, enums and masking are preserved. Shape tests per endpoint, minus §14 deviations.
- **Safety:** every decision-table row and every guard-matrix row; spoofed `X-Forwarded-For` with
  `FORWARDED_ALLOW_IPS=*`; host app with `CORSMiddleware(allow_origins=["*"])`; catch-all route; inactive 404 for every
  path and method; env-overrides-kwargs.
- **No side effects on GET:** every GET and every MCP tool runs with sockets blocked and a spy that fails on
  `Logger.setLevel`, writes under `state_dir` and `os.environ` changes.
- **Masking corpus** asserted across API, MCP and CLI-endpoint outputs, incl. secret defaults and `q` probing.
- OSV/EPSS from recorded responses; a fake OSV that sleeps past the MCP timeout.
- `examples/fastapi_sample/` exercises every panel. UI: vitest + Playwright (§10 checks).
- CI: GitHub Actions, Python 3.12–3.14, ruff, pyright, pytest, UI build, built UI committed and up to date.
- **Parity:** `replica/features.csv` updated as features land; the must-priority rows must all be `yes` and
  `parity.py` reported in the morning summary.

## 13. Left to the builder

Internal module structure, caching details, UI component structure and visuals within §10, fixture sanitisation tooling.

## 14. Deviation log

| BootUI | sharpit | Reason |
|---|---|---|
| `/bootui`, `bootui.*`, `BOOTUI_SESSION`, realm BootUI | `/sharpit`, `SHARPIT_*`, `SHARPIT_SESSION`, realm sharpit | name; env config |
| Spring active profiles | union of `SHARPIT_PROFILE_VARS`; `development` added to enabled | no profiles in Python |
| DevTools on classpath | argv-based dev-server signal; programmatic reload not detected | no DevTools; safe default |
| cross-site check on writes only | on every method | host-wide CORS middleware in Python |
| forwarded headers ignored (raw socket peer) | forwarded headers present → untrusted | ASGI servers rewrite the peer |
| XSRF cookie priming | dropped | Spring Security only |
| `defaultValue` unmasked | masked | Python defaults come from code |
| `platform` spring-boot/quarkus | `fastapi` | framework |
| `javaVersion`, `javaVendor`, `webApplicationType` | same keys, Python values, `ASGI` | keep contract keys |
| property sources, config metadata | settings instances, environ, getenv scan | no single Environment |
| beans, application context | dependency providers, middleware, lifespan | no IoC container |
| Maven coordinates, messages | `pypi` group, normalised names, PyPI wording | ecosystem |
| config overrides, health, profile diff | deferred | MVP scope |
| MCP `vulnerabilities_scan` | CLI endpoint only | MCP read-only goal |
| CLI client | deferred; endpoint kept | MVP scope |
| `.bootui/boot-ui.yml` | `.sharpit/sharpit.yml`, created lazily | name |
| Vue UI | Svelte UI, same contract | owner wants a new look |
| validation errors → host 500 | `400 {"error"}` | contract ambiguity #1 |
| Docker Desktop `gateway.docker.internal` DNS lookup for gateway trust | route-table gateway only, no DNS | no network or DNS at request time |
| bare `{path}` handled by the host router (Spring) | guarded `SharpitMount` also matches bare `{path}` | a Starlette `Mount` never receives it |
| `pydantic-settings` custom `settings_customise_sources` | source shown as `settings (<Class>)` | provenance cannot be inferred |
| Host-only Origin check on writes | full origin (scheme+host+port) compared on every API path | stricter against cross-port and cross-scheme requests; a TLS-terminating proxy must run `uvicorn --proxy-headers` or same-origin writes are refused |
| No per-endpoint body caps | per-endpoint caps answer `413 {"error":"Request payload exceeds limit"}` | bounded memory for a console on a dev machine; oversized payloads are refused |
| Forwarded-header 403 generic text | 403 text names `SHARPIT_TRUSTED_PROXIES` and `SHARPIT_ALLOW_NON_LOCALHOST` | the user can fix it without reading source |
| `BOOTUI_ENABLED` boolean | `SHARPIT_ENABLED` accepts 1/0/true/false/yes/no/on/off, case-insensitive; `ON` overrides a disabled profile and adds a warning | env var ergonomics; a loud opt-in instead of silent profile precedence |
| Vulnerabilities `scannedAt` always a timestamp | `scannedAt` is `null` before the first scan | no scan has happened; no invented time |
| Beans carry no `overriddenBy` key | provider `overridden_by` is appended to `resource` as `(overridden by X)` | keeps the bean DTO keys; the override is still visible |
| URL userinfo masked only with a non-empty user | any URL with userinfo is masked, including an empty user (`scheme://:x@host`) | fail closed; an odd non-secret `://:x@` URL is masked too |
| FULL exposure shows raw values | FULL keeps the `SecretStr` placeholder `**********` and shows plain-`str` defaults | Pydantic `SecretStr` cannot be unwrapped safely; FULL is an explicit opt-in |
| Config suggestions unfiltered | suggestions are filtered by `q` (relaxed name or description) | contract §3 is silent; fewer, relevant hits while searching |
| MCP `prompts/list = []` (spec §9) | BootUI's 3 prompt names and 5 conformance fragments kept, rewritten for sharpit's tools and Python | the conformance tests need them; wording follows the Python port |
| Localhost grant survives forwarded headers | a forwarded header voids the localhost grant unless a trusted proxy is configured | uvicorn `FORWARDED_ALLOW_IPS=*` rewrites the peer; a local reverse proxy that adds `X-Forwarded-For` needs a token |
| A trusted-proxies peer needs no token (`ApiAuthenticationFilterTests.sourcesTrustedViaTrustedProxiesDoNotRequireAuthentication`) | a trusted-proxies peer is admitted past the source check but must present the token | the ASGI server may have rewritten the peer from `X-Forwarded-For` (`--forwarded-allow-ips='*'`), so a spoofed header could land inside the range |
| Vue UI look and feel (Svelte row above) | the UI is a new design (DESIGN.md), not a restyle of BootUI's | owner wants a new look; behaviour follows the contract |
| Spring MVC, WebFlux and Quarkus adapters | FastAPI is the only adapter in the MVP | scope; the engine is framework-neutral behind the `spi` |
| `bootui` CLI binary | no `sharpit` console script; only `/api/cli` endpoints | MVP scope (repeats the CLI client row for the binary itself) |
| Panel copy says "beans" | panel copy says "providers"; ids and keys (`beans`) are unchanged | no IoC container in Python; the contract stays stable |
| OSV and EPSS base URIs resolved with an absolute path (`URI.resolve("/v1/querybatch")` drops the base path) | the base URI's path is kept (`https://mirror/osv` + `v1/querybatch`) | a mirror or proxy under a path prefix works |
| `activation.localhostOnly` = `!allow-non-localhost` | `localhostOnly` is false whenever remote access is configured: `allow_non_localhost`, `trusted_proxies` or container gateway trust | the Overview's "This machine only" must not show while proxies or the gateway are admitted; the key is unchanged |
| `bootui.path` taken as configured | `path="/"` and a trailing slash are refused with `ValueError` at install | `/` would mount over every host route even while inactive; a trailing slash produced `/sharpit//api` |
| sharpit's own token follows the exposure policy | sharpit's own token value is masked under every exposure except `METADATA_ONLY` (which shows no values), even with `mask_secrets=false` or `FULL` | the token grants the whole console; an MCP client would pass it to an LLM provider |

## 15. Coordinator's calls (owner to check)

1. "REA" = REA tool for runtime evidence + Replica for process.
2. Deps: starlette + packaging only; MCP on the contract, no SDK; own `.env` parser.
3. Profiles: union of `SHARPIT_PROFILE_VARS`; `development` enabled by default; env beats kwargs.
4. Dev signal is argv-only; programmatic `reload=True` needs a profile.
5. Cross-site rejection on all methods; forwarded headers make a source untrusted.
6. MCP strictly read-only; CLI client deferred.
7. getenv scan on by default for the caller's package, lazy.
8. Svelte 5 + Vite UI.
