# Lane B-fastapi-security: `fastapi-security` (BootUI `spring-security`, static, best effort)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development, one task at a time,
> `/sharpit:check` before every commit. **No code before Task 0's council verdict.**

| | |
|---|---|
| **Lane id** | `B-fastapi-security` (worktree `...\0.4.0-B-fastapi-security`, branch `lane/0.4.0-B-fastapi-security`); best effort |
| **Goal** | BootUI's three Spring Security views for a FastAPI app — middleware "chain", auth scheme types, endpoint × security rule, and `explain` — read statically from route and middleware objects, never calling a dependency. |
| **Spec** | §2 (Wave B needs predict + high-tier council), §4 (no GET calls user code), §6.1, §6.2 (rename), §8 intro, §8.1 row `fastapi-security`, §11 ("static on GET") |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §3; BootUI `SpringSecurityService.java`, `SpringSecurityReport`, `SpringSecurityFilterChainDto`, `SpringSecurityAuthDto`, `SpringSecurityExplainDto`, `SpringSecurityEndpointsReport`, `SpringSecurityEndpointDto` |
| **Worker** | M, security lane → claude-flavio (Opus); reviewer another family + `ponytail-review` (introspection) |
| **Depends on** | F, D1 |
| **May touch** | `src/sharpit/engine/collectors/appsecurity.py` (new), `src/sharpit/engine/spi.py` (append `SecurityModel` dataclasses only), `src/sharpit/fastapi/introspector.py` (new method `security_model()`), `src/sharpit/fastapi/routes/fastapi_security.py` (F stub), the panel's pre-registered rows, F's MCP stub, `ui/src/views/FastapiSecurity.svelte` (+ test), `tests/engine/test_appsecurity.py`, `tests/fastapi/test_introspector_security.py`, `tests/fastapi/test_fastapi_security_api.py`, goldens (`ids.json`: `spring-security` → `fastapi-security`), lane folder |
| **Must NOT touch** | §10.3 protected files; `engine/guard.py`; other lanes' modules |

**Architecture:** The adapter reads; the engine assembles. `FastApiIntrospector.security_model() -> SecurityModel`
(`fastapi/introspector.py:171`, reusing `_walk` at `:217` and `_dependant_of` at `:100`) walks `app.user_middleware`
(class names and `backend` type only, never kwargs values) and each `APIRoute.dependant` tree. Scheme detection:
`isinstance(call, fastapi.security.base.SecurityBase)` plus `dependant.security_requirements` when present (read with
`getattr` defaults; FastAPI internals drift). `explain` matches with `route.path_regex.match(path)` and
`route.methods` only — never `Route.matches()` (it runs path convertors, possibly user code). A custom `BaseRoute`
without `path_regex` → `bestEffort: true`.

## Global Constraints

- **Static on GET**: no dependency, scheme, middleware, convertor or route `matches()` is called; no attribute that
  is a property on a user class is read (use `inspect.getattr_static` where the object is user-defined).
- Middleware configuration values (CORS origins, TrustedHost hosts, session secret) never appear in any output.
- sharpit's own mount and middleware (`GuardMiddleware`, `CaptureMiddleware`) hidden; explain on a sharpit path →
  `matcherDescription: "sharpit endpoints are hidden from this report"`.
- Keys verbatim from the Spring DTOs (the Spring key names stay, e.g. `springSecurityPresent`; logged §11).
- `# ported: SpringSecurityControllerTests.<method>`. Red is an assertion. PT018. Introspection degrades, never crashes
  the host (AGENTS.md safety 5).

## Review Focus

1. **A dependency that would raise or do I/O if called** (`Depends(verify_token)` that hits a database). Expect it is
   never invoked by any GET. Pinned in Task 2: `test_get_never_calls_dependencies` (a sentinel dependency that
   `pytest.fail`s if called, also nested two levels).
