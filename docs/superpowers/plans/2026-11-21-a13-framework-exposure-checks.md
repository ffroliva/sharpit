# A13 Framework-Exposure Pentesting Checks Implementation Plan

> Run `/sharpit:status --feature a13-framework-exposure-checks` for the next unchecked step. Complete one task at a time and run `/sharpit:check` before each commit.

**Goal:** Add the BootUI v2.5.0 framework-exposure checks that have a FastAPI/Starlette equivalent (PT-A05-041 documentation or developer console exposed, PT-A05-044 forwarded headers trusted) to the explicitly invoked pentesting scan, and record every other framework-metadata check as not applicable with its reason.

**Architecture:** The framework-free pentesting engine gains one value object (`FrameworkEvidence`) and the two rules that evaluate it. The FastAPI adapter builds that evidence from the application's own route table and middleware facts by attribute reads, as the Security and Routes panels already do; nothing is called and no request is sent. The scan action (the same function that serves the route, MCP and CLI) builds the evidence; GET report reads never do. Unreadable, unrecognised or truncated evidence is reported as a gap and makes the scan partial, never a clean result.

**Tech Stack:** Python 3.12+, existing `RouteInfo` and `SecurityFacts` introspection, pytest, BootUI-derived fixtures.

**Review gate:** Complete the required high-tier review of this plan and record its disposition before implementation begins. The gate covers the two behaviour choices recorded under "Decisions" and the interaction with the security advisor rules.

## Review disposition

- Pending: the plan has not been reviewed yet.

## Decisions

