# sharpit MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pip-installable `sharpit` package whose `sharpit.install(app)` gives a FastAPI app BootUI's local-only developer console (overview, config, mappings, loggers, beans/graph, vulnerabilities, read-only MCP, CLI endpoints) with a new Svelte UI at `/sharpit/`.

**Architecture:** A framework-neutral engine (`sharpit.engine`: pure functions and collectors, no Starlette imports except in `engine/http.py`) plus a thin FastAPI adapter that inserts one Starlette `Mount` at `app.router.routes[0]`. The engine ports BootUI's Java classes and their unit tests one for one; shapes come from `docs/reference/BOOTUI-CONTRACT-MVP.md`.

**Tech Stack:** Python ≥ 3.12, Starlette (via FastAPI ≥ 0.115), `packaging`, stdlib `urllib`/`ast`/`importlib.metadata`/`logging`; uv, ruff, pyright strict, pytest; UI: Svelte 5 + Vite + TypeScript, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` (rev 2). Executors read the spec, the contract file, and this plan. BootUI source (read-only) at `C:\development\github\boot-ui`.

## Global Constraints

- Python `>=3.12`; runtime deps exactly `starlette` (any version FastAPI ≥ 0.115 brings) and `packaging`. `fastapi` and `pydantic-settings` are optional: import them only inside `try/except ImportError` or in `sharpit/fastapi/`.
- Defaults: `path="/sharpit"`, `api_path="/sharpit/api"`; `api_path` not starting with `path` → `ValueError`.
- Env `SHARPIT_*` overrides `install()` kwargs; empty env value = unset.
- Every JSON key in the contract DTOs is emitted (nulls included), camelCase, no envelope, epoch ms.
- Error bodies and reason strings verbatim from contract §1/§10 with `BootUI`→`sharpit`, `bootui.<prop>`→`SHARPIT_<PROP>` (e.g. `"Disabled by SHARPIT_ENABLED=OFF"`, `{"error":"sharpit authentication required"}`, `WWW-Authenticate: Bearer realm="sharpit"`, `"sharpit panel access denied"`, `"sharpit action already in progress"`).
- No GET and no MCP tool may open a socket, write a file, change a logger level or change `os.environ`.
- Each ported test cites its BootUI source in a comment: `# ported: LocalhostGuardTests.rejectsMalformedHost`.
- Commits: conventional prefix (`feat:`, `test:`, `chore:`), no AI attribution of any kind. Never push to `master`, never merge, never publish.
- Long commands (full pytest, `uv build`, `npm run build`, Playwright) run in the background with a timeout and a log file.

## Review Focus

1. **A secret reaching any output through a side door** — error messages, `description`, `defaultValue`, MCP `structuredContent`, CLI tool output, `q` probing. Expectation: never. Pinned by Task 14's corpus test over every surface.
2. **sharpit active in production because a profile var is spelled differently** (`Production`, ` prod `, `prod,dev`). Expectation: disabled. Pinned in Task 4 (`test_disabled_profile_case_and_whitespace`).
3. **Large real apps** (KliperMedia: ~300 routes, 79 getenv keys, ~200 distributions): pages must stay ≤ 1000 items and the UI must not freeze. Pinned in Task 6 (`test_limit_clamped_to_1000`) and Task 15's 2,000-row table check.
4. **A host app with its own middleware stack** (`TrustedHostMiddleware`, `CORSMiddleware`, auth middleware, SPA catch-all). Expectation: sharpit still reachable from localhost and unreadable cross-site. Pinned in Task 7 (`test_host_cors_wildcard_cannot_read`, `test_catch_all_does_not_shadow`).
5. **OSV down or slow during a scan.** Expectation: the scan reports failure in `scan.status` with a message, the UI shows it, and the next scan works. Pinned in Task 12 (`test_osv_failure_reports_status_and_releases_lock`).

---

## File map

```
pyproject.toml, .gitattributes, NOTICE, README.md, .github/workflows/ci.yml
src/sharpit/__init__.py                 install, __version__
src/sharpit/settings.py                 SharpitSettings, load_settings
src/sharpit/engine/masking.py           Masker, SecretValueDetector, is_sensitive_name, mask_uri, redact_credentials
src/sharpit/engine/relaxed.py           canonicalize
src/sharpit/engine/paging.py            PageMetadata, paged
src/sharpit/engine/panels.py            PANELS, panels_report, panel_for_api_path
src/sharpit/engine/headers.py           security_headers
src/sharpit/engine/singleflight.py      SingleFlight, ActionBusy
src/sharpit/engine/activation.py        ActivationStatus, decide, active_profiles
src/sharpit/engine/guard.py             GuardConfig, GuardDecision, decide_guard, extract_request_host, check_token, panel_access
src/sharpit/engine/collectors/overview.py
src/sharpit/engine/collectors/config/{__init__,dotenv,settings_source,getenv_scan}.py
src/sharpit/engine/collectors/loggers.py
src/sharpit/engine/collectors/vulns/{inventory,cvss,osv,epss,service,dismissals}.py
src/sharpit/engine/spi.py               AppIntrospector, RouteInfo, ProviderInfo, AppInfo
src/sharpit/engine/tools.py             Tool, TOOLS, call_tool
src/sharpit/engine/mcp.py               McpServer
src/sharpit/fastapi/{adapter,introspector,signals,http}.py
src/sharpit/ui/static/                  built UI (committed)
ui/                                     Svelte source
examples/fastapi_sample/app.py
tests/fixtures/bootui/*.json            sanitised golden responses + meta.json
tests/...                               one test module per source module
scripts/sanitize_golden.py
```