2. **Secrets in middleware kwargs** (`CORSMiddleware(allow_origins=["https://x?token=sk_live_..."])`,
   `SessionMiddleware(secret_key=...)`). Expect absent from all three GETs and MCP. Pinned in Task 3:
   `test_middleware_values_never_exposed` + masking corpus row.
3. **Optional auth vs required auth** (`OAuth2PasswordBearer(auto_error=False)` vs default; `Security(dep,
   scopes=["admin"])`). Expect `permitAll` / `authenticated` / `hasAuthority` + `roles == ["admin"]`. Pinned in Task 1:
   `test_rule_classification_table` (parametrised).
4. **Router-level and app-level `dependencies=[...]`** guards with no scheme. Expect `rule: "custom"`,
   `bestEffort: true`. Pinned in Task 1: `test_route_level_unknown_dependency_is_custom`.
5. **Odd explain input**: `path` without leading `/`, 10 kB path, unknown method, a path matching a `Mount` of a plain
   Starlette sub-app. Expect 400 `{"error": "Invalid request"}` for the first two, `matched:false` for the method,
   `bestEffort:true` for the opaque mount. Pinned in Task 3: `test_explain_input_edges`.

---

### Task 0: Predict and council (spec §8)

- [ ] **Step 1:** `/sharpit:predict` on this plan → `.superpowers/sdd/0.4.0/lanes/B-fastapi-security/predict.md` (GO
  or CAUTION; NO-GO parks the lane).
- [ ] **Step 2:** `/sharpit:llm-council --tier high` on this plan → `council.md`; apply changes to this file in a
  `docs:` commit; code starts only after the verdict line.

### Task 1: Model and classification

**Files:** `src/sharpit/engine/spi.py` (append), `src/sharpit/engine/collectors/appsecurity.py`; Test
`tests/engine/test_appsecurity.py`.

**Interfaces:** `@dataclass(frozen=True) class SecurityScheme: type_name: str; auto_error: bool; scopes: tuple[str,
...]`; `class SecuredRoute: methods: tuple[str, ...]; path: str; handler: str; schemes: tuple[SecurityScheme, ...];
route_level_unknown: bool; unknown_dependency: bool; opaque: bool`; `class SecurityModel: middleware: tuple[str, ...];
auth_backends: tuple[str, ...]; routes: tuple[SecuredRoute, ...]; limitations: tuple[str, ...]`. In
`appsecurity.py`: `classify(route: SecuredRoute) -> tuple[str, bool, list[str], bool]` (`rule, secured, roles,
bestEffort`), `security_report(model) -> dict`, `endpoints_report(model) -> dict`, `explain(model, method: str, path:
str, matcher: Callable[[str, str], SecuredRoute | None]) -> dict`. Rules: no scheme → `unsecured`; any
`auto_error=True` with scopes → `hasAuthority` + sorted scopes; `auto_error=True` → `authenticated`; only
`auto_error=False` → `permitAll`; no scheme + route-level unknown → `custom`; `secured = rule in {"authenticated",
"hasAuthority", "custom"}`; `bestEffort = unknown_dependency or opaque`. CSRF names: `starlette_csrf.CSRFMiddleware`,
`asgi_csrf`; CORS `CORSMiddleware`; session `SessionMiddleware`.

