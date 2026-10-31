# sharpit MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pip-installable `sharpit` package whose `sharpit.install(app)` gives a FastAPI app BootUI's local-only developer console (overview, config, mappings, loggers, beans/graph, vulnerabilities, read-only MCP, CLI endpoints) with a new Svelte UI at `/sharpit/`.

**Architecture:** A framework-neutral engine (`sharpit.engine`: pure functions and collectors, no Starlette imports) plus a thin FastAPI adapter that inserts one Starlette `Mount` at `app.router.routes[0]`. The engine ports BootUI's Java classes and their unit tests one for one; shapes come from `docs/reference/BOOTUI-CONTRACT-MVP.md`.

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
- Commits: conventional prefix (`feat:`, `test:`, `chore:`), no AI attribution of any kind. Task subagents never push. Only the coordinator pushes, and only the `mvp` branch to `origin` (the owner's goal requires the branch on ffroliva/sharpit). Nobody touches `master`, merges or publishes to PyPI.
- Env names follow one rule: `SHARPIT_` + the BootUI property with `bootui.` dropped and `.`/`-` → `_`, upper case (`bootui.vulnerabilities.osv-enabled` → `SHARPIT_VULNERABILITIES_OSV_ENABLED`); the dataclass field is the same name in lower case.
- Session cookie name is the constant `SESSION_COOKIE = "SHARPIT_SESSION"` in `engine/guard.py`; nothing else spells it.
- Durations accept `Ns`, `Nms` or a bare number of seconds.
- Long commands (full pytest, `uv build`, `npm run build`, Playwright) run in the background with a timeout and a log file.

## Review Focus

1. **A secret reaching any output through a side door** — error messages, `description`, `defaultValue`, MCP `structuredContent`, CLI tool output, `q` probing. Expectation: never. Pinned by Task 14's corpus test over every surface.
2. **sharpit active in production because a profile var is spelled differently** (`Production`, ` prod `, `prod,dev`). Expectation: disabled. Pinned in Task 4 (`test_disabled_profile_case_and_whitespace`).
3. **Large real apps** (KliperMedia: ~300 routes, 79 getenv keys, ~200 distributions): pages must stay ≤ 1000 items and the UI must not freeze. Pinned in Task 3 (`test_limit_clamped_to_1000`) and Task 15c's large-table check.
4. **A host app with its own middleware stack** (`TrustedHostMiddleware`, `CORSMiddleware`, auth middleware, SPA catch-all). Expectation: sharpit still reachable from localhost and unreadable cross-site. Pinned in Task 6 (`test_host_cors_wildcard_cannot_read`, `test_catch_all_does_not_shadow`, `test_host_trusted_host_middleware_with_localhost_allowed`).
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
src/sharpit/engine/collectors/{loggers,mappings,beans}.py
src/sharpit/engine/collectors/vulns/{inventory,cvss,osv,epss,interpreter,service,dismissals}.py
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
- Produces: `sharpit.__version__ = "0.1.0.dev0"`; fixture loader `tests/conftest.py::golden(name: str) -> dict`; pytest fixture `no_side_effects(tmp_state_dir)` that fails the test on any of: `socket.socket.connect`, `socket.create_connection`, `socket.getaddrinfo`, `socket.gethostbyname`; any change (files added, removed or modified) in the cwd tree or the state dir, compared by a before/after snapshot of paths + mtimes + sizes; any logger level different before vs after; any `os.environ` difference.

- [ ] **Step 1:** Write `pyproject.toml`: hatchling build, `name="sharpit"`, `requires-python=">=3.12"`, `dependencies=["starlette>=0.40","packaging>=23"]`, optional `test=["fastapi>=0.115","pydantic-settings>=2.4","uvicorn>=0.30","httpx","pytest","pytest-timeout"]`, ruff (line length 120), pyright strict on `src/sharpit`, pytest `testpaths=["tests"]`, `timeout=60`. Wheel includes `src/sharpit/ui/static/**`. Then run `uv sync --extra test --resolution lowest-direct`; if it fails to resolve or the tests fail at the floor, raise the floors (fastapi/starlette) until both pass and record the final floors in README.
- [ ] **Step 2:** `scripts/sanitize_golden.py <src_dir> <dst_dir>`: loads each `replica/evidence/golden/*.json` except `mcp.json` (empty) and `beans_view_graph.json` (duplicate of beans), keeps every item (no truncation, so `page` stays consistent), replaces values of an enumerated volatile list only (absolute paths → `"/path"`, hostnames → `"localhost"`, `bootUiVersion/frameworkVersion/javaVersion` → `"x"`, `startupTimeMillis`/`scannedAt` → `0`), and writes `meta.json` `{"bootui": "1.17.0", "app": "bootui-spring-sample-app", "profile": "dev", "captured": "2026-10-30"}`. Before writing, it walks every key and value recursively and aborts if any non-`"******"` value matches the secret patterns (JWT, PEM private key, AWS key id, URL userinfo) or sits under a sensitive key name.
- [ ] **Step 3:** Run it: `uv run python scripts/sanitize_golden.py replica/evidence/golden tests/fixtures/bootui`. Expected: panels, overview, config, mappings, loggers, beans, vulnerabilities, health written.
- [ ] **Step 4:** `tests/test_fixtures.py`: `test_golden_shapes_load` (each loads; `golden("overview")["activation"]["enabled"] is True`; for every fixture with `page`, `page.returned == len(items)` and `hasMore == offset+returned < matched`); `test_no_side_effects_blocks_socket`, `test_no_side_effects_detects_tempfile_write` (a `tempfile.NamedTemporaryFile(dir=cwd)` inside the fixture fails it), `test_no_side_effects_detects_dns`, `test_no_side_effects_detects_level_change`.
- [ ] **Step 5:** CI workflow: matrix 3.12/3.13/3.14 on ubuntu + windows-3.14; `uv sync --extra test`, `ruff check`, `ruff format --check`, `pyright`, `pytest`; one extra job with `--resolution lowest-direct`; job `ui` guarded by `if: hashFiles('ui/package-lock.json') != ''`: `npm ci && npm run build && git diff --exit-code src/sharpit/ui/static` in `ui/`.
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

- [ ] **Step 1:** Port every `@Test` from `bootui-core/.../SecretValueDetectorTests.java`, `bootui-engine/.../support/{SensitiveNamesTests,UriMaskingTests,CredentialRedactionTests,RelaxedNamesTests}.java` as parametrised pytest cases with identical inputs/outputs. `KeywordPatternMasker` has no upstream test class: derive one case per entry of its `DEFAULT_KEY_PATTERNS` and per `shouldMask` branch, marked `# derived: KeywordPatternMasker` (no oracle). Add sharpit cases: `test_secretstr_always_masked`, `test_metadata_only_hides_value`, `test_full_returns_raw`, `test_cache_key_prefix_masked_by_design` (`"cache.key-prefix"` → masked).
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
  - `Panel(id, title, action_capable: bool | None, api_prefix: str | None)`; `PANELS: tuple[Panel, ...]` = overview(None,None), config(False,"/config") (not action-capable in the MVP: overrides deferred, spec §8), mappings(False,"/mappings"), loggers(True,"/loggers"), beans(False,"/beans"), vulnerabilities(True,"/vulnerabilities"), mcp-server(True,"/mcp-server"), cli(None,None), in that order; titles from contract §1.
  - `panels_report(global_read_only: bool, panel_flags: Mapping[str, tuple[bool, bool]], available: Mapping[str, str | None]) -> dict` (`panel_flags[id] = (enabled, read_only)`, missing = `(True, False)`; `{"platform":"fastapi","panels":[...]}`; `available[id]` None = available, else the reason). Task 6 adapts `SharpitSettings` to these arguments.
  - `panel_for_api_path(sub_path: str) -> Panel | None` (prefix rule `p == prefix or p.startswith(prefix + "/")`).
  - `security_headers(kind: Literal["api","shell","asset"]) -> list[tuple[str, str]]` (CSP etc. verbatim + cache per kind).
  - `class SingleFlight: run(operation: str, fn: Callable[[], T], wait_timeout: float | None = None) -> T` — raises `ActionBusy(operation, active)` if another operation holds the lock; otherwise runs `fn` on a daemon worker thread, and if `wait_timeout` elapses raises `WaitTimeout` to the caller while the worker keeps running; the lock is released in the worker's `finally`. `ActionBusy.body() -> dict` per contract 409 shape.

- [ ] **Step 1:** Tests: `test_limit_clamped_to_1000` (limit=5000 → `page.limit==1000`), `test_limit_zero_clamped_to_1`, `test_negative_offset_zero`, `test_unbounded_limit_equals_matched`, `test_has_more`, `test_q_case_insensitive_trimmed`, `test_parse_int_rejects_abc`; panels: `test_registry_order_titles_and_action_capability` (full table incl. config not action-capable), `test_read_only_only_for_action_capable` (global read-only → overview and config readOnly False, loggers True with reason `"sharpit is read-only via SHARPIT_READ_ONLY=true"`), `test_mcp_not_under_mcp_server_prefix`; headers: exact CSP string; single-flight: `test_second_call_busy_409_body`, `test_lock_released_after_exception`, `test_lock_held_until_worker_finishes` (wait_timeout 0.05 on a 0.5 s fn → `WaitTimeout`, a second `run` → `ActionBusy`, after 0.6 s a `run` succeeds).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: paging, panel registry, security headers, single-flight`.

### Task 4: Settings and activation

**Files:**
- Create: `src/sharpit/settings.py`, `src/sharpit/engine/activation.py`, `src/sharpit/fastapi/__init__.py`, `src/sharpit/fastapi/signals.py`
- Test: `tests/test_settings.py`, `tests/engine/test_activation.py`, `tests/fastapi/test_signals.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class PanelSettings: enabled: bool = True; read_only: bool = False` (in `settings.py`).
  - `@dataclass(frozen=True) class SharpitSettings` with fields (defaults): `enabled: str="AUTO"`, `enabled_profiles=("dev","local","development")`, `disabled_profiles=("prod","production")`, `profile_vars=("SHARPIT_PROFILES","APP_ENV","ENVIRONMENT")`, `path="/sharpit"`, `api_path="/sharpit/api"`, `allow_non_localhost=False`, `allowed_hosts=()`, `trusted_proxies=()`, `trust_container_gateway="OFF"` (BootUI default, fail closed), `authentication_token: str | None=None`, `read_only=False`, `panels: Mapping[str, PanelSettings]` (`enabled=True, read_only=False`), `expose_values=Exposure.MASKED`, `mask_secrets=True`, `show_banner=True`, `state_dir=".sharpit"`, `config_scan: tuple[str,...] | bool = True`, `vulnerabilities_osv_enabled=True`, `vulnerabilities_request_timeout=10.0`, `vulnerabilities_max_packages=500`, `vulnerabilities_max_advisories=200`, `vulnerabilities_osv_base_uri="https://api.osv.dev"`, `vulnerabilities_epss_enabled=True`, `vulnerabilities_epss_base_uri="https://api.first.org"` (BootUI's base; the client appends `/data/v1/epss`), `mcp_enabled="OFF"`, `mcp_max_results=200`, `mcp_max_payload_bytes=1048576`, `mcp_max_concurrent_calls=20`, `mcp_execution_timeout=30.0`, `mcp_max_response_bytes=4194304`, `cli_enabled=True`, `cli_max_results`, `cli_max_concurrent_calls`, `cli_execution_timeout` (defaults from contract §10 properties table / BootUI `docs/PROPERTIES.md`), `warnings: tuple[str,...]=()`.
  - `load_settings(kwargs: Mapping[str, object], environ: Mapping[str, str]) -> SharpitSettings` — env names per the Global Constraints rule (panels: `SHARPIT_PANELS_<ID>_ENABLED` / `_READ_ONLY`, id `-`→`_`); lists comma-split; booleans true/false/yes/no/on/off/1/0; durations per Global Constraints. An invalid value takes the field's **fail-safe** value (not necessarily its default) and adds the warning `"Ignoring invalid SHARPIT_<X> value '<raw>'"`. Fail-safe table: `enabled`→disabled (BootUI reason), `read_only`→True, `expose_values`→MASKED, `mask_secrets`→True, `mcp_enabled`→OFF, `cli_enabled`→False, `allow_non_localhost`→False, `trust_container_gateway`→OFF, `show_banner`→True, numeric caps→their defaults. `ValueError` when `path` doesn't start with `/`, or when `api_path` is not `path` + `/` + one or more segments (so `/sharpitized/api` is rejected for `path=/sharpit`). When `expose_values` is FULL, add the warning `"SHARPIT_EXPOSE_VALUES=FULL exposes unmasked secrets"`.
  - `@dataclass(frozen=True) class ActivationStatus: enabled: bool; localhost_only: bool; reason: str; warnings: tuple[str,...]`; `to_dto() -> dict` (`{"enabled","localhostOnly","reason","warnings"}`).
  - `active_profiles(settings, environ) -> list[str]` (union over `profile_vars`, split, trimmed, lower-cased, de-duplicated in order).
  - `decide(settings: SharpitSettings, profiles: Sequence[str], dev_signal: str | None) -> ActivationStatus` (contract §10 order; `warnings` = `settings.warnings` + decision warnings; reasons with env names; step 5 reason `f"Enabled because a reloading development server was detected ({dev_signal})"`; step 6 `"Disabled: no enabled profile and no reloading development server detected"`).
  - `dev_server_signal(argv: Sequence[str]) -> str | None` in `fastapi/signals.py` (spec §7.4).

- [ ] **Step 1:** Port every case from `BootUiActivationConditionTests` and `BootUiActivationConditionAdditionalTests` (map property names to env names). Add: `test_disabled_profile_case_and_whitespace` (`APP_ENV=" Production "` → disabled), `test_union_of_profile_vars` (`APP_ENV=dev`, `ENVIRONMENT=production` → disabled), `test_bare_ENV_ignored`, `test_env_overrides_kwargs` (`kwargs enabled="ON"`, env `SHARPIT_ENABLED=OFF` → disabled), `test_empty_env_is_unset`, `test_invalid_enabled_disables` (reason `"Disabled: invalid SHARPIT_ENABLED value 'maybe'"`), `test_invalid_values_fail_safe` (parametrised over the fail-safe table), `test_expose_full_warns`, `test_warnings_reach_activation`, `test_gateway_trust_default_off`, `test_api_path_segment_boundary` (`/sharpit/api` ok, `/sharpit/x/api` ok, `/sharpitized/api` and `/api` rejected), `test_env_name_table` (every field's env name equals the Global Constraints rule applied to its BootUI property). Signals, exactly these 8: `[".../uvicorn/__main__.py","m:app","--reload"]` → `"uvicorn --reload"`; `[".../uvicorn/__main__.py","m:create_app","--factory","--reload","--port","8001"]` → `"uvicorn --reload"`; `[".../uvicorn/__main__.py","m:app","--reload","--workers","2"]` → `"uvicorn --reload"`; `[".../uvicorn/__main__.py","m:app","--workers","2"]` → None; `["fastapi","dev","main.py"]` → `"fastapi dev"`; `["C:\\venv\\Scripts\\fastapi.exe","dev"]` → `"fastapi dev"`; `["fastapi","run","main.py"]` → None; `["gunicorn","-k","uvicorn.workers.UvicornWorker","m:app"]` → None; plus `["main.py"]` → None (programmatic reload, not detected). `python -m fastapi dev` arrives as argv `[".../fastapi/__main__.py","dev"]` → `"fastapi dev"`.
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
  - `SESSION_COOKIE = "SHARPIT_SESSION"`.
  - `decide_guard(facts, settings, token: str | None, gateway: str | None) -> Denial | None` — order: source (skipped when allow_non_localhost) → host → cross-site on **every** method (message `"sharpit rejected a cross-site request."`) → token for untrusted sources on API paths (constant-time compare, bearer or `SESSION_COOKIE` cookie) → panel access.
  - `remote_access_configured(settings) -> bool`; `resolve_token(settings) -> tuple[str | None, bool]` (token, generated?) using `secrets.token_urlsafe(32)`.
  - `detect_container_gateway(route_file: Path = Path("/proc/net/route"), in_container: Callable[[], bool] = ...) -> str | None` — port BootUI's gateway rule: only when running in a container (`/.dockerenv` or `/run/.containerenv` exists), parse the default route's little-endian hex gateway; never DNS; None elsewhere (Windows/macOS). Called lazily by Task 6 and memoised.

- [ ] **Step 1:** Port the `LocalhostGuardTests.java` cases that exercise `LocalhostGuard.decide`/`extractRequestHost` inputs and outputs, each with `# ported:` and the Java method name. Before porting, write the case list into the test module's docstring with one of three labels per Java test: **same** (expected outcome unchanged), **inverted** (sharpit deviation: every test that allows a cross-site request on a safe method now expects 403; every cross-site message expects `"sharpit rejected a cross-site request."`), **dropped** (with reason: `autoTrustsDockerDesktopGatewayAlongsideRouteTableGateway` and any test needing DNS → not supported, spec §7.5; tests of servlet request scoping → covered by Task 6 ASGI tests). `ApiAuthenticationFilterTests` are servlet-filter tests: port their decision cases (trusted source needs no token, bearer, cookie, constant-time compare, wrong token) here and their HTTP cases (401 body + headers, `auth/session`) in Task 6. Add: `test_xff_with_no_trusted_proxies_is_untrusted` (peer `127.0.0.1` + `x-forwarded-for: 127.0.0.1` → 403 source message), `test_cross_site_get_rejected` (GET + `sec-fetch-site: cross-site` → 403), `test_origin_mismatch_get_rejected`, `test_same_origin_vite_port_allowed` (Origin `http://localhost:5173`, Host `localhost:8000` → allowed), `test_panel_disabled_all_methods_403_body`, `test_dismissed_rules_global_read_only`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS. **Step 5:** Commit `feat: port LocalhostGuard and API guards`.

### Task 6: FastAPI adapter skeleton: install, mount, guard middleware, shell, auth, panels, overview

**Files:**
- Create: `src/sharpit/fastapi/adapter.py`, `src/sharpit/fastapi/http.py`, `src/sharpit/engine/spi.py`, `src/sharpit/engine/collectors/__init__.py`, `src/sharpit/engine/collectors/overview.py`, `src/sharpit/fastapi/introspector.py` (only `app_info()` in this task), `src/sharpit/ui/static/index.html` (placeholder until Task 15)
- Modify: `src/sharpit/__init__.py` (re-export `install`)
- Test: `tests/fastapi/test_install.py`, `tests/engine/test_overview.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces:
  - `install(app, *, settings: Sequence[object] = (), **options) -> SharpitHandle` — reads `load_settings(options, os.environ)`, `decide(...)`, inserts a `SharpitMount(path, app=sub_app, name="sharpit")` at `app.router.routes[0]`. `SharpitMount` subclasses Starlette `Mount` and overrides its compiled path regex to `^{path}(?:/(?P<path>.*))?$` so the **bare** `{path}` (any method) also reaches the sub-app and its guard (a plain `Mount` never receives it; the host router would redirect or a host catch-all would answer). It registers a lifespan-start hook by wrapping `app.router.lifespan_context` (the original is kept as `handle.original_lifespan` for Task 10) that records startup ms; logs one INFO line `sharpit inactive: <reason>` when inactive; when active and `show_banner`, prints the banner to stderr, including the generated token if any; when `expose_values` is FULL, logs a WARNING.
  - Inactive response: 404 with the host framework's not-found shape (`{"detail":"Not Found"}` JSON for a FastAPI host), no sharpit headers, for every method and every path including the bare `{path}`.
  - Host middleware (e.g. `TrustedHostMiddleware`, auth middleware) wraps the mount and stays authoritative; README documents adding `localhost` to the host's allowed hosts. sharpit does not try to bypass it.
  - `class SharpitHandle: settings; activation: ActivationStatus; context: SharpitContext; original_lifespan` (for tests).
  - `class SharpitContext` holding settings, activation, introspector, masker, token, single-flight, lazy caches, and `app_settings: tuple[object, ...]` (the `settings=` objects passed to `install`, read by Task 7c); `context.lazy(key: str, factory: Callable[[], T]) -> T` (memoised, thread-safe).
  - `spi.AppIntrospector` Protocol: `app_info() -> AppInfo`, `routes() -> list[RouteInfo]`, `providers() -> list[ProviderInfo]`; `AppInfo(title: str | None, framework: str, framework_version: str | None, docs_url: str | None)`; `RouteInfo` / `ProviderInfo` dataclasses defined here with the fields Tasks 9 and 10 fill (see those tasks).
  - `http.json_response(data, status=200) -> Response` (nulls kept, `security_headers("api")`); `http.error(status, message, **extra)`.
  - Routes in the sub-app (API routes derived from `api_path` relative to `path`, never hard-coded `/api`): bare `{path}` GET→307 `{path}/` (after the guard); `GET "/"` shell (`no-cache`); `/assets/{file}` (immutable); `POST /api/auth/session`; `GET /api/panels`; `GET /api/overview`. Inactive sub-app: one catch-all route returning 404 for every method.
  - `overview_dto(ctx, scope) -> dict` (spec §8 Overview, every OverviewDto key; `serverPort` is None when `scope.get("server")` is missing).

- [ ] **Step 1:** Tests with `fastapi.testclient.TestClient(app, client=("127.0.0.1", 50000))`: `test_inactive_404_every_path_and_method` (GET/POST/DELETE on `/sharpit`, `/sharpit/`, `/sharpit/api/overview`, `/sharpit/api/nope`; body equals the host's own 404 body for `/definitely-not-a-route`), `test_bare_path_goes_through_guard` (active; `GET /sharpit` with `Host: evil.example` → 403, not a host redirect), `test_redirect_to_trailing_slash`, `test_shell_served_with_csp_and_no_cache`, `test_overview_shape_matches_golden_keys` (`set(resp) == set(golden("overview"))`, `frameworkName=="FastAPI"`, `webApplicationType=="ASGI"`, `managementPort is None`), `test_panels_platform_fastapi_and_ids`, `test_catch_all_does_not_shadow` (host route `/{p:path}` added before install; both `/sharpit` and `/sharpit/api/overview` reach sharpit), `test_custom_paths` (`path="/dev/console"`, `api_path="/dev/console/rest"` → overview at `/dev/console/rest/overview`, cookie Path follows), `test_host_cors_wildcard_cannot_read` (host `CORSMiddleware(allow_origins=["*"])`, GET overview with `Origin: https://evil.example` → 403), `test_host_trusted_host_middleware_with_localhost_allowed` (host `TrustedHostMiddleware(allowed_hosts=["localhost"])` → overview 200), `test_remote_needs_token_and_session_cookie` (allow_non_localhost, client `10.0.0.5`: 401 body `{"error":"sharpit authentication required"}` with `WWW-Authenticate: Bearer realm="sharpit"` and `Cache-Control: no-store`; `POST auth/session` with bearer → 204 and `Set-Cookie` starting `SHARPIT_SESSION=` with `Path=/sharpit/api; HttpOnly; SameSite=Strict`, plus `Secure` when the request scheme is https; next GET with cookie → 200; wrong token → 401), `test_xff_spoof_through_uvicorn_proxy_headers` (app wrapped in `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware(trusted_hosts="*")`, client 10.0.0.5, `X-Forwarded-For: 127.0.0.1` → 403), `test_startup_time_set_after_lifespan`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (sub-app = `Starlette(routes=..., middleware=[Middleware(GuardMiddleware, ctx=ctx)])`; GuardMiddleware builds `RequestFacts` from `scope` and calls `decide_guard`). **Step 4:** Run → PASS. **Step 5:** Commit `feat: FastAPI install, guard middleware, panels and overview`.

### Task 7a: Config inputs — dotenv parser and getenv scan

**Files:**
- Create: `src/sharpit/engine/collectors/config/__init__.py` (empty for now), `dotenv.py`, `getenv_scan.py`
- Test: `tests/engine/config/test_dotenv.py`, `test_getenv_scan.py`, fixtures `tests/fixtures/getenv_corpus/`

**Interfaces:**
- Produces:
  - `parse_dotenv(text: str) -> dict[str, str]` (python-dotenv grammar: `export ` prefix, single/double quotes, `\n` escapes in double quotes, `#` comments outside quotes, `${VAR}` expansion from earlier keys/environ in double-quoted and unquoted values).
  - `@dataclass class GetenvFinding: key: str; default: str | None; location: str`; `scan_packages(roots: Sequence[Path]) -> list[GetenvFinding]` (spec §8 item 3 forms; skip `.venv`, `venv`, `node_modules`, `__pycache__`, `site-packages`, files > 1 MB, syntax errors).

- [ ] **Step 1:** Tests: dotenv grammar table (10 rows); getenv corpus: a fixture package with all 5 supported forms, a dynamic key (ignored), a syntax-error file (skipped), a 1.1 MB file (skipped), a `.venv` dir (skipped) → exact expected findings list.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat: dotenv parser and getenv scanner`.

### Task 7b: Config inputs — pydantic-settings provenance

**Files:**
- Create: `src/sharpit/engine/collectors/config/settings_source.py`
- Test: `tests/engine/config/test_settings_source.py`

**Interfaces:**
- Produces:
  - `@dataclass class ConfigEntry: name: str; value: object; source: str; description: str | None; default: object; secret_typed: bool`
  - `settings_entries(instance: object, environ: Mapping[str,str]) -> tuple[list[ConfigEntry], list[str]]` (entries, source names in precedence order); `([], [])` when pydantic-settings is not installed or the object is not a `BaseSettings`.
  - Algorithm: for the instance's class, evaluate each source separately in pydantic-settings order — `EnvSettingsSource(cls)()`, `DotEnvSettingsSource(cls)()` (the model's `env_file`), `SecretsSettingsSource(cls)()` (when `secrets_dir` set) — and the winner for a field is the first source whose result contains it (`systemEnvironment`, `dotenv: <path>`, `secrets: <dir>`). If none contains it: `default (<ClassName>)` when the instance value equals the field default, else `init (<ClassName>)`. A class that overrides `settings_customise_sources` gets source `settings (<ClassName>)` for every field (provenance not inferred; logged in §14 as known limit). Name = env name from `env_prefix` + field name or alias, upper-cased unless `case_sensitive`.

- [ ] **Step 1:** Tests: `env_prefix="APP_"`; field with `validation_alias`; `SecretStr` (`secret_typed` True); `env_file` → `dotenv: <path>`; `secrets_dir` → `secrets: <dir>`; `env_nested_delimiter="__"` with a nested model → `APP_DB__HOST`; constructor kwarg → `init (Settings)`; untouched field → `default (Settings)`; custom `settings_customise_sources` → `settings (Settings)`; pydantic-settings absent (monkeypatched import) → `([], [])`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: pydantic-settings provenance`.

### Task 7c: Config report and route

**Files:**
- Modify: `src/sharpit/engine/collectors/config/__init__.py` (`config_report`), `src/sharpit/fastapi/adapter.py` (route `GET {api}/config`)
- Test: `tests/engine/config/test_config_report.py`

**Interfaces:**
- Consumes: 7a, 7b, `Masker`, `paged`, `canonicalize`.
- Produces: `config_report(ctx, q, source, overrides_only, offset, limit) -> dict` — ConfigReport per contract §3: masking first (value **and** defaultValue), then filter (`q` via `canonicalize` on name, or substring on displayed value/description/defaultValue), then `paged`; properties sorted by name; `overrideCount` 0; `override` False; `origin` null; `propertySuggestions` = getenv/settings keys with no value anywhere, masked defaults, filtered by `q` on name (relaxed) or description as BootUI does. Settings objects come from `ctx.app_settings`. Scan root default = top-level package of the module that called `install()` (captured in `install` via `sys._getframe(1).f_globals["__name__"]`), resolved lazily through `importlib.util.find_spec`.

- [ ] **Step 1:** Port all 9 `ConfigServiceTests` cases (override-related expectations become `overrideCount == 0` / `override False`), incl. `queryMatchesMaskedValueNeverRevealingSecret`, `relaxedNameMatchingDoesNotWidenValueOrMetadataMatching`, `metadataOnlyExposureHidesAllValues`. Add: `test_secret_default_masked` (`os.getenv("JWT_SECRET","dev-secret")` → suggestion `defaultValue=="******"`), `test_q_cannot_probe_masked_value` (`API_TOKEN=abc123`, `q=abc1` → `matched==0`), `test_relaxed_q` (`q=my-prop` matches `MY_PROP`), `test_source_filter_exact`, `test_shape_matches_golden_keys`, `test_dotenv_in_cwd_not_reported`, `test_config_get_no_side_effects`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: config panel with provenance and masking`.

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
- Produces: `ProviderInfo(name: str, type_name: str, scope: Literal["request","singleton"], resource: str | None, dependencies: tuple[str,...], classification: Literal["APPLICATION","FRAMEWORK","PLATFORM","OTHER"], overridden_by: str | None)`; `beans_report(ctx, q, classification, offset, limit) -> dict` (shape per contract §6; `aliases` always present, `[]` when none; keys exactly BeanSummary's — `overridden_by` is rendered into an existing text field per the contract, chosen by the implementer and recorded in the Task 14 conformance deviations dict if it needs a new key). Classification: stdlib module → PLATFORM, under site-packages → FRAMEWORK, `sharpit.*` → BOOTUI (the UI probes `classification=BOOTUI`), else APPLICATION. The lifespan bean is `handle.original_lifespan`, never sharpit's wrapper.

- [ ] **Step 1:** Tests: two `get_db` functions in different modules → distinct names; `OAuth2PasswordBearer` instance → class qualname; two instances of one class → second gets `#2`; nested `Depends` edges; router- and app-level dependencies included; `SessionMiddleware(secret_key="s3cr3t")` → bean present, `"s3cr3t"` appears nowhere in the JSON; `dependency_overrides` → override is the bean and carries `overridden_by`; `test_lifespan_bean_is_host_lifespan`; `test_classification_bootui_filter`; `test_every_dependency_resolves_to_a_bean`; `test_classification_application_vs_framework`; `test_shape_matches_golden_keys`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: beans panel with dependency edges`.

### Task 11: Vulnerabilities — inventory, CVSS, OSV/EPSS clients

**Files:**
- Create: `src/sharpit/engine/collectors/vulns/{__init__,inventory,cvss,osv,epss}.py`
- Test: `tests/engine/vulns/test_inventory.py`, `test_cvss.py`, `test_osv.py`, `test_epss.py`, recorded fixtures `tests/fixtures/osv/*.json`, `tests/fixtures/epss/*.json`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Package: name: str (normalised); version: str; location: str | None`; `inventory() -> list[Package]` (spec §8 dedupe/skip rules).
  - `cvss3_base_score(vector: str) -> float | None` (port `CvssV3BaseScore`), `severity_for(score: float | None) -> str` (BootUI thresholds).
  - `@dataclass class QueryResult: ids: dict[Package, list[str]]; failed: list[Package]; truncated: bool`; `class OsvClient: __init__(base_uri, timeout, opener=urllib.request.build_opener()); querybatch(pkgs: Sequence[Package]) -> QueryResult` (chunks of 1000, follows `next_page_token` up to 20 pages per query then `truncated=True`, a failed chunk lands in `failed`); `vuln(id: str) -> dict`.
  - `class EpssClient: scores(cve_ids: Sequence[str]) -> dict[str, tuple[float, float]]` (chunking and pagination validation as BootUI; any failure → `{}`).
  - `interpreter.py`: port `OsvAdvisoryInterpreter` — `interpret(advisory: dict, pkg: Package, requested_id: str) -> Finding | None` handling ECOSYSTEM range events, `fixedVersions`/`fixAvailable` via `packaging.version`, severity source order, `withdrawn` (→ None), id mismatch (→ None), evidence limitations; `Finding` fields = the contract §8 finding DTO.
  Clients take an injectable `opener` so tests pass a fake; no test touches the network.

- [ ] **Step 1:** Port `CvssV3BaseScore` tests and all `OsvAdvisoryInterpreterTests` cases (~30; Maven versions rewritten as PyPI versions, ordering via `packaging.version`). From `OsvVulnerabilityScannerTests` (spring-autoconfigure, 47 cases) port every interpretation, chunking, pagination and EPSS case, citing each; mark Maven-coordinate cases **adapted** with the PyPI input and expected output written out; mark JVM-only cases **dropped** with the reason in the module docstring. Recorded PyPI fixtures under `tests/fixtures/osv/` (querybatch response, two advisories: one with a fix, one withdrawn) and `tests/fixtures/epss/`. Inventory: fake `distributions()` with a duplicate, a versionless dist and `sharpit` → deduped/skipped. OSV: request body exactly `{"queries":[{"package":{"name":"jinja2","ecosystem":"PyPI"},"version":"3.1.2"}]}`; timeout raises `OsvError`; `test_pagination_truncated`; `test_failed_chunk_reported`. EPSS: malformed response → `{}`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: vulnerability inventory, CVSS and OSV/EPSS clients`.

### Task 12: Vulnerabilities — scan service, report, dismissals, endpoints

**Files:**
- Create: `src/sharpit/engine/collectors/vulns/service.py`, `dismissals.py`
- Modify: adapter routes `GET /api/vulnerabilities`, `POST /api/vulnerabilities/scan`, `GET/POST/DELETE /api/dismissed-rules[/{rule_id:path}]`
- Test: `tests/engine/vulns/test_service.py`, `test_dismissals.py`, `tests/fastapi/test_vulns_api.py`

**Interfaces:**
- Consumes: Task 11, `SingleFlight`, `Masker`.
- Produces:
  - `class VulnerabilityService: __init__(settings, osv: OsvClient, epss: EpssClient, inventory: Callable[[], list[Package]], dismissals: DismissalStore, single_flight: SingleFlight); report() -> dict` (cached or not-scanned DTO with dismissals applied, never network); `scan(wait_timeout: float | None = None) -> dict` (single-flight op `"vulnerabilities-scan"`; statuses SCANNED / PARTIAL (some chunks failed or truncated) / ERROR / DISABLED with BootUI's messages, PyPI-worded; caches SCANNED/PARTIAL/ERROR; DISABLED when `vulnerabilities_osv_enabled` is false is returned but **not cached**).
  - `class DismissalStore: __init__(state_dir: Path); list() -> list[str]; add(rule_id) -> list[str]; remove(rule_id) -> list[str]` — rule ids validated against `^[A-Za-z0-9._:-]+::pypi:[a-z0-9._-]+$` (else `BadRequest`); file `sharpit.yml` in BootUI's `boot-ui.yml` format (header comment renamed to sharpit, `dismissedRules:` list), other lines preserved, created on first `add`, atomic write via temp + `os.replace`; no YAML dependency (read/write only that list).
  - rule id `f"{vuln_id}::pypi:{name}"`.

- [ ] **Step 1:** Tests: `test_get_never_network` (`no_side_effects`), `test_not_scanned_shape_matches_golden_keys`, `test_scan_report_shape_matches_golden_keys` (fake OSV fixture with 2 advisories), `test_ordering_as_bootui`, `test_epss_failure_keeps_osv`, `test_osv_failure_reports_status_and_releases_lock`, `test_partial_on_failed_query`, `test_disabled_not_cached`, `test_concurrent_scan_409`, `test_scan_outlives_caller_and_caches` (fake OSV sleeps 2 s; `scan(wait_timeout=0.1)` raises `WaitTimeout`; later `report()` has results), `test_caps_max_packages`, `test_dismissed_applied_to_report` (finding `dismissed=true`; `vulnerabilityCount`, `highestSeverity`, `vulnerable`, `severityCounts` (always 6 entries) and `scan.vulnerabilitiesFound` recomputed from active findings; restoring reverts them), `test_dismiss_restore_roundtrip_file_created_lazily`, `test_dismiss_rejects_bad_ids` (quote, newline, backslash, no `::pypi:` → 400, file unchanged), `test_dismissal_file_preserves_other_lines`, `test_dismissals_global_read_only_403`, `test_vulnerabilities_read_only_panel_blocks_scan`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: vulnerability scan service, dismissals and endpoints`.

### Task 13: Tool catalogue, CLI endpoints, MCP server and status panel

**Files:**
- Create: `src/sharpit/engine/tools.py`, `src/sharpit/engine/mcp.py`
- Modify: adapter routes `GET /api/cli`, `POST /api/cli/tools/{tool}`, `POST /api/mcp` (+ GET 405), `GET /api/mcp-server`, `POST /api/mcp-server/toggle`
- Test: `tests/engine/test_tools.py`, `tests/engine/test_mcp.py`, `tests/fastapi/test_mcp_api.py`, `tests/fastapi/test_cli_api.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class CallContext: ctx: SharpitContext; scope: Mapping[str, object]` (the HTTP request scope, so `get_overview` fills `serverPort`/`contextPath` as spec §8).
  - `@dataclass(frozen=True) class Tool: name: str; description: str; input_schema: dict; panel: str | None; action: bool; handler: Callable[[CallContext, dict], dict]`
  - `TOOLS: tuple[Tool, ...]` = get_overview, get_config, get_mappings, get_loggers, get_beans, get_vulnerabilities_report (action False), vulnerabilities_scan (action True); names, descriptions and schemas verbatim from BootUI `McpToolSchema`/`BootUiMcpService` (only these tools).
  - `call_tool(call: CallContext, name, args, *, via: Literal["mcp","cli"]) -> dict` — `via="mcp"` treats action tools as unknown: JSON-RPC `-32602` with message `"Unknown tool: vulnerabilities_scan"` (-32601 stays for unknown **methods**); caps applied per `via` (MCP vs CLI settings: max_results, payload, response bytes in UTF-8, concurrency, timeout via `SingleFlight`-style worker with semaphore release).
  - `class McpServer: __init__(ctx); enabled: bool; handle(body: bytes, headers: Mapping[str,str], scope) -> tuple[int, dict | None, list[tuple[str,str]]]` covering every row of contract §9 "HTTP-level responses" and methods (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `ping`, `prompts/list`, `prompts/get`); prompts and `instructions` ported from BootUI `McpGuidance`/`McpPrompt` with names substituted; unknown prompt → `-32602 "Unknown prompt: <name>"`; `serverInfo.name == "sharpit"`.
  - CLI endpoints per contract §11 with its status DTO and status mapping, independent of whether MCP is enabled.
  - `GET mcp-server` lists only the tools exposed over MCP (`action=False`, 6); `toolCount == 6`.

- [ ] **Step 1:** Port `BootUiMcpServiceTests` and `AbstractMcpConformanceTest` cases (property names → env names), each cited. Add: `test_tools_list_has_no_action_tool`, `test_mcp_call_action_tool_unknown_32602`, `test_unknown_method_32601`, `test_prompts_list_and_get`, `test_prompts_get_unknown`, `test_mcp_disabled_by_default` (contract disabled response), `test_toggle_enables_in_memory`, `test_get_mcp_405_allow_post`, `test_response_cap_counts_utf8_bytes`, `test_timeout_releases_semaphore`, `test_overview_tool_uses_request_scope`, `test_mcp_tools_no_side_effects` (each `get_*` under `no_side_effects`). CLI, one table-driven test over every contract §11 outcome: OK 200, disabled 503 + body, unknown tool, invalid args 400, panel disabled/read-only 403, busy 409, capacity 429, timeout 504; `test_cli_status_shape_matches_contract`; `test_cli_works_with_mcp_disabled`; `test_cli_scan_gated_by_read_only`.
- [ ] **Step 2–4.** **Step 5:** Commit `feat: read-only MCP server, CLI endpoints and tool catalogue`.

### Task 14: Cross-cutting safety suite and example app

**Files:**
- Create: `examples/fastapi_sample/app.py`, `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py`, `tests/test_conformance.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `examples/fastapi_sample/app.py::create_app() -> FastAPI` exercising every panel (settings model with a `SecretStr`, getenv calls incl. secret default, nested deps, middleware, websocket, static mount, catch-all), used by Task 15 (UI dev server) and Task 16.

- [ ] **Step 1:** `test_safety_matrix.py`: every row of spec §7.6 (parametrised path × peer × headers → expected status); spoofed XFF; inactive 404 matrix incl. bare path; `test_every_get_no_side_effects` parametrised over **every** GET route read from the sub-app's own route table (so a new route cannot escape it). `test_masking_corpus.py` plants the sentinel `S3NT1NEL9f3c` as: the value of `API_TOKEN` and `DB_PASSWORD` (sensitive names), a URL userinfo under harmless `DATABASE_URL` (`postgres://u:S3NT1NEL9f3c@h/db`), a JWT-shaped value under harmless `FOO_VALUE`, the getenv default of `JWT_SECRET`, a `SecretStr` field, and a `SessionMiddleware(secret_key=...)` kwarg. It then calls every route (GET and the error paths: 400/401/403/404/409), every MCP tool, every CLI tool, with `q` probes (`q=S3NT1NEL`, `q=9f3c`), and asserts the sentinel and the JWT appear in no response body, header or captured log record. Token: `test_generated_token_printed_once_to_stderr_not_logged` (capsys has it once, caplog never) and `test_configured_token_never_printed`. `test_conformance.py`: for every MVP endpoint with a golden fixture (not `health.json`, a non-goal), the recursive key set of sharpit's response equals the golden's minus the documented deviations dict in the test file. `test_install_budget` (median of 5 `install()` on `create_app()` ≤ 50 ms with sockets blocked).
- [ ] **Step 2:** Run full suite in background → all PASS (fix any production bug found in the owning module, with its own test there). **Step 3:** Commit `test: safety matrix, masking corpus and conformance suite`.

### Task 15a: UI foundation (after Task 6)

**Files:**
- Create: `ui/package.json` (+ lock), `ui/vite.config.ts` (base `./`, outDir `../src/sharpit/ui/static`, `build.modulePreload.polyfill=false`, no inline scripts), `ui/DESIGN.md`, `ui/src/lib/{api,paging,graph,palette}.ts`, `ui/tests/unit/**`

**Interfaces:**
- Consumes: the HTTP contract (relative `api/...` URLs) and `tests/fixtures/bootui/*.json` as unit-test data.
- Produces: `api.ts` (`get<T>(path, params) -> Promise<T>`, `post`, `del`; `ApiError {status, body}`; 401 → `authRequired` store; 409 busy → `busyMessage`), `paging.ts` (`ServerPage<T>` with page size 200), `graph.ts` (`buildGraph(beans) -> {nodes, edges}`, `neighbourhood(graph, id, depth=1)`), `palette.ts` (`search(index, query) -> Hit[]`).

- [ ] **Step 1:** Load the `impeccable` and `frontend-design` skills when the harness provides them (Claude Code: `Skill` tool); without them, follow `ui/DESIGN.md` alone. Write `ui/DESIGN.md` first: tokens (one accent, neutral scale, mono for values, light/dark), density, type scale; it must not reuse BootUI's palette or layout.
- [ ] **Step 2:** vitest tests first for the four modules (relative URLs; 401/409 handling; paging maths; graph from golden beans has one edge per `dependencies` entry; palette ranks exact prefix above fuzzy). FAIL → implement → PASS. Commit `feat(ui): design tokens and client foundations`.

### Task 15b: UI views (after Task 15a; panels wired as Tasks 7–13 land)

**Files:** `ui/src/App.svelte`, `ui/src/views/*.svelte`, `ui/src/components/*.svelte`, build output under `src/sharpit/ui/static/`

- [ ] **Step 1:** Build S00–S07 meeting spec §10 checks 1–8 using 15a modules; component tests in vitest for the token prompt and the vulnerabilities state machine (never-scanned → scanning → results / busy / failed / dismissed).
- [ ] **Step 2:** `npm run build` in background; commit `feat(ui): sharpit views` (source + built static).

### Task 15c: UI end-to-end (after Task 14)

**Files:** `ui/playwright.config.ts`, `ui/tests/e2e/**`

- [ ] **Step 1:** Lease the app port and a browser session via agentctl; serve `examples/fastapi_sample` with uvicorn in background (sharpit's real CSP). One Playwright test per spec §10 check 1–9; axe-core zero serious/critical violations in light and dark; `test_large_table_filter_responsive`: with 1,000 loggers in the example app, type a filter and assert the row count updates within 1 s, measured with `performance.now()` around the keystroke over 5 runs, median reported (no hard sub-frame thresholds). Save screenshots of every panel to `ui/tests/e2e/screenshots/`.
- [ ] **Step 2:** Stop the server by task id, release leases; commit `test(ui): end-to-end checks and screenshots`.

### Task 16: Packaging, docs, dogfood on KliperMedia

**Files:**
- Modify: `README.md` (install, `sharpit.install(app)`, env table, safety model, deviations link)
- KliperMedia: local worktree `C:\development\github\klipermedia-sharpit-wt`, branch `local/sharpit-dogfood` (never pushed), `src/kliper/adapters/web/fastapi_app.py` (`create_app`)

- [ ] **Step 1:** `uv build` in background → wheel contains `sharpit/ui/static/index.html` and `sharpit/py.typed` (check with `python -m zipfile -l`). Install the wheel into a fresh venv with fastapi and run `examples/fastapi_sample` smoke (`GET /sharpit/api/overview` → 200).
- [ ] **Step 2:** KliperMedia: create worktree, `uv add --editable ../sharpit-mvp-wt` (local branch only), add `sharpit.install(app)` at the end of `create_app`. Lease the app port via agentctl. Start in background with `SHARPIT_PROFILE_VARS=KLIPER_ENV,SHARPIT_PROFILES`, `localhost` added to `KLIPER_ALLOWED_HOSTS`, and KliperMedia's own local env, command `uv run uvicorn kliper.adapters.web.fastapi_app:create_app --factory --reload --port <leased>`. **Stop condition:** if KliperMedia cannot start without external services or secrets that only the owner has, record exactly what is missing in the report and skip to Step 4.
- [ ] **Step 3:** Verify spec §11 done criteria with requests and a Playwright screenshot pass. Stop that server by its task id. Start a second one with `KLIPER_ENV=production`, assert 404 on `/sharpit`, `/sharpit/`, `/sharpit/api/overview`, stop it by task id. Record findings (bugs → fix in sharpit with a test first) in `docs/reports/2026-10-31-dogfood-klipermedia.md`.
- [ ] **Step 4:** Confirm no server is left running; release the lease. Commit sharpit changes only: `docs: README and KliperMedia dogfood report`. The KliperMedia worktree stays local and unpushed (kept for the owner to inspect; listed in the morning report).

### Task 17: Parity and morning report

**Files:**
- Modify: `replica/features.csv` (clone column), Create: `docs/reports/2026-10-31-mvp-summary.md`

- [ ] **Step 1:** Set `clone` for every row from evidence (tests/screens); run `python C:\development\github\replica-skill\replica-diff\parity.py replica/features.csv` → paste the score; every `must` row must be `yes`.
- [ ] **Step 2:** Full verification in background: `ruff check`, `ruff format --check`, `pyright`, `pytest` (count), `npm run build && git diff --exit-code`, Playwright. Paste the summary lines.
- [ ] **Step 3:** Write the summary: what shipped, test counts, parity score, deviations, dogfood findings, screenshots, open risks, coordinator's calls for the owner. Commit `docs: MVP summary report`. The coordinator pushes `mvp` to origin (never `master`).

---

## Execution lanes

- Lane A (sequential, subagents with review gates): 1 → 2 → 3 → 4 → 5 → 6 → 7a → 7b → 7c → 8 → 9 → 10 → 12 → 13 → 14.
- Lane C (parallel after Task 3): Task 11 (no adapter dependency), merged by the coordinator before Task 12.
- Lane B (parallel after Task 6): 15a, then 15b as panel routes land; 15c after Task 14.
- Then 16 → 17. The coordinator alone pushes `mvp`.