---

### Task 1: Project scaffold, sanitised golden fixtures, CI

**Files:**
- Create: `pyproject.toml`, `.gitattributes` (`* text=auto eol=lf`), `NOTICE`, `src/sharpit/__init__.py`, `src/sharpit/py.typed`, `tests/conftest.py`, `scripts/sanitize_golden.py`, `tests/fixtures/bootui/*.json`, `tests/fixtures/bootui/meta.json`, `tests/test_fixtures.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `sharpit.__version__ = "0.1.0.dev0"`; fixture loader `tests/conftest.py::golden(name: str) -> dict`; pytest fixture `no_side_effects` (blocks `socket.socket.connect`, `socket.create_connection`, spies `logging.Logger.setLevel`, `os.environ` mutation, and `open(..., "w")` under a given dir; fails the test on any).

- [ ] **Step 1:** Write `pyproject.toml`: hatchling build, `name="sharpit"`, `requires-python=">=3.12"`, `dependencies=["starlette>=0.40","packaging>=23"]`, optional `test=["fastapi>=0.115","pydantic-settings>=2.4","httpx","pytest","pytest-timeout"]`, ruff (line length 120), pyright strict on `src/sharpit`, pytest `testpaths=["tests"]`, `timeout=60`. Wheel includes `src/sharpit/ui/static/**`.
- [ ] **Step 2:** `scripts/sanitize_golden.py <src_dir> <dst_dir>`: loads each `replica/evidence/golden/*.json`, replaces values of an enumerated volatile list only (absolute paths → `"/path"`, hostnames → `"localhost"`, versions in `bootUiVersion/frameworkVersion/javaVersion` → `"x"`, `startupTimeMillis`/`scannedAt` → `0`), truncates every top-level list to its first 5 items (recomputing nothing — `page` keeps original values), and writes `meta.json` `{"bootui": "1.17.0", "app": "bootui-spring-sample-app", "profile": "dev", "captured": "2026-10-30"}`. It also asserts that no value outside masked ones matches `SecretValueDetector` patterns (simple regexes) and aborts otherwise.
- [ ] **Step 3:** Run it: `uv run python scripts/sanitize_golden.py replica/evidence/golden tests/fixtures/bootui`. Expected: files for panels, overview, config, mappings, loggers, beans, vulnerabilities; `mcp.json` (empty capture) skipped.
- [ ] **Step 4:** `tests/test_fixtures.py::test_golden_shapes_load` asserts each fixture loads and `golden("overview")["activation"]["enabled"] is True`, and `test_no_side_effects_blocks_socket` asserts that `socket.create_connection(("1.1.1.1", 80))` raises inside the fixture.
- [ ] **Step 5:** CI workflow: matrix 3.12/3.13/3.14 on ubuntu + windows-3.14; `uv sync --extra test`, `ruff check`, `ruff format --check`, `pyright`, `pytest`; job `ui`: `npm ci && npm run build && git diff --exit-code src/sharpit/ui/static` in `ui/`.
- [ ] **Step 6:** `NOTICE`: "sharpit ports the design, JSON contract and test cases of BootUI (https://github.com/jdubois/boot-ui), Copyright Julien Dubois, Apache License 2.0."
- [ ] **Step 7:** Run `uv sync --extra test && uv run pytest -q` → 2 passed. Commit `chore: scaffold sharpit package, fixtures and CI`.

### Task 2: Masking, relaxed names (ported oracles)

**Files:**
- Create: `src/sharpit/engine/__init__.py`, `src/sharpit/engine/masking.py`, `src/sharpit/engine/relaxed.py`
- Test: `tests/engine/test_masking.py`, `tests/engine/test_relaxed.py`

**Interfaces:**
- Produces:
  - `MASK = "******"`
  - `class Exposure(StrEnum): MASKED; METADATA_ONLY; FULL`
  - `is_secret_value(value: str) -> bool` (SecretValueDetector)
  - `is_sensitive_key(name: str) -> bool` (KeywordPatternMasker name patterns, contract §3 list)
  - `is_sensitive_header(name: str) -> bool` (SensitiveNames)
  - `mask_uri(uri: str) -> str` (UriMasking), `redact_credentials(text: str) -> str` (CredentialRedaction)
  - `class Masker: __init__(exposure: Exposure, mask_secrets: bool); mask(name: str, value: object) -> tuple[object | None, bool]` returning `(display_value, masked)`; FULL → raw; METADATA_ONLY → `(None, False)`; `SecretStr`/`SecretBytes` (duck-typed: has `get_secret_value`) → always masked unless FULL.
  - `canonicalize(name: str) -> str` (RelaxedNames)

- [ ] **Step 1:** Port every `@Test` from `bootui-core/.../SecretValueDetectorTests.java`, `bootui-engine/.../support/{SensitiveNamesTests,UriMaskingTests,CredentialRedactionTests,RelaxedNamesTests}.java` and the KeywordPatternMasker tests, as parametrised pytest cases with identical inputs/outputs. Add sharpit cases: `test_secretstr_always_masked`, `test_metadata_only_hides_value`, `test_full_returns_raw`, `test_cache_key_prefix_masked_by_design` (`"cache.key-prefix"` → masked).
- [ ] **Step 2:** Run `uv run pytest tests/engine/test_masking.py tests/engine/test_relaxed.py` → FAIL (import error).
- [ ] **Step 3:** Implement by porting the Java classes (regexes verbatim from contract §3 and the Java sources).
- [ ] **Step 4:** Run → PASS. Commit `feat: port BootUI masking and relaxed names`.

### Task 3: Paging, panels registry, security headers, single-flight

**Files:**
- Create: `src/sharpit/engine/{paging,panels,headers,singleflight}.py`
- Test: `tests/engine/test_paging.py`, `test_panels.py`, `test_headers.py`, `test_singleflight.py`

**Interfaces:**
- Produces:
  - `paged(items: Sequence[T], q: str | None, offset: int | None, limit: int | None, text: Callable[[T], Iterable[str | None]]) -> tuple[list[T], dict]` — the dict is PageMetadata `{"total","matched","offset","limit","returned","hasMore"}`; rules per contract §1 (q trimmed+lowercased substring over `text(item)`; offset <0/None→0; limit None→matched, else clamp 1..1000).
  - `parse_int_param(raw: str | None, name: str) -> int | None` raising `BadRequest(f"Invalid '{name}' parameter")` for non-integers; `class BadRequest(Exception)`.
  - `Panel(id, title, action_capable: bool | None, api_prefix: str | None)`; `PANELS: tuple[Panel, ...]` = overview(None,None), config(True,"/config"), mappings(False,"/mappings"), loggers(True,"/loggers"), beans(False,"/beans"), vulnerabilities(True,"/vulnerabilities"), mcp-server(True,"/mcp-server"), cli(None,None), in that order; titles from contract §1.
  - `panels_report(global_read_only: bool, panel_flags: Mapping[str, tuple[bool, bool]], available: Mapping[str, str | None]) -> dict` (`panel_flags[id] = (enabled, read_only)`, missing = `(True, False)`; `{"platform":"fastapi","panels":[...]}`; `available[id]` None = available, else the reason). Task 6 adapts `SharpitSettings` to these arguments.
  - `panel_for_api_path(sub_path: str) -> Panel | None` (prefix rule `p == prefix or p.startswith(prefix + "/")`).
  - `security_headers(kind: Literal["api","shell","asset"]) -> list[tuple[str, str]]` (CSP etc. verbatim + cache per kind).
  - `class SingleFlight: run(operation: str, fn: Callable[[], T]) -> T` raising `ActionBusy(operation, active)`; `ActionBusy.body() -> dict` per contract 409 shape; `release` happens when `fn` finishes even if the caller stopped waiting.

- [ ] **Step 1:** Tests: `test_limit_clamped_to_1000` (limit=5000 → `page.limit==1000`), `test_limit_zero_clamped_to_1`, `test_negative_offset_zero`, `test_unbounded_limit_equals_matched`, `test_has_more`, `test_q_case_insensitive_trimmed`, `test_parse_int_rejects_abc`; panels: `test_registry_order_and_titles`, `test_read_only_only_for_action_capable` (global read-only → overview readOnly False, loggers True with reason `"sharpit is read-only via SHARPIT_READ_ONLY=true"`), `test_mcp_not_under_mcp_server_prefix`; headers: exact CSP string; single-flight: `test_second_call_busy_409_body`, `test_lock_released_after_exception`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: paging, panel registry, security headers, single-flight`.

### Task 4: Settings and activation

**Files:**
- Create: `src/sharpit/settings.py`, `src/sharpit/engine/activation.py`, `src/sharpit/fastapi/__init__.py`, `src/sharpit/fastapi/signals.py`
- Test: `tests/test_settings.py`, `tests/engine/test_activation.py`, `tests/fastapi/test_signals.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class SharpitSettings` with fields (defaults): `enabled: str="AUTO"`, `enabled_profiles=("dev","local","development")`, `disabled_profiles=("prod","production")`, `profile_vars=("SHARPIT_PROFILES","APP_ENV","ENVIRONMENT")`, `path="/sharpit"`, `api_path="/sharpit/api"`, `allow_non_localhost=False`, `allowed_hosts=()`, `trusted_proxies=()`, `trust_container_gateway="AUTO"`, `authentication_token: str | None=None`, `read_only=False`, `panels: Mapping[str, PanelSettings]` (`enabled=True, read_only=False`), `expose_values=Exposure.MASKED`, `mask_secrets=True`, `show_banner=True`, `state_dir=".sharpit"`, `config_scan: tuple[str,...] | bool = True`, `vuln_osv_enabled=True`, `vuln_request_timeout=10.0`, `vuln_max_packages=500`, `vuln_max_advisories=200`, `vuln_osv_base_uri="https://api.osv.dev"`, `vuln_epss_enabled=True`, `vuln_epss_base_uri="https://api.first.org/data/v1/epss"`, `mcp_enabled="OFF"`, `mcp_max_results=200`, `mcp_max_payload_bytes=1048576`, `mcp_max_concurrent_calls=20`, `mcp_execution_timeout=30.0`, `mcp_max_response_bytes=4194304`, `cli_enabled=True`, `warnings: tuple[str,...]=()`.
  - `load_settings(kwargs: Mapping[str, object], environ: Mapping[str, str]) -> SharpitSettings` — env name = `"SHARPIT_" + field.upper()` (panels: `SHARPIT_PANELS_<ID>_ENABLED` with `-`→`_`); lists comma-split; booleans true/false/yes/no/on/off/1/0; invalid boolean → field default **if that default is the safe one** plus a warning `"Ignoring invalid SHARPIT_<X> value '<raw>'"`; `ValueError` when `api_path` doesn't start with `path`.
  - `@dataclass(frozen=True) class ActivationStatus: enabled: bool; localhost_only: bool; reason: str; warnings: tuple[str,...]`; `to_dto() -> dict` (`{"enabled","localhostOnly","reason","warnings"}`).
  - `active_profiles(settings, environ) -> list[str]` (union over `profile_vars`, split, trimmed, lower-cased, de-duplicated in order).
  - `decide(settings: SharpitSettings, profiles: Sequence[str], dev_signal: str | None) -> ActivationStatus` (contract §10 order; reasons with env names; step 5 reason `f"Enabled because a reloading development server was detected ({dev_signal})"`; step 6 `"Disabled: no enabled profile and no reloading development server detected"`).
  - `dev_server_signal(argv: Sequence[str]) -> str | None` in `fastapi/signals.py` (spec §7.4).

- [ ] **Step 1:** Port every case from `BootUiActivationConditionTests` and `BootUiActivationConditionAdditionalTests` (map property names to env names). Add: `test_disabled_profile_case_and_whitespace` (`APP_ENV=" Production "` → disabled), `test_union_of_profile_vars` (`APP_ENV=dev`, `ENVIRONMENT=production` → disabled), `test_bare_ENV_ignored`, `test_env_overrides_kwargs` (`kwargs enabled="ON"`, env `SHARPIT_ENABLED=OFF` → disabled), `test_empty_env_is_unset`, `test_invalid_enabled_disables` (reason `"Disabled: invalid SHARPIT_ENABLED value 'maybe'"`), `test_api_path_outside_path_rejected`. Signals: parametrised over the 8 argv cases in spec §7.4, incl. `[".../uvicorn/__main__.py","m:app","--reload","--workers","2"]` → `"uvicorn --reload"`, `["fastapi","dev","main.py"]` → `"fastapi dev"`, `["fastapi","run"]` → None, `["gunicorn","-k","uvicorn.workers.UvicornWorker"]` → None, `["main.py"]` → None.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: settings and fail-closed activation`.

### Task 5: Request guard (ported LocalhostGuard, token, panel access)

**Files:**
- Create: `src/sharpit/engine/guard.py`
- Test: `tests/engine/test_guard.py`

**Interfaces:**
- Consumes: `SharpitSettings`, `panel_for_api_path`, `Panel`.
- Produces:
  - `@dataclass(frozen=True) class RequestFacts: method: str; peer: str | None; headers: Mapping[str, str]` (lower-case keys); `api_sub_path: str | None` (path after `api_path`, None for shell/assets).
  - `extract_request_host(value: str | None) -> str | None` (exact port of `LocalhostGuard.extractRequestHost`).
  - `@dataclass(frozen=True) class Denial: status: int; body: dict; headers: tuple[tuple[str,str],...] = ()`.
  - `is_trusted_source(facts, settings, gateway: str | None) -> bool` — False whenever `forwarded`/`x-forwarded-for`/`x-real-ip` is present and `settings.trusted_proxies` is empty.
  - `decide_guard(facts, settings, token: str | None, gateway: str | None) -> Denial | None` — order: source (skipped when allow_non_localhost) → host → cross-site on **every** method (message `"sharpit rejected a cross-site request."`) → token for untrusted sources on API paths (constant-time compare, bearer or `sharpit_session` cookie) → panel access.
  - `remote_access_configured(settings) -> bool`; `resolve_token(settings) -> tuple[str | None, bool]` (token, generated?) using `secrets.token_urlsafe(32)`.
  - `detect_container_gateway(route_file: Path = Path("/proc/net/route"), in_container: Callable[[], bool] = ...) -> str | None` — port BootUI's gateway rule: only when running in a container (`/.dockerenv` or `/run/.containerenv` exists), parse the default route's little-endian hex gateway; never DNS; None elsewhere (Windows/macOS). Called lazily by Task 6 and memoised.

- [ ] **Step 1:** Port all 65 `@Test` cases from `bootui-engine/.../safety/LocalhostGuardTests.java` (they test pure decisions; map their config builder to `SharpitSettings`). Port `ApiAuthenticationFilterTests` decision cases. Add: `test_xff_with_no_trusted_proxies_is_untrusted` (peer `127.0.0.1` + `x-forwarded-for: 127.0.0.1` → 403 source message), `test_cross_site_get_rejected` (GET + `sec-fetch-site: cross-site` → 403), `test_origin_mismatch_get_rejected`, `test_same_origin_vite_port_allowed` (Origin `http://localhost:5173`, Host `localhost:8000` → allowed), `test_panel_disabled_all_methods_403_body`, `test_dismissed_rules_global_read_only`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: port LocalhostGuard and API guards`.

### Task 6: FastAPI adapter skeleton: install, mount, guard middleware, shell, auth, panels, overview

**Files:**
- Create: `src/sharpit/fastapi/adapter.py`, `src/sharpit/fastapi/http.py`, `src/sharpit/engine/spi.py`, `src/sharpit/engine/collectors/__init__.py`, `src/sharpit/engine/collectors/overview.py`, `src/sharpit/fastapi/introspector.py` (only `app_info()` in this task), `src/sharpit/ui/static/index.html` (placeholder until Task 15)
- Modify: `src/sharpit/__init__.py` (re-export `install`)
- Test: `tests/fastapi/test_install.py`, `tests/engine/test_overview.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces:
  - `install(app, *, settings: Sequence[object] = (), **options) -> SharpitHandle` — reads `load_settings(options, os.environ)`, `decide(...)`, inserts `Mount(path, app=sub_app, name="sharpit")` at `app.router.routes[0]`, registers a lifespan-start hook (wrap `app.router.lifespan_context`) that records startup ms; logs one INFO line `sharpit inactive: <reason>` when inactive; prints banner to stderr when active and `show_banner`.
  - `class SharpitHandle: settings; activation: ActivationStatus; context: SharpitContext` (for tests).
  - `class SharpitContext` holding settings, activation, introspector, masker, token, single-flight, lazy caches; `context.lazy(key: str, factory: Callable[[], T]) -> T` (memoised, thread-safe).
  - `spi.AppIntrospector` Protocol: `app_info() -> AppInfo`, `routes() -> list[RouteInfo]`, `providers() -> list[ProviderInfo]`; `AppInfo(title: str | None, framework: str, framework_version: str | None, docs_url: str | None)`; `RouteInfo` / `ProviderInfo` dataclasses defined here with the fields Tasks 9 and 11 fill (see those tasks).
  - `http.json_response(data, status=200) -> Response` (nulls kept, `security_headers("api")`); `http.error(status, message, **extra)`.
  - Routes in the sub-app: `GET ""`→307 `{path}/`; `GET "/"` shell (`no-cache`); `/assets/{file}` (immutable); `POST /api/auth/session`; `GET /api/panels`; `GET /api/overview`. Inactive sub-app: one catch-all route returning 404 for every method.
  - `overview_dto(ctx, scope) -> dict` (spec §8 Overview, every OverviewDto key).

- [ ] **Step 1:** Tests with `fastapi.testclient.TestClient(app, client=("127.0.0.1", 50000))`: `test_inactive_404_every_path_and_method` (GET/POST/DELETE on `/sharpit`, `/sharpit/`, `/sharpit/api/overview`, `/sharpit/api/nope`), `test_redirect_to_trailing_slash`, `test_shell_served_with_csp_and_no_cache`, `test_overview_shape_matches_golden_keys` (`set(resp) == set(golden("overview"))`, `frameworkName=="FastAPI"`, `webApplicationType=="ASGI"`, `managementPort is None`), `test_panels_platform_fastapi_and_ids`, `test_catch_all_does_not_shadow` (host route `/{p:path}` added before install), `test_host_cors_wildcard_cannot_read` (host `CORSMiddleware(allow_origins=["*"])`, GET overview with `Origin: https://evil.example` → 403), `test_remote_needs_token_and_session_cookie` (allow_non_localhost, client `10.0.0.5`: 401 with `WWW-Authenticate`; `POST auth/session` with bearer → 204 + cookie `Path=/sharpit/api; HttpOnly; SameSite=Strict`; next GET with cookie → 200), `test_install_budget` (median of 5 `install()` on the example-sized app ≤ 50 ms with sockets blocked), `test_startup_time_set_after_lifespan`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (sub-app = `Starlette(routes=..., middleware=[Middleware(GuardMiddleware, ctx=ctx)])`; GuardMiddleware builds `RequestFacts` from `scope` and calls `decide_guard`). **Step 4:** Run → PASS. **Step 5:** Commit `feat: FastAPI install, guard middleware, panels and overview`.

### Task 7: Config collector

**Files:**
- Create: `src/sharpit/engine/collectors/config/__init__.py` (`config_report`), `dotenv.py`, `settings_source.py`, `getenv_scan.py`
- Modify: `src/sharpit/fastapi/adapter.py` (route `GET /api/config`)
- Test: `tests/engine/config/test_dotenv.py`, `test_settings_source.py`, `test_getenv_scan.py`, `test_config_report.py`, fixtures `tests/fixtures/getenv_corpus/`

**Interfaces:**
- Produces:
  - `parse_dotenv(text: str) -> dict[str, str]` (python-dotenv grammar: `export ` prefix, single/double quotes, `\n` escapes in double quotes, `#` comments outside quotes, `${VAR}` expansion from earlier keys/environ in double-quoted and unquoted values).
  - `@dataclass class ConfigEntry: name: str; value: object; source: str; description: str | None; default: object; secret_typed: bool`
  - `settings_entries(instance: object, environ: Mapping[str,str]) -> tuple[list[ConfigEntry], list[str]]` (entries, source names in precedence order) — spec §8 Config item 1; returns `([], [])` when pydantic-settings is not installed or the object is not a `BaseSettings`.
  - `@dataclass class GetenvFinding: key: str; default: str | None; location: str` ; `scan_packages(roots: Sequence[Path]) -> list[GetenvFinding]` (spec §8 item 3 forms; skip `.venv`, `venv`, `node_modules`, `__pycache__`, `site-packages`, files > 1 MB, syntax errors).
  - `config_report(ctx, q, source, overrides_only, offset, limit) -> dict` — ConfigReport per contract §3: masking first (value **and** defaultValue), then filter (`q` via `canonicalize` on name, or substring on displayed value/description/defaultValue), then `paged`; properties sorted by name; `overrideCount` 0; `override` False; `origin` null; `propertySuggestions` = getenv/settings keys with no value anywhere, masked defaults.

- [ ] **Step 1:** Tests: dotenv grammar table (10 rows); settings source: a `BaseSettings` with `env_prefix="APP_"`, field `db_url` with `validation_alias`, `SecretStr` field, `env_file` → winners `systemEnvironment` / `dotenv: <path>` / `default (Settings)` as set up, `test_secretstr_masked`; getenv corpus: a fixture package with all 5 supported forms, a dynamic key (ignored), a syntax-error file (skipped) → exact expected findings list; report: `test_secret_default_masked` (`os.getenv("JWT_SECRET","dev-secret")` → suggestion `defaultValue=="******"`), `test_q_cannot_probe_masked_value` (`API_TOKEN=abc123`, `q=abc1` → `matched==0`), `test_relaxed_q` (`q=my-prop` matches `MY_PROP`), `test_source_filter_exact`, `test_shape_matches_golden_keys` (top-level keys and per-property keys equal golden), `test_dotenv_in_cwd_not_reported`, `test_config_get_no_side_effects` (uses `no_side_effects`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement; the scan root default = top-level package of the module that called `install()` (captured in `install` via `sys._getframe(1).f_globals["__name__"]`), resolved lazily through `importlib.util.find_spec`. **Step 4:** Run → PASS. **Step 5:** Commit `feat: config panel with provenance and masking`.

### Task 8: Loggers

**Files:**
- Create: `src/sharpit/engine/collectors/loggers.py`
- Modify: adapter routes `GET /api/loggers`, `POST /api/loggers/{name:path}`
- Test: `tests/engine/test_loggers.py`, `tests/fastapi/test_loggers_api.py`

**Interfaces:**
- Produces: `loggers_report(q, offset, limit) -> dict` (LoggersReport shape per contract §5); `set_level(name: str, level: str | None) -> dict` raising `BadRequest` with the spec's messages.

- [ ] **Step 1:** Port `LoggersServiceTests` cases that apply. Add: `test_root_named_ROOT`, `test_placeholders_skipped`, `test_post_root_lowercase_accepted`, `test_reset_root_to_warning`, `test_unknown_level_400`, `test_own_logger_refused` (message verbatim from spec), `test_dotted_and_slash_names_route` (`/api/loggers/a.b/c`), `test_read_only_panel_403_on_post`, `test_shape_matches_golden_keys`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat: loggers panel`.

### Task 9: Mappings

**Files:**
- Modify: `src/sharpit/fastapi/introspector.py` (`routes()`), `src/sharpit/engine/spi.py` (`RouteInfo`)
- Create: `src/sharpit/engine/collectors/mappings.py`
- Test: `tests/fastapi/test_introspector_routes.py`, `tests/engine/test_mappings.py`

**Interfaces:**
- Produces: `RouteInfo(methods: tuple[str,...], path: str, handler: str, host: str | None, produces: str | None, consumes: str | None, name: str | None)`; `mappings_flat(ctx, q, offset, limit) -> dict` (shape per contract §4, filled from RouteInfo; Java-only keys null).

- [ ] **Step 1:** Tests on an app with: APIRoute GET+POST, Starlette Route, WebSocket, router via `include_router(prefix="/v1")`, `Mount("/static", StaticFiles(...))`, nested `Mount` with routes, `Host` route, sharpit installed. Assert exact rows (HEAD dropped, `WS`, `ANY /static/{path}`, joined nested path, no `/sharpit` rows, sorted), `produces` `application/json` for APIRoute, `consumes` `multipart/form-data` for a `UploadFile` endpoint, `test_shape_matches_golden_keys`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: mappings panel`.

### Task 10: Beans and dependency graph data

**Files:**
- Modify: `src/sharpit/fastapi/introspector.py` (`providers()`), `src/sharpit/engine/spi.py` (`ProviderInfo`)
- Create: `src/sharpit/engine/collectors/beans.py`
- Test: `tests/fastapi/test_introspector_providers.py`, `tests/engine/test_beans.py`

**Interfaces:**
- Produces: `ProviderInfo(name: str, type_name: str, scope: Literal["request","singleton"], resource: str | None, dependencies: tuple[str,...], application: bool, description: str | None)`; `beans_report(ctx, q, classification, offset, limit) -> dict` (shape per contract §6).

- [ ] **Step 1:** Tests: two `get_db` functions in different modules → distinct names; `OAuth2PasswordBearer` instance → class qualname; two instances of one class → second gets `#2`; nested `Depends` edges; router- and app-level dependencies included; `SessionMiddleware(secret_key="s3cr3t")` → bean present, `"s3cr3t"` appears nowhere in the JSON; `dependency_overrides` → override is the bean, original's `description` names it; `test_every_dependency_resolves_to_a_bean`; `test_classification_application_vs_framework`; `test_shape_matches_golden_keys`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: beans panel with dependency edges`.

### Task 11: Vulnerabilities — inventory, CVSS, OSV/EPSS clients

**Files:**
- Create: `src/sharpit/engine/collectors/vulns/{__init__,inventory,cvss,osv,epss}.py`
- Test: `tests/engine/vulns/test_inventory.py`, `test_cvss.py`, `test_osv.py`, `test_epss.py`, recorded fixtures `tests/fixtures/osv/*.json`, `tests/fixtures/epss/*.json`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Package: name: str (normalised); version: str; location: str | None`; `inventory() -> list[Package]` (spec §8 dedupe/skip rules).
  - `cvss3_base_score(vector: str) -> float | None` (port `CvssV3BaseScore`), `severity_for(score: float | None) -> str` (BootUI thresholds).
  - `class OsvClient: __init__(base_uri, timeout, opener=urllib.request.build_opener()); querybatch(pkgs: Sequence[Package]) -> list[list[str]]` (vuln ids per package); `vuln(id: str) -> dict`.
  - `class EpssClient: scores(cve_ids: Sequence[str]) -> dict[str, tuple[float, float]]`.
  Both take an injectable `opener` so tests pass a fake; no test touches the network.

- [ ] **Step 1:** Port `CvssV3BaseScore` tests and `OsvVulnerabilityScannerTests` parsing cases (inputs adapted from Maven to PyPI). Inventory: fake `distributions()` with a duplicate, a versionless dist and `sharpit` → deduped/skipped. OSV: request body exactly `{"queries":[{"package":{"name":"jinja2","ecosystem":"PyPI"},"version":"3.1.2"}]}`; timeout raises `OsvError`. EPSS: malformed response → `{}`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: vulnerability inventory, CVSS and OSV/EPSS clients`.

### Task 12: Vulnerabilities — scan service, report, dismissals, endpoints

**Files:**
- Create: `src/sharpit/engine/collectors/vulns/service.py`, `dismissals.py`
- Modify: adapter routes `GET /api/vulnerabilities`, `POST /api/vulnerabilities/scan`, `GET/POST/DELETE /api/dismissed-rules[/{rule_id:path}]`
- Test: `tests/engine/vulns/test_service.py`, `test_dismissals.py`, `tests/fastapi/test_vulns_api.py`

**Interfaces:**
- Consumes: Task 11, `SingleFlight`, `Masker`.
- Produces:
  - `class VulnerabilityService: __init__(settings, osv: OsvClient, epss: EpssClient, inventory: Callable[[], list[Package]]); report() -> dict` (cached or not-scanned DTO, never network); `scan() -> dict` (single-flight op `"vulnerabilities-scan"`, caches result, failure → report with `scan.status` failure + message, lock released).
  - `class DismissalStore: __init__(state_dir: Path); list() -> list[str]; add(rule_id) -> list[str]; remove(rule_id) -> list[str]` — file `sharpit.yml` created on first `add`, atomic write; YAML written as a minimal fixed format (`dismissed:\n  - "<id>"`), no YAML dependency.
  - rule id `f"{vuln_id}::pypi:{name}"`.

- [ ] **Step 1:** Tests: `test_get_never_network` (`no_side_effects`), `test_not_scanned_shape_matches_golden_keys`, `test_scan_report_shape_matches_golden_keys` (fake OSV fixture with 2 advisories), `test_ordering_as_bootui`, `test_epss_failure_keeps_osv`, `test_osv_failure_reports_status_and_releases_lock`, `test_concurrent_scan_409`, `test_scan_outlives_caller_and_caches` (fake OSV sleeps 2 s; caller abandons after 0.1 s; later `report()` has results), `test_caps_max_packages`, `test_dismiss_restore_roundtrip_file_created_lazily`, `test_dismissals_global_read_only_403`, `test_vulnerabilities_read_only_panel_blocks_scan`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: vulnerability scan service, dismissals and endpoints`.

### Task 13: Tool catalogue, CLI endpoints, MCP server and status panel

**Files:**
- Create: `src/sharpit/engine/tools.py`, `src/sharpit/engine/mcp.py`
- Modify: adapter routes `GET /api/cli`, `POST /api/cli/tools/{tool}`, `POST /api/mcp` (+ GET 405), `GET /api/mcp-server`, `POST /api/mcp-server/toggle`
- Test: `tests/engine/test_tools.py`, `tests/engine/test_mcp.py`, `tests/fastapi/test_mcp_api.py`, `tests/fastapi/test_cli_api.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Tool: name: str; description: str; input_schema: dict; panel: str | None; action: bool; handler: Callable[[SharpitContext, dict], dict]`
  - `TOOLS: tuple[Tool, ...]` = get_overview, get_config, get_mappings, get_loggers, get_beans, get_vulnerabilities_report (action False), vulnerabilities_scan (action True); names, descriptions and schemas verbatim from BootUI `McpToolSchema`/`BootUiMcpService` (only these tools).
  - `call_tool(ctx, name, args, *, via: Literal["mcp","cli"]) -> dict` — `via="mcp"` refuses action tools as unknown tool (-32601-equivalent per contract); caps applied (max_results, payload, response bytes in UTF-8, timeout with semaphore release).
  - `class McpServer: __init__(ctx); enabled: bool; handle(body: bytes, headers: Mapping[str,str]) -> tuple[int, dict | None, list[tuple[str,str]]]` covering every row of contract §9 "HTTP-level responses" and methods (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`, `prompts/list` → `[]`); `serverInfo.name == "sharpit"`.
  - CLI endpoints per contract §11 with status mapping.

- [ ] **Step 1:** Port `BootUiMcpServiceTests` and `AbstractMcpConformanceTest` cases (property names → env names). Add: `test_tools_list_has_no_action_tool`, `test_mcp_disabled_by_default` (contract disabled response), `test_toggle_enables_in_memory`, `test_get_mcp_405_allow_post`, `test_response_cap_counts_utf8_bytes`, `test_timeout_releases_semaphore`, `test_mcp_tools_no_side_effects` (each `get_*` under `no_side_effects`), `test_cli_scan_gated_by_read_only`, `test_cli_unknown_tool_status`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: read-only MCP server, CLI endpoints and tool catalogue`.

### Task 14: Cross-cutting safety suite and example app

**Files:**
- Create: `examples/fastapi_sample/app.py`, `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py`, `tests/test_conformance.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `examples/fastapi_sample/app.py::create_app() -> FastAPI` exercising every panel (settings model with a `SecretStr`, getenv calls incl. secret default, nested deps, middleware, websocket, static mount, catch-all), used by Task 15 (UI dev server) and Task 16.

- [ ] **Step 1:** `test_safety_matrix.py`: every row of spec §7.6 (parametrised path × peer × headers → expected status); spoofed XFF; inactive 404 matrix. `test_masking_corpus.py`: plant `SECRET_SENTINEL_9f3c` in env var values, a getenv default, a `SecretStr`, a middleware kwarg, a URL userinfo, and a JWT-shaped value under a harmless name; call every GET endpoint, every MCP tool and every CLI tool with `q` probes (`q=SENTINEL`, `q=9f3c`) and assert the sentinel and JWT never appear in any response body or captured log. `test_conformance.py`: for every endpoint with a golden fixture, the recursive key set of sharpit's response equals the golden's minus the documented deviations dict in the test file.
- [ ] **Step 2:** Run full suite in background → all PASS (fix any production bug found in the owning module, with its own test there). **Step 3:** Commit `test: safety matrix, masking corpus and conformance suite`.

### Task 15: UI (Svelte 5 + Vite + TypeScript)

**Files:**
- Create: `ui/package.json`, `ui/vite.config.ts` (base `./`, outDir `../src/sharpit/ui/static`, `build.modulePreload.polyfill=false`, no inline scripts), `ui/src/**`, `ui/tests/unit/**` (vitest), `ui/tests/e2e/**` (Playwright), `ui/README.md`
- Modify: `src/sharpit/ui/static/**` (build output, committed)

**Interfaces:**
- Consumes: the HTTP contract only (relative `api/...` URLs), example app from Task 14 for e2e.
- Produces: built assets with hashed names under `assets/`.

- [ ] **Step 1:** Load the `impeccable` and `frontend-design` skills; write `ui/DESIGN.md` (tokens: one accent, neutral scale, mono for values, light/dark) before components. The look must not reuse BootUI's palette/layout.
- [ ] **Step 2:** vitest unit tests first for: `api.ts` (relative URLs, 401 → token prompt state, 409 busy → message), `paging.ts` (server paging, page 200), `graph.ts` (nodes/edges from beans `dependencies`, focus neighbourhood), `palette.ts` (fuzzy match over panels, loggers, config keys). Run → FAIL; implement; → PASS.
- [ ] **Step 3:** Build the views for S00–S07 meeting spec §10 checks 1–9.
- [ ] **Step 4:** Playwright e2e against `examples/fastapi_sample` served by uvicorn on the leased port with sharpit's real CSP: one test per spec §10 check, plus `test_2000_row_table_stays_responsive` (filter keystroke → render < 100 ms), axe-core zero serious violations in light and dark; screenshots of every panel saved to `ui/tests/e2e/screenshots/` for the report.
- [ ] **Step 5:** `npm run build`; commit `feat: sharpit web UI` (source + built static).

### Task 16: Packaging, docs, dogfood on KliperMedia

**Files:**
- Modify: `README.md` (install, `sharpit.install(app)`, env table, safety model, deviations link)
- KliperMedia: local worktree `C:\development\github\klipermedia-sharpit-wt`, branch `local/sharpit-dogfood` (never pushed), `src/kliper/adapters/web/fastapi_app.py` (`create_app`)

- [ ] **Step 1:** `uv build` in background → wheel contains `sharpit/ui/static/index.html` and `sharpit/py.typed` (check with `python -m zipfile -l`). Install the wheel into a fresh venv with fastapi and run `examples/fastapi_sample` smoke (`GET /sharpit/api/overview` → 200).
- [ ] **Step 2:** KliperMedia: create worktree, `uv add --editable ../sharpit-mvp-wt` (local branch only), add `sharpit.install(app)` at the end of `create_app`. Lease the app port via agentctl. Start in background with `SHARPIT_PROFILE_VARS=KLIPER_ENV,SHARPIT_PROFILES` and KliperMedia's own local env, command `uv run uvicorn kliper.adapters.web.fastapi_app:create_app --factory --reload --port <leased>`.
- [ ] **Step 3:** Verify spec §11 done criteria with requests and a Playwright screenshot pass; then restart with `KLIPER_ENV=production` and assert 404 on `/sharpit/`, `/sharpit/api/overview`. Record findings (bugs → fix in sharpit with a test first) in `docs/reports/2026-10-31-dogfood-klipermedia.md`.
- [ ] **Step 4:** Stop the server by task id; release the lease. Commit sharpit changes only: `docs: README and KliperMedia dogfood report`.

### Task 17: Parity and morning report

**Files:**
- Modify: `replica/features.csv` (clone column), Create: `docs/reports/2026-10-31-mvp-summary.md`

- [ ] **Step 1:** Set `clone` for every row from evidence (tests/screens); run `python C:\development\github\replica-skill\replica-diff\parity.py replica/features.csv` → paste the score; every `must` row must be `yes`.
- [ ] **Step 2:** Full verification in background: `ruff check`, `ruff format --check`, `pyright`, `pytest` (count), `npm run build && git diff --exit-code`, Playwright. Paste the summary lines.
- [ ] **Step 3:** Write the summary: what shipped, test counts, parity score, deviations, dogfood findings, screenshots, open risks, coordinator's calls for the owner. Commit `docs: MVP summary report` and push `mvp`.

---

## Execution lanes

- Lane A (sequential, Claude subagents with review gates): Tasks 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14.
- Lane B (parallel after Task 6 lands, so the contract routes exist): Task 15 UI, developed against the sanitised fixtures through a Vite dev proxy to the example app as backend tasks land.
- Tasks 2/3 and 11 have no dependency on each other and may run in parallel lanes on separate worktrees, merged back by the coordinator.
- Then 16 → 17.