- [ ] **Step 1:** Tests: `test_rule_classification_table`, `test_route_level_unknown_dependency_is_custom`,
  `test_single_chain_lists_middleware_outermost_first` (`# ported: SpringSecurityControllerTests.singleChainFiltersListedBySimpleClassName`),
  `test_two_mounted_apps_two_chains_in_order` (`# ported: ...twoFilterChainsProducedTwoDtoEntriesInOrder`),
  `test_auth_provider_types_listed` (`# ported: ...authenticationProviderTypeListed`),
  `test_no_auth_providers_empty_lists` (`# ported: ...noAuthProvidersResultsInEmptyLists`),
  `test_configured_username_is_null` (`# derived: no analogue; ported intent of configuredUsernameIsExposedButPasswordIsNot`),
  `test_endpoints_sorted_by_pattern_then_method`.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: fastapi-security model and rule classification`.

### Task 2: Introspection `security_model()`

**Files:** `src/sharpit/fastapi/introspector.py`; Test `tests/fastapi/test_introspector_security.py`.

- [ ] **Step 1:** Tests: `test_get_never_calls_dependencies`, `test_scheme_found_in_nested_dependency`,
  `test_security_scopes_read`, `test_sharpit_mount_hidden` (`# ported: SpringSecurityControllerTests.bootUiSecurityChainsAreHiddenByDefault`),
  `test_plain_starlette_app_not_present` (`# ported: ...absentFilterChainProxyReturnsDisabledReport`; reason
  `"FastAPI security dependencies are not available: the app is not a FastAPI app"`),
  `test_internals_drift_degrades` (monkeypatch `dependant.security_requirements` away and `dependencies` to raise →
  limitation text, no crash).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: static security introspection of FastAPI routes`.

### Task 3: Routes, MCP, safety

**Files:** `src/sharpit/fastapi/routes/fastapi_security.py` (F stub), flag flip; Tests
`tests/fastapi/test_fastapi_security_api.py`, safety-matrix and masking-corpus rows.

**Interfaces:** `GET {api}/fastapi-security`, `GET {api}/fastapi-security/explain?method=GET&path=/` (defaults
BootUI's; `path` must start with `/` and be ≤ 2048 chars), `GET {api}/fastapi-security/endpoints`. MCP
`get_fastapi_security` (read; BootUI's description with "Spring Security" → "FastAPI security"). `actionCapable=False`.

- [ ] **Step 1:** Tests: `test_report_golden_parity`, `test_endpoints_golden_parity`, `test_explain_matches_route`
  (`# ported: ...explainMatchesChainWhenPathMatches`), `test_explain_absent_is_unmatched`
  (`# ported: ...explainEndpointWithAbsentProxyReturnsUnmatchedResult`), `test_explain_input_edges`,
  `test_middleware_values_never_exposed`, `test_get_no_side_effects` (all three GETs), `test_mcp_read_tool_only`,
  `test_panel_disabled_403`.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS + full gate. Commit `feat: fastapi-security routes and MCP read tool`.

### Task 4: Svelte view, live check, evidence

- [ ] **Step 1:** `ui/src/views/FastapiSecurity.svelte` + vitest (chain list, endpoint table filter by rule, explain
  form; `bestEffort` badge). `npm --prefix ui run check` PASS.
- [ ] **Step 2:** Live on `examples/fastapi_sample` / tiny-ledger-py (OAuth2 routes) → `live-verify.md`.
- [ ] **Step 3:** Commit `feat: fastapi-security view and lane evidence`.

## §6.1 → task

1 parity (+ field map from the contract's Python mapping, `null`s: `configuredUsername`): 3 · 2 citations: 1–3 ·
3 safety/masking (middleware configuration): 2–3 · 4 gatekeeper: n/a (fastapi only in `sharpit/fastapi/`; boundary
test green) · 5 budget: n/a (no hot path) · 6 MCP read-only: 3 · 7 Svelte: 4 · 8 gates: 3–4 · 9 live: 4 · 10 handoff.

## Lane evidence checklist (`.superpowers/sdd/0.4.0/lanes/B-fastapi-security/`)

`predict.md` · `council.md` (verdict before the first code commit) · `handoff.md` · `field-map.md` · `checklist.md` ·
`findings.md` · `review.md` (`VERDICT: APPROVE`, reviewer ≠ implementer, head SHA, plus `ponytail-review`) ·
`gate/` (four gates, lowest-direct, no-SQLAlchemy logs, each naming the head SHA) · `live-verify.md`.