1. PT-A05-041 and PT-A05-044 are emitted as pentesting findings with BootUI's IDs, so dismissals and the report contract match BootUI, which also keeps its separate advisor rules for the same concerns. They share facts with the security advisor but not code: `SEC-FAPI-002` and the proxy rule are not changed, and a test pins that.
2. The documentation routes are identified by the registered handler (module and qualified name), not by path and not by the configured URL attributes (see the scenario's worst-case trace). The path is only what the finding reports.
3. Evidence exists only in the scan action. A report read returns the cached or initial report.

## Global Constraints

- Reads have no side effects: no GET route and no read MCP or CLI tool builds the evidence, opens a socket, writes a file, changes a logger level or changes `os.environ`. The evidence is built by attribute reads inside the action; no host endpoint is called.
- Actions keep A10's gates: enablement, guard, enabled panel, non-read-only, single-flight.
- Route paths are masked before output; no raw host value other than a masked route path or a middleware class name is returned.
- No claim of authorization or reachability: the evidence says the route is registered, nothing more.
- A failure, an unrecognised shape, or a truncated inventory is indeterminate and stated, never a clean result.
- `engine/` imports no `fastapi` or `starlette`; the adapter owns the handler names.
- Every ported test cites its BootUI source with `# ported: <Class>.<method>`.
- No module under `src/` exceeds 1000 lines; ratchets only go down.
- Every pytest command in this plan is targeted and parallel: `uv run pytest -q -n 4 <files>`. The full suite is not run locally.

## Merge order and conflicts

This lane builds on the A10 probe and report. It lands after A11 (CORS) and A12 (cookies and session), which also edit `report.py`, `service.py`, `routes/pentesting.py` and the shared limitation sentences. A12 adds a `session` keyword to `scanned_report` and `PentestingService.scan`; this lane adds an `exposure` keyword beside it. Each lane keeps its own matrix fragment. Resolve overlaps by merging the earlier lane in, and edit only the words of the shared limitation sentence that concern route and middleware checks.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A host-chosen documentation path carries a secret into evidence, MCP or CLI output | Pass paths through the engine masker; test with a secret-bearing path on every output surface. |
| Critical | A report read builds evidence or touches the host | Evidence only in the scan action; call-count and `no_side_effects` tests on GET, MCP and CLI reads. |
| High | Configured URL attributes flag an app that serves no documentation | Match registered handlers; worst-case trace test. |
| High | FastAPI renames its documentation handlers and the check goes silent | Declared-but-unrecognised becomes a stated gap; a test pins the installed handler names, and the lowest-direct CI leg runs it. |
| High | Introspection failure reads as "no exposure" | `available` and `truncated` map to gaps, PARTIAL and A02 INDETERMINATE. |
| Medium | Duplicate or contradictory findings with the security advisor | Distinct IDs, no shared code, advisor rules unchanged and pinned. |
| Medium | Merge conflicts with A11 and A12 in `report.py` | Section above; own module and matrix file. |

## File map

- `src/sharpit/engine/collectors/pentesting/framework_exposure.py` (new): `FrameworkEvidence`, the two rules, the gap messages, the inspection bound.
- `src/sharpit/engine/collectors/pentesting/report.py`: accept `exposure`, add its findings and gaps, mark A02 indeterminate on an incomplete inventory, update the limitation sentence.
- `src/sharpit/engine/collectors/pentesting/service.py`: pass `exposure` through `scan`.
- `src/sharpit/fastapi/pentesting_exposure.py` (new): build `FrameworkEvidence` from the introspector (`routes()`, duck-typed `security_facts`); owns the handler names.
- `src/sharpit/fastapi/routes/pentesting.py`: the scan function builds the evidence and passes it on.
- `tests/engine/collectors/pentesting/test_framework_exposure_ledger.py`, `test_framework_exposure.py` (new).
- `tests/fastapi/test_pentesting_exposure_api.py`, `test_pentesting_exposure_adapter.py` (new).
- `tests/fixtures/bootui/2.5.0/pentesting/framework-exposure.json` (new): the ledger and the BootUI projection of the two implemented rules. Separate from the hand-derived ASGI transport golden.
- `docs/reference/matrix-updates/0.8.0-a13.tsv` (new), `docs/reference/PARITY.md`, `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` section 14.

## Deviation rows (recorded in `0.8.0-a13.tsv`)

| Key | Status | Deviation | Reason |
|---|---|---|---|
| `pentesting:exposure-docs-source` | adapted | PT-A05-041 matches the registered OpenAPI, Swagger UI and ReDoc handlers, and reports their route paths, instead of BootUI's fixed prefix list `/v3/api-docs`, `/v2/api-docs`, `/swagger-ui`, `/graphiql` | The Java prefixes name Spring libraries; paths are configurable in FastAPI, so the handler is the stable fact |
| `pentesting:exposure-graphiql` | n-a | GraphiQL marker dropped | A GraphQL library serves its IDE and its API on one route; the route table cannot distinguish them |
| `pentesting:exposure-docs-text` | adapted | PT-A05-041 recommendation and learn-more link name FastAPI's conditional OpenAPI guidance and omit the H2 sentence; id, title, category, severity and confidence are BootUI's | The H2 console has no Python equivalent |
| `pentesting:exposure-proxy` | adapted | PT-A05-044 evaluates `ProxyHeadersMiddleware` on the application stack instead of `server.forward-headers-strategy`; title, target, evidence, recommendation and link are Python-specific; id, category, severity and confidence are BootUI's | The Spring property does not exist; uvicorn's server flags are not observable and are stated as a limitation |
| `pentesting:exposure-unavailable` | adapted | Unreadable route or middleware evidence is a gap, partial scan and A02 INDETERMINATE | BootUI treats an absent mapping provider as nothing to evaluate; FastAPI internals vary by version, so absence of evidence is not a clean result |
| `pentesting:exposure-bound` | adapted | The 4096-pattern inspection bound and its gap text are BootUI's; the 64-handler-mapping bound has no analogue | Starlette has one route tree, not a list of handler mappings |
| `pentesting:exposure-html-mappings` | n-a | `htmlMappingsPresent` is not ported | It only gates BootUI's Spring whitelabel 404 exclusion, which A10 does not apply (`pentesting:browser-document`) |
| `pentesting:exposure-actuator` | n-a | PT-A05-016, 019, 027-040, 049, 052-056 | No management-endpoint model; Prometheus `/metrics` is host-chosen, not a framework path |
| `pentesting:exposure-h2` | n-a | PT-A05-017 | No embedded database console |
| `pentesting:exposure-actuator-cors` | n-a | PT-A05-029 | Spring property; generic CORS is A11 |
| `pentesting:exposure-request-logging` | n-a | PT-A05-051 | Logging verbosity is server configuration, not readable from the app |
| `pentesting:exposure-devtools` | n-a | PT-A05-062 | No remote-restart secret; the Werkzeug debugger is not visible on the app object |
| `pentesting:exposure-firewall` | n-a | PT-A05-042 | Starlette has no request firewall |
| `pentesting:exposure-management-port` | n-a | PT-A05-043 | No separate management port |
| `pentesting:exposure-spring-security` | n-a | PT-A07-001..005, PT-A01-001 | Spring Security is not ported |
| `pentesting:exposure-oauth2` | n-a | PT-A07-006, PT-A07-007 | Not a framework-exposure condition; the security advisor keeps its scheme-URL rule |
| `pentesting:exposure-jvm` | n-a | PT-A08-001 | JVM serialization |
| `pentesting:exposure-flask` | pending | Flask documentation routes and the Werkzeug debugger | The pentesting scan is wired to the FastAPI adapter only |

### Task 1: Freeze the ledger and the report statements

**Commit:** `test: freeze the framework-exposure ledger and report statements`

**Files:** `tests/fixtures/bootui/2.5.0/pentesting/framework-exposure.json`, `tests/engine/collectors/pentesting/test_framework_exposure_ledger.py`.

**Interfaces:** The fixture is the ledger consumed by Tasks 3 and 6.

- [ ] **Step 1:** Create the fixture from `PentestingChecks.java`: the 38 `SPRING_METADATA` IDs, each with its disposition (`implemented`, `other-lane` or `n-a`), its BootUI source range and, for `n-a`, the reason; for PT-A05-041 and PT-A05-044 the BootUI id, title, OWASP category, severity, confidence and the registry position from `PentestingCheckRegistry.java:35-105`.
- [ ] **Step 2:** Add `test_framework_exposure_ledger_partitions_the_bootui_metadata_checks` (every one of the 38 IDs appears exactly once, all exist in `rule-ids.json`, none is retired). Cite `# ported: PentestingScannerTests.registryDefinesUniquePentestingIds` (`PentestingScannerTests.java:817`).
- [ ] **Step 3:** Add `test_matrix_fragment_accounts_for_every_not_applicable_id`: `assert path.is_file()` for `docs/reference/matrix-updates/0.8.0-a13.tsv`, then every `n-a` ID of the ledger appears in a row of status `n-a`.
- [ ] **Step 4:** Add `test_scan_without_route_evidence_states_the_route_checks_were_not_evaluated`: `scanned_report(get, options)` (no evidence) contains no PT-A05-041 or PT-A05-044 finding and a limitation naming both IDs and saying no route evidence was supplied.
- [ ] **Step 5:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_framework_exposure_ledger.py` and `uv run python scripts/dev/red_check.py <node ids of steps 3 and 4>`. The red must be the assertions (missing fragment, missing limitation), not an import error. Step 2 is a data guard and is green on arrival. Commit with explicit `git add` and `git commit -s`.

### Task 2: Port the BootUI cases through the scan action

**Commit:** `test: port BootUI developer-tooling and forwarded-header cases`

**Files:** `tests/fastapi/test_pentesting_exposure_api.py`.

**Interfaces:** Drives the existing `POST` scan route on real FastAPI apps built with the repo's test helpers; no new API is needed for these to run and fail on their assertions.

- [ ] **Step 1:** `test_default_fastapi_app_reports_developer_tooling` with `# ported: SpringPentestingObservationCollectorTests.apiDocsCheckFiresForDeveloperConsoles` (`:1088`): one PT-A05-041, severity INFO, confidence Medium, evidence `Detected developer-tooling mapping(s): /docs, /openapi.json, /redoc. Anonymous reachability was not tested.`, and no mention of an ordinary API route.
- [ ] **Step 2:** `test_openapi_disabled_app_has_no_documentation_finding` (worst case), `test_custom_docs_url_is_reported_without_the_oauth2_redirect`, `test_user_route_named_docs_is_not_documentation`, `test_mounted_subapp_documentation_is_reported`.
- [ ] **Step 3:** `test_proxy_headers_middleware_is_reported` with `# ported: SpringPentestingObservationCollectorTests.forwardHeadersStrategyFiresForFrameworkAndNative` (`:1185`): fires with the middleware on the root stack, silent without it (the `none` case), and a mounted-only case; `trust_any_proxy` leaves the finding unchanged.
- [ ] **Step 4:** `test_docs_route_path_with_a_secret_is_masked_in_evidence` across route, MCP and CLI output; `test_framework_exposure_findings_can_be_dismissed` for an initial, cached and scanned report (`# ported: PentestingDismissalTests`, `PentestingDismissalTests.java:40-43`).
- [ ] **Step 5:** `test_report_reads_do_not_build_route_evidence` using `no_side_effects` and an introspector double that counts `routes()` calls on GET, MCP read and CLI read; `test_mcp_and_cli_scan_include_framework_evidence`.
- [ ] **Step 6:** `test_unavailable_route_metadata_is_incomplete_not_clean`, `test_unrecognised_documentation_handlers_are_incomplete_not_clean`, `test_route_inspection_bound_makes_the_scan_partial` with `# ported: PentestingScannerTests.truncatedEndpointMetadataMakesA07IndeterminateButNotA04` (`:754`), adapted: PARTIAL, the BootUI gap wording, A02 INDETERMINATE, A04 and A10 unchanged.
- [ ] **Step 7:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_exposure_api.py` and `uv run python scripts/dev/red_check.py <node ids>`. Each red names a missing finding or gap. Commit.

### Task 3: Engine value object and rules

**Commit:** `feat: evaluate framework-exposure evidence in the pentesting engine`

**Files:** `engine/collectors/pentesting/framework_exposure.py`, `tests/engine/collectors/pentesting/test_framework_exposure.py`.

**Interfaces:** `FrameworkEvidence(documentation_routes: tuple[str, ...], proxy_headers: tuple[str, ...], available: bool, truncated: bool, declared_documentation: bool, limitations: tuple[str, ...])`; `evaluate(evidence) -> list[Finding]`; `gaps(evidence) -> list[str]`; `MAX_ROUTE_PATTERNS = 4096`. Consumed by Tasks 4 and 5. Imports no framework.

- [ ] **Step 1:** Unit tests first, ported from the same BootUI cases as Task 2: evidence text, sorted and de-duplicated routes (`LinkedHashSet` then sorted, `PentestingChecks.java:2282-2292`), empty routes give no finding, the mounted-name evidence of PT-A05-044, BootUI's DTO fields from the fixture, masking of every path.
- [ ] **Step 2:** Implement with `checks.finding(...)`; evidence passes the engine masker before use (read how `collectors/security/report.py` uses `Masker`).
- [ ] **Step 3:** `gaps`: unavailable metadata, truncation (BootUI text `endpoint metadata was incomplete or exceeded the 4096-pattern inspection limit`, `PentestingScanner.java:260-262`), and declared documentation with no recognised handler.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_framework_exposure.py tests/engine/test_import_boundary.py`; commit.

### Task 4: FastAPI adapter

**Commit:** `feat: read framework-exposure evidence from the FastAPI introspector`

**Files:** `fastapi/pentesting_exposure.py`, `tests/fastapi/test_pentesting_exposure_adapter.py`.

**Interfaces:** `framework_evidence(introspector) -> FrameworkEvidence`. Reads `routes()` and the duck-typed `security_facts` exactly as `engine/tools04/security.py` does; never calls an endpoint.

- [ ] **Step 1:** Tests: the installed handler names equal the expected set (`fastapi.applications:FastAPI.setup.<locals>.openapi`, `swagger_ui_html`, `redoc_html`; `swagger_ui_redirect` is not a marker); a lookalike handler elsewhere does not match; the 4096 bound; `declared_documentation` is true when the app declares an OpenAPI URL and a docs or ReDoc URL but no recognised handler appears; an introspector without `routes`, one that raises, and a non-FastAPI app give `available=False`; middleware facts whose name ends in `ProxyHeadersMiddleware` set `proxy_headers` (root and mounted); non-empty `security_facts.limitations` mark the evidence incomplete.
- [ ] **Step 2:** Implement. The handler names and the middleware class name live only here.
- [ ] **Step 3:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_exposure_adapter.py tests/fastapi/test_introspector_security.py tests/engine/test_import_boundary.py`; commit.

### Task 5: Wire the scan action and the report

**Commit:** `feat: add BootUI framework-exposure checks to the pentesting scan`

**Files:** `report.py`, `service.py`, `fastapi/routes/pentesting.py`, the Task 2 and Task 1 tests.

**Interfaces:** `scanned_report(get, options, scanned_at=None, ..., exposure=None)` and `PentestingService.scan(..., exposure=None)`; `None` means no evidence supplied (no finding, the Task 1 limitation), which keeps older callers valid. The scan function in `routes/pentesting.py` always supplies it.

- [ ] **Step 1:** Confirm the Task 1 and Task 2 failures are the named assertions.
- [ ] **Step 2:** Add the findings and gaps to `scanned_report`; an incomplete inventory sets `partial` and makes the A02 coverage INDETERMINATE only (`PentestingCheckRegistry.java:409-425`); update the limitation sentence so route and middleware evidence is described as static declaration evidence (`PentestingChecks.java:2287-2291` wording) and Spring, Actuator and JVM checks are n-a; do not touch the CORS and cookie wording owned by A11 and A12.
- [ ] **Step 3:** Pass `exposure` through the service; build it once per scan in the route's scan function so the route, MCP and CLI share it. The single-flight acquisition is unchanged.
- [ ] **Step 4:** Add the regression pin `test_security_advisor_documentation_and_proxy_rules_are_unchanged` (existing `SEC-FAPI-002` and the proxy rule on the same apps) in `tests/engine/collectors/security/test_rules_auth.py` and `test_rules_transport.py` beside their current cases.
- [ ] **Step 5:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_exposure_api.py tests/engine/collectors/pentesting tests/fastapi/test_pentesting_api.py tests/engine/collectors/security/test_rules_auth.py tests/engine/collectors/security/test_rules_transport.py tests/cli/test_fail_on.py` and `red_check.py` for any `test:` commit; commit implementation with explicit paths and DCO sign-off.

### Task 6: Matrix, parity and documentation

**Commit:** `docs: document the framework-exposure checks of the pentesting scan`

**Files:** `docs/reference/matrix-updates/0.8.0-a13.tsv`, `docs/reference/PARITY.md`, spec section 14, user documentation of the pentesting scan.

- [ ] **Step 1:** Write the matrix rows from the deviation table above (three tab-separated columns: key, status, reason). Task 1's matrix test turns green.
- [ ] **Step 2:** Update `PARITY.md` and spec section 14 for the two implemented checks and the n-a families; state in the user documentation that the findings report registered routes and middleware, not authorization or reachability, and name the unobservable server flags.
- [ ] **Step 3:** Regenerate the deviation table with `scripts/dev/generate_parity_deviations.py` if the repository gate requires it; run `uv run pytest -q -n 4 tests/parity tests/engine/collectors/pentesting tests/fastapi/test_pentesting_exposure_api.py tests/fastapi/test_pentesting_exposure_adapter.py`, `uv run ruff check`, `uv run ruff format --check` and `uv run pyright`.
- [ ] **Step 4:** Live check with `/sharpit:live-verify` on a sample app: default docs reported, `openapi_url=None` silent, scan partial with a deliberately broken introspector; describe the evidence as route-table evidence only. Commit docs with explicit paths and `git commit -s`.

## Definition of done

- [ ] High-tier review disposition recorded before implementation.
- [ ] Every Critical and High scenario has a named passing test; GET reads provably build no evidence.
- [ ] PT-A05-041 and PT-A05-044 match the BootUI contract projection in id, category, severity, confidence and order; text deviations are matrix rows.
- [ ] All 38 framework-evidence IDs are implemented, owned by another lane, or n-a with a reason, exactly once.
- [ ] Unreadable, unrecognised and truncated evidence is stated and never clean.
- [ ] Security advisor rules are unchanged and pinned.
- [ ] Lane tests, ruff and pyright pass; parity and spec section 14 reflect the lane.
