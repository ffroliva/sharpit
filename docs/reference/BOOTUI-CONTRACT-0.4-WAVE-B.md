# BootUI JSON contract — 0.4.0 Wave B extract (Security) for sharpit

Source: `C:\development\github\boot-ui-ref` (BootUI 2.2.0, commit `ddfcb2436`, 2026-10-23), read-only, 2026-11-01.
Paths below are relative to that root. The MVP abbreviations moved; the real roots at this commit are:

- `DTO/` = `bootui-engine/src/main/java/io/github/jdubois/bootui/core/dto/` (DTOs moved from `bootui-core` into `bootui-engine`).
- `ENG/` = `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/`.
- `AC/` = `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/` (was `bootui-spring-autoconfigure`).
- `UI/` = `bootui-ui/src/main/frontend/src/`.
- `CONF/` = `bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/`.
- `DOCS/` = `docs/`.

Legend: **[JVM]** = Spring/JVM-specific, drop or replace in Python. **[AMBIG]** = not settled by the source; decide
deliberately. **N** = a new rule with no BootUI source. `sharpit:` lines are proposals, not source facts.

Panels in this wave: `security` (§2), `spring-security` (§3), `security-logs` (§4), `pentesting` (§5),
`architecture` (§6), `spring` → FastAPI advisor (§7). Panel registry rows (`ENG/panel/BootUiPanels.java:111-140`):

| id | title | actionCapable | route |
|---|---|---|---|
| spring-security | Spring Security | false | /spring-security |
| security | Security | true | /security |
| security-logs | Security Logs | false | /security-logs |
| pentesting | Pentesting | true | /pentesting |
| architecture | Architecture | true | /architecture |
| spring | Spring | true | /spring |

---

## 1. Shared advisor contract (Security, Architecture, Spring; Pentesting partly)

sharpit 0.3.0 already ports this plumbing for `rest-api` (`src/sharpit/engine/advisors/{report,retention,dismissals,
registry,findings,rules}.py`, routes in `src/sharpit/fastapi/adapter.py:580-585`). The Wave B advisors reuse it; only
the per-advisor DTO keys differ.

### Endpoints (every rule-based advisor)
- `GET /bootui/api/<id>` → cached report with dismissals applied. Never scans. Before the first scan it returns the
  advisor's `initialReport()` (`scan.status = "NOT_SCANNED"`, `scannedAt = null`, `evidence = unknown`).
- `POST /bootui/api/<id>/scan` → runs the scan under a single-flight lock (`SingleFlightAction`, operation ids
  `ActionOperations.SECURITY_SCAN|PENTESTING_SCAN|ARCHITECTURE_SCAN`; spring uses the same pattern), caches it, returns
  it with dismissals applied. An overlapping scan fails fast (busy error, as the MVP vulnerabilities scan;
  `ArchitectureScannerTests.duplicateScanFailsFastAndLaterRetryRuns`, `SpringScannerTests.singleFlightRejectsOverlappingScanAndReleasesAdmission`).
- `GET /bootui/api/<id>/rules/{ruleId}/violations?scanId=&offset=&limit=` → `AdvisorRuleViolationsDto`
  (`AC/web/AdvisorViolationsEndpoint.java`; offset/limit parsed strictly by `AdvisorViolationException.parseInteger`).
  Security, Architecture and Spring implement it; **Pentesting does not** (no `/rules/...` route, no `get_*_rule_violations` tool).
  sharpit: `retention.py` `ViolationRetention.page()` and `parse_integer()` already do this; reuse.
- Dismissal: `POST|DELETE /bootui/api/dismissed-rules/{id}` (shared store `.bootui/boot-ui.yml`, `dismissedRules` and
  `dismissedFindings` lists, `DOCS/PROPERTIES.md:118`). sharpit already has this (fingerprints in `dismissedRules:`,
  0.3.0 spec §5.6). Each new advisor needs an `AdvisorSpec` row in `engine/advisors/registry.py`.

### Report shape (one per advisor, keys differ in the counted noun)
```
<X>Report {
  localOnly: bool /* always true */, disclaimer: str,
  <scopeList>: str[], <scopeCount>: int, rulesEvaluated: int, violationsFound: int,
  severityCounts: {severity: str, count: int}[] /* CRITICAL,HIGH,MEDIUM,LOW,INFO, zeros included */,
  scan: { analyzer: str, status: str, message: str, scannedAt: long|null /* epoch ms */,
          rulesEvaluated: int, <scopeCount>: int, violationsFound: int },
  results: <X>RuleResultDto[] /* violating rules only, incl. dismissed, ordered severity → violationCount desc → id */,
  analysisErrors: <X>RuleResultDto[] /* status ERROR only, sorted by id */,
  evidence: AdvisorEvidenceDto { usable: bool, coverageComplete: bool, limitations: str[] },
  violationDetails: AdvisorViolationDetailsDto { scanId, total, retained, retentionLimit, truncated, locationNotes, ... }
}
<X>RuleResultDto { id, name, category /* label */, severity, description, status, violationCount: int,
                   sampleViolations: str[] /* ≤ 10 */, recommendation, learnMoreUrl, dismissed: bool }
```
- Rule `status` values in BootUI 2.2.0: `PASS`, `VIOLATION`, `SKIPPED`, `ERROR` (`AC/security/SecurityRuleSupport.java:10-13`,
  `AC/spring/SpringRuleSupport.java:10-13`, `ENG/architecture/ArchitectureRuleSupport.java:26-29`, same in REST API).
  **[AMBIG]** sharpit 0.3.0 emits `PASSED`/`FAILED`/`SKIPPED` (`src/sharpit/engine/advisors/rules.py:13`). Either the
  REST port deviated or upstream changed; decide once for all advisors before Wave B (golden fixtures pin it).
- Scan `status` values: `NOT_SCANNED`, `SCANNED`, `PARTIAL`, `ERROR` (architecture), `DISABLED` (security, spring).
- Sample detail sanitising: CR/LF/TAB → space, trimmed, ≤ 240 chars (`SecurityRuleSupport.java:24,102`).
- `applyDismissals`: dismissed rules stay in `results` with `dismissed=true`; `violationsFound`, `severityCounts` and
  `scan.violationsFound` are recomputed from the rest; `evidence` and `analysisErrors` unchanged
  (`AC/security/SecurityScanner.java:223-251`). sharpit `report.apply_dismissals` already does this.
- Severity counting for Security counts **occurrences** per severity, not rules (`DOCS/SECURITY-CHECKS.md` "Severity
  scale": "The advisor score applies the shared severity penalty to every concrete finding"). [AMBIG] check that the
  existing sharpit `severity_counts` (occurrence pairs) matches for every new advisor.
- Retention: `bootui.advisors.max-retained-violations`, default `10000` (`DOCS/PROPERTIES.md:248`); sharpit has
  `advisors_max_retained_violations`.

### MCP (shared)
- `<x>_scan` (schema NONE, action), `get_<x>_report` (NONE, read), `get_<x>_rule_violations` (schema `RULE_VIOLATIONS`
  = `id`, `scanId`, `offset`, `limit`; limit default 100, cap `min(1000, bootui.mcp.max-results)`)
  (`ENG/mcp/McpToolCatalog.java:85-116`, `ENG/mcp/McpToolSchema.java:36`, `ENG/mcp/McpToolInputSchema.java:21-24`).
- Scan tools do **not** return the report; they return a compact summary (`ENG/mcp/McpScanSummaries.java:59-84,353-363`):
  `{reportTool, detailsTool, scan, findingsFound, severityCounts, topFindings: {id,title,severity,count}[≤10],
  moreFindings, evidence, violationDetails(compact)}`; titles ≤ 160 chars. sharpit has no port of this yet (grep finds no
  `topFindings`): [AMBIG] port it in Wave B or keep returning the full report as `rest_api_scan` does today.
- Report tool descriptions are verbatim in `ENG/mcp/McpToolDescriptions.java:232-297` (e.g. `get_security_report`:
  "Return the last completed Security advisor report without starting a new configuration scan. Use this cached
  evidence before deciding whether an active security_scan is necessary.").

### CLI (shared, `DOCS/CLI.md:541-628`)
`bootui <x> report|scan|violations <id> --scan-id <scanId> [--offset N] [--limit N]`, plus `--fail-on <severity>` on scan
and report (exit `1` when the gate cannot be evaluated: status not `SCANNED`/`PARTIAL`, or `evidence.usable=false`
with nothing at the threshold, `DOCS/CLI.md:458-474`).

### UI (shared)
`UI/utils/useAdvisorPanel.js` (+ `scanStatus.js`, `scannerScore.js`, `useDismissedRules`, `useDismissedFindings`),
components `AdvisorSummary.vue`, `AdvisorRuleViolations.vue`, `PanelHeader.vue`, `PanelSkeleton.vue`,
`SpinnerButton.vue`. sharpit equivalent: `ui/src/components/AdvisorPanel.svelte` (used by `RestApi.svelte`).

---

## 2. Security (advisor) — `security`

Sources: `AC/security/SecurityController.java`, `AC/security/SecurityScanner.java`, `AC/security/SecurityRules.java`,
`AC/security/SecurityRuleRegistry.java`, `AC/security/SecurityCategory.java`, `DTO/SecurityReport.java`,
`DTO/SecurityRuleResultDto.java`, `DTO/SecurityScanStatusDto.java`, `DTO/SecuritySeverityCountDto.java`.
Reactive twin: `ENG/reactivesecurity/*`, `AC/reactive/ReactiveSecurityController.java` [JVM]. Quarkus twin:
`ENG/quarkussecurity/*` [JVM].

### Endpoints
- `GET /bootui/api/security` → `applyDismissals(lastReport())`.
- `POST /bootui/api/security/scan` → scan, then dismissals.
- `GET /bootui/api/security/rules/{ruleId}/violations?scanId=&offset=&limit=`.
- No request bodies. Controller is `@ConditionalOnClass(FilterChainProxy.class)`.

### Response DTO
```
SecurityReport { localOnly: true, disclaimer: str,
  filterChains: str[] /* each chain's request-matcher toString; [] before a scan */,
  filterChainsAnalyzed: int, rulesEvaluated: int, violationsFound: int,
  severityCounts: SecuritySeverityCountDto{severity,count}[],
  scan: SecurityScanStatusDto{analyzer, status, message, scannedAt: long|null, rulesEvaluated, filterChainsAnalyzed, violationsFound},
  results: SecurityRuleResultDto[], analysisErrors: SecurityRuleResultDto[],
  evidence: AdvisorEvidenceDto, violationDetails: AdvisorViolationDetailsDto }
SecurityRuleResultDto { id, name, category, severity, description, status, violationCount, sampleViolations,
                        recommendation, learnMoreUrl, dismissed }
```
- `category` is a label from `SecurityCategory`: `Authentication`, `Authorization`, `CSRF`, `Session management`,
  `Transport and headers`, `CORS`, `Method security`, `Actuator exposure`, `OAuth2 / JWT`, `Configuration`.
- Verbatim strings (`SecurityScanner.java:77-80,119-176`):
  - analyzer: `"BootUI Spring Security Advisor"`
  - disclaimer: `"Heuristic Spring Security rules run against the host application's registered filter chains and security beans only. These checks are review prompts, not verdicts, and should be validated against the application's threat model."`
  - NOT_SCANNED message: `"Security Advisor has not run yet. Run security checks in the panel, or call security_scan (bootui security scan), to inspect the filter chains."`
  - DISABLED: `"No Spring Security FilterChainProxy was found to inspect."` or `"Spring Security configuration could not be read: " + errors joined by "; "`.
  - SCANNED/PARTIAL: `"Security Advisor completed against " + n + " filter chain" + (n==1 ? "." : "s.")`, then
    `" Some configuration remains unobserved: " + errors`, then for PARTIAL
    `" Unsupported or incomplete evidence remains unknown; skipped checks are not security passes."`.
  - Status is `PARTIAL` whenever `!evidence.coverageComplete`, else `SCANNED`.
- Samples are 10 per rule (20 on Quarkus, `McpToolDescriptions.java:850`) [JVM].

```json
{"localOnly":true,"disclaimer":"Heuristic Spring Security rules run against ...","filterChains":["any request"],
 "filterChainsAnalyzed":1,"rulesEvaluated":54,"violationsFound":1,
 "severityCounts":[{"severity":"CRITICAL","count":0},{"severity":"HIGH","count":1},{"severity":"MEDIUM","count":0},{"severity":"LOW","count":0},{"severity":"INFO","count":0}],
 "scan":{"analyzer":"BootUI Spring Security Advisor","status":"SCANNED","message":"Security Advisor completed against 1 filter chain.","scannedAt":1793560000000,"rulesEvaluated":54,"filterChainsAnalyzed":1,"violationsFound":1},
 "results":[{"id":"SEC-CORS-002","name":"CORS must not combine wildcard origins with credentials","category":"CORS","severity":"HIGH","description":"...","status":"VIOLATION","violationCount":1,"sampleViolations":["..."],"recommendation":"...","learnMoreUrl":"...","dismissed":false}],
 "analysisErrors":[],"evidence":{"usable":true,"coverageComplete":true,"limitations":[]},
 "violationDetails":{"scanId":"...","total":1,"retained":1,"retentionLimit":10000,"truncated":false,"locationNotes":[]}}
```

### Errors
None specific; violations endpoint errors come from `AdvisorViolationException` (already ported in `retention.py`).
Panel unavailable reasons (`AC/web/PanelsController.java:665-676`): `"Spring Security not on the classpath"`,
`"No Spring Security filter chains are available"`, reactive: `"Spring Security is not on the classpath"`,
`"No application SecurityWebFilterChain beans are available"`. sharpit: [AMBIG] the FastAPI analogue is always
available (CORS/middleware/settings exist in every app); propose always available.

### Panel flags and settings
- `actionCapable=true`. `bootui.panels.security.enabled` (true), `bootui.panels.security.read-only` (false: "Disable
  the explicit Spring Security Advisor scan action.") (`DOCS/PROPERTIES.md:337-342`). Read-only blocks POST scan and
  dismissals; GET and violations stay open.
- No `bootui.security.*` settings. Uses `bootui.advisors.max-retained-violations`.
- sharpit env: `SHARPIT_PANELS_SECURITY_ENABLED`, `SHARPIT_PANELS_SECURITY_READ_ONLY` (via existing `panels` mapping).

### Side effects
- GET: none. `initialReport()` does not inspect configuration
  (`SecurityScannerTests.initialReportDoesNotInspectConfigurationBeforeExplicitScan`).
- POST scan: reflection over filter-chain beans and `Environment`; "never executes application authorization, matcher,
  credential or endpoint callbacks" (`SecurityScanner.java:70-73`, `DOCS/SECURITY-CHECKS.md:3-8`). BUT
  `SEC-AUTHZ-002` probes the authorization manager with bounded synthetic paths/methods
  (`SecurityScannerTests.blanketPermitAllRequiresEveryBoundedPathProbeToBeGranted`). [JVM]
- No socket, no file writes.

### Streams
None.

### MCP / CLI
- MCP: `security_scan` (action), `get_security_report`, `get_security_rule_violations`. `security_scan` description:
  `"Actively review application security configuration and return prioritized findings. Treat results as review evidence and verify exploitability before proposing a fix."`
- CLI: `bootui security report|scan|violations`.

### Advisor rules (54 servlet + 26 reactive; `DOCS/SECURITY-CHECKS.md`; titles verbatim)
FastAPI column: **Y** = direct analogue, **P** = partial, **–** = [JVM] drop. Python source for Y/P is in the last column.

| id | sev | title | FastAPI | Python signal |
|---|---|---|---|---|
| SEC-AUTH-001 | CRITICAL | Password encoder must not store credentials in plain text | P | a module-level passlib `CryptContext(schemes=["plaintext"...])` found on POST [AMBIG] |
| SEC-AUTH-002 | HIGH | Password encoder should not use a weak or legacy algorithm | P | `CryptContext` default scheme md5/sha1/des |
| SEC-AUTH-006 | LOW | BCrypt password encoder should use an adequate work factor | P | `bcrypt__rounds` < 10 |
| SEC-AUTH-004 | MEDIUM | Review the Boot property-backed default account | – | |
| SEC-AUTH-007 | HIGH | HTTP Basic authentication should run only over HTTPS | Y | production-like profile; `fastapi.security.HTTPBasic` in a route's Depends tree and no `HTTPSRedirectMiddleware` |
| SEC-AUTH-008 | MEDIUM | hideUserNotFoundExceptions should stay enabled | – | |
| SEC-AUTH-009 | HIGH | Do not run production on Spring Boot's auto-generated default user | – | |
| SEC-AUTH-010 | HIGH | Form login should run only over HTTPS | P | production-like profile; `OAuth2PasswordBearer`/`OAuth2PasswordRequestForm` and no HTTPS redirect |
| SEC-AUTHZ-001 | HIGH | Every filter chain should enforce authorization | P | routes with no security scheme dependency (INFO in Python: public APIs are legitimate) |
| SEC-AUTHZ-002 | HIGH | Avoid blanket permitAll authorization | P | no route has any security dependency |
| SEC-AUTHZ-003 | HIGH | Application security should not be effectively disabled | P | merge with AUTHZ-002 |
| SEC-AUTHZ-004 | INFO | Catch-all filter chains should be ordered last | – | |
| SEC-AUTHZ-005 | INFO/HIGH | Broader authorizeHttpRequests matchers should not shadow narrower ones | – | |
| SEC-CSRF-001 | HIGH | CSRF protection should stay on for browser-automatic credentials | Y | `APIKeyCookie` or `SessionMiddleware` + unsafe-method routes + no known CSRF middleware |
| SEC-CSRF-002 | MEDIUM | CSRF protection should stay on for HTTP Basic authentication | Y | `HTTPBasic` + unsafe-method routes + no CSRF middleware |
| SEC-SESSION-001 | HIGH | Session fixation protection should be enabled | – | |
| SEC-SESSION-002 | MEDIUM | Session cookie should set the Secure flag | Y | production-like profile; `SessionMiddleware(https_only=False)` (default) |
| SEC-SESSION-003 | MEDIUM | Session cookie should set the HttpOnly flag | – | Starlette always sets HttpOnly |
| SEC-SESSION-004 | LOW | Review SameSite=None on the session cookie | Y | `SessionMiddleware(same_site="none")` |
| SEC-SESSION-006 | LOW | Review bearer authentication saved in sessions | – | D: detecting an Authlib token response copied into `request.session` needs dataflow beyond the source scan's current local AST checks |
| SEC-SESSION-007 | INFO | Consider configuring concurrent session control | – | |
| SEC-SESSION-008 | MEDIUM | Remember-me signing key should be sufficiently long | P | `SessionMiddleware` `secret_key` length < 32 (length only, never the value) |
| SEC-HEAD-001 | MEDIUM | HTTP Strict Transport Security should be emitted | P | static: no headers middleware; dynamic check lives in Pentesting |
| SEC-HEAD-002 | MEDIUM | X-Frame-Options (clickjacking protection) should stay enabled | P | as above |
| SEC-HEAD-003 | LOW | A Content-Security-Policy should be defined | P | as above |
| SEC-HEAD-004 | LOW | X-Content-Type-Options should stay enabled | P | as above |
| SEC-HEAD-007 | MEDIUM | Security response headers should not be globally disabled | – | |
| SEC-HEAD-008 | LOW | Review HSTS max-age below the framework default | – | (Pentesting PT-A05-063 covers it) |
| SEC-HEAD-009 | MEDIUM | Review permissive CSP script execution | – | (PT-A05-060) |
| SEC-HEAD-010 | INFO | Cross-origin isolation headers should be considered | – | (PT-A05-021/022/068) |
| SEC-CORS-001 | LOW | CORS should not allow all origins | Y | `CORSMiddleware(allow_origins=["*"])` |
| SEC-CORS-002 | HIGH | CORS must not combine wildcard origins with credentials | Y | `allow_origins=["*"]` + `allow_credentials=True` (Starlette then reflects the Origin) |
| SEC-CORS-006 | LOW/HIGH | CORS should not allow broad origin patterns | Y | `allow_origin_regex` that matches any host (`.*`, `https?://.*`); HIGH with credentials |
| SEC-METHOD-001 | HIGH | Method security annotations require method security to be enabled | – | |
| SEC-METHOD-002 | LOW | Replace @EnableGlobalMethodSecurity with @EnableMethodSecurity | – | |
| SEC-ACT-001..007 | – | Actuator exposure (7 rules) | – | Actuator [JVM]; see N rule SEC-FAPI-002 |
| SEC-OAUTH-002 | INFO | Validate the JWT audience claim | P | partial: local AST flags PyJWT `jwt.decode` without `audience=` or with `verify_aud=False`; BootUI checks only a framework-managed decoder on an active bearer chain and does not judge custom decoders; without `audience=`, tokens with `aud` are rejected, so the risk is tokens without `aud` |
| SEC-OAUTH-003 | INFO | Review static verification-key rotation | – | D: a static PEM key may be intentional pinning; rotation intent needs configuration or key-history evidence |
| SEC-OAUTH-004 | HIGH | JWT issuer and JWK endpoints should use HTTPS | Y | production-like profile; `OpenIdConnect(openIdConnectUrl="http://non-loopback")` |
| SEC-OAUTH-005 | HIGH | Opaque-token introspection must use HTTPS | – | |
| SEC-OAUTH-006 | HIGH | OAuth2 client provider endpoints must use HTTPS | Y | production-like profile; `OAuth2AuthorizationCodeBearer(authorizationUrl/tokenUrl="http://...")` |
| SEC-CONFIG-001 | MEDIUM | Spring Security debug mode should be off | Y | `app.debug is True` (Starlette debug tracebacks) |
| SEC-CONFIG-002 | HIGH | H2 console should not be enabled in production | – | |
| SEC-CONFIG-005 | MEDIUM | Error responses should not leak stack traces or internal messages | Y | merge with CONFIG-001 (`ServerErrorMiddleware(debug=True)`) |
| SEC-CONFIG-006 | LOW | Application should enforce HTTPS in production | Y | no `HTTPSRedirectMiddleware` with a production-like profile |
| SEC-CONFIG-007 | HIGH | Configuration should not hold literal secret values | Y | sharpit config collector: a value the masker's value detectors flag (JWT, PEM, AWS key, URL userinfo) |
| SEC-CONFIG-008 | HIGH | StrictHttpFirewall should not relax its default URL protections | – | see N rule SEC-FAPI-001 |
| SEC-CONFIG-009 | MEDIUM | Spring Security framework logging should not run at DEBUG/TRACE in production | Y | loggers `fastapi`, `starlette`, `uvicorn`, `sqlalchemy.engine` at DEBUG with a production-like profile (read the level, never set it) |
| SEC-RXF-* (26) | – | WebFlux duplicates | – | [JVM] all |

N rules (no BootUI source; ids proposed, [AMBIG] prefix):
- **N SEC-FAPI-001** (MEDIUM) Host header not restricted: no `TrustedHostMiddleware`, or `allowed_hosts=["*"]`.
- **N SEC-FAPI-002** (LOW) Interactive API docs exposed with a production-like profile: `docs_url`/`redoc_url`/`openapi_url` not None.
- **N SEC-FAPI-003** (MEDIUM) Proxy headers trusted from any host: `ProxyHeadersMiddleware(trusted_hosts="*")` in the stack.
- **N SEC-FAPI-004** (INFO) A security scheme has `auto_error=False` and the route has no other check (silent anonymous access).

### UI
`UI/views/Security.vue` (252 lines): `useAdvisorPanel('api/security')`, `AdvisorSummary`, `AdvisorRuleViolations`,
`UnavailableState`, `SpinnerButton`. Calls `GET api/security`, `POST api/security/scan`, the violations route and the
dismissal routes. sharpit: `ui/src/views/Security.svelte` over `AdvisorPanel.svelte`.

### Tests to port (`AC/../security/SecurityScannerTests.java` and siblings, test root `bootui-spring-boot-starter/src/test/java/.../autoconfigure/security/`)
`SecurityScannerTests.initialReportDoesNotInspectConfigurationBeforeExplicitScan`,
`.scanReturnsStableDisabledReportWhenNoFilterChainProxyIsAvailable`, `.scanReportsNoViolationsForAHardenedChain`,
`.noApplicableTargetsAndUnavailableDiscoveryNeverCompleteChecks`,
`.missingRequiredOperationInventoryMakesScanStatusAndEvidencePartial`,
`.ruleEvaluationWrapsRuntimeExceptionAsErrorResult`, `.skippedRuleSurfacesSkippedStatusAndReason`,
`.everyActiveRuleRoutesThroughTheFailClosedBase`, `.analysisErrorsKeepsOnlyErrorResultsSortedById`,
`.forwardedHeadersDoNotProveHttpsEnforcement`, `.flagsMissingHttpsEnforcementInProduction`,
`.unusedApplicationCorsBeanDoesNotProveMissingIntegration`; plus `SecurityDocumentationTests` (docs table matches the
registry) and `SecurityViolationDetailsTests`.

### Python mapping
- Data: the ASGI middleware stack (`app.user_middleware`: class + kwargs, read only), the `Depends` tree of every route
  (`fastapi.security.*` instances: `HTTPBasic`, `HTTPBearer`, `OAuth2PasswordBearer`, `OAuth2AuthorizationCodeBearer`,
  `OpenIdConnect`, `APIKey{Header,Query,Cookie}`, `SecurityScopes`), `app.debug`, `docs_url`/`openapi_url`, logger
  levels, the sharpit config collector. The adapter already walks dependants (`src/sharpit/fastapi/introspector.py:100-321`).
- Optional library: none in the engine. FastAPI types are read only in `sharpit/fastapi/`.
- Port: new `AppIntrospector` method (e.g. `security_model() -> SecurityModel`, a frozen dataclass of middleware and
  per-route scheme facts) in `engine/spi.py`; rules in `engine/collectors/security/` (rules.py, service.py, report.py,
  mirroring `restapi/`). Gatekeeper: none needed. passlib detection [AMBIG]: if kept, a gatekeeper
  `engine/collectors/security/passlib_source.py` reading module globals only.

### [JVM] / [AMBIG]
- [JVM] filter chains, `FilterChainProxy`, Actuator, method security, reactive rules, Quarkus `QS-*` rules, AOT/native notes.
- [AMBIG] keep the key names `filterChains`/`filterChainsAnalyzed` (contract stability) with values = middleware stack
  descriptions and `1`? Proposal: keep the keys; `filterChains = ["ASGI middleware stack"]` plus one entry per mounted sub-app.
- [AMBIG] analyzer/disclaimer text: replace "Spring Security" with "FastAPI security"; record in the deviation log.
- [AMBIG] "production-like profile" in Python = sharpit's active profiles (`SHARPIT_PROFILES`?) matching `prod*`; define once.

### Size: **L** — ~25 portable rules over a new security model in the adapter, plus docs table, golden fixtures and UI view.

---

## 3. Spring Security (view) — `spring-security` → FastAPI security wiring

Sources: `AC/web/SpringSecurityController.java`, `AC/web/SpringSecurityService.java`, `DTO/SpringSecurityReport.java`,
`DTO/SpringSecurityFilterChainDto.java`, `DTO/SpringSecurityAuthDto.java`, `DTO/SpringSecurityEndpointDto.java`,
`DTO/SpringSecurityEndpointsReport.java`, `DTO/SpringSecurityExplainDto.java`. Reactive: `AC/reactive/ReactiveSpringSecurity*` [JVM].

### Endpoints (all GET, no bodies)
- `GET /bootui/api/spring-security` → `SpringSecurityReport`.
- `GET /bootui/api/spring-security/explain?method=GET&path=/` → `SpringSecurityExplainDto`. Defaults `method="GET"`,
  `path="/"`. No validation, length cap or clamp found in the controller/service (not found).
- `GET /bootui/api/spring-security/endpoints` → `SpringSecurityEndpointsReport`.

### Response DTOs
```
SpringSecurityReport { springSecurityPresent: bool, chains: SpringSecurityFilterChainDto[], auth: SpringSecurityAuthDto|null }
SpringSecurityFilterChainDto { order: int, requestMatcher: str, requestMatcherType: str, filters: str[] /* simple class names, in order */,
                               csrfEnabled: bool, corsEnabled: bool, sessionManagementPresent: bool }
SpringSecurityAuthDto { authenticationProviderTypes: str[] /* FQCN, sorted */, userDetailsServiceTypes: str[] /* FQCN, sorted */,
                        configuredUsername: str|null }
SpringSecurityExplainDto { matched: bool, bestEffort: bool, chainIndex: int|null, matcherDescription: str|null, filters: str[] }
SpringSecurityEndpointsReport { springSecurityPresent: bool, handlerMappingAvailable: bool, total: int, endpoints: SpringSecurityEndpointDto[] }
SpringSecurityEndpointDto { method: str /* or "ANY" */, pattern: str /* "/**" when none */, handler: str /* "SimpleName#method" */,
  secured: bool, rule: "permitAll"|"denyAll"|"authenticated"|"hasRole"|"hasAuthority"|"unsecured"|"custom"|"unknown",
  roles: str[] /* ROLE_ stripped for hasRole */, chainIndex: int|null, matcherDescription: str|null,
  description: str|null, bestEffort: bool }
```
- No proxy: `{"springSecurityPresent":false,"chains":[],"auth":null}`; explain → `{matched:false,bestEffort:false,chainIndex:null,matcherDescription:null,filters:[]}`
  (`SpringSecurityService.java:91-120`).
- `endpoints` sorted by `pattern` then `method` (`:184`). No handler mappings → `{springSecurityPresent, handlerMappingAvailable:false, total:0, endpoints:[]}`.
- `configuredUsername` = `spring.security.user.name`, null under `METADATA_ONLY`; the password is never read (`:516-523`).
- BootUI's own chains/endpoints are hidden (`BootUiSelfDataFilter`; `SpringSecurityControllerTests.bootUiSecurityChainsAreHiddenByDefault`).

Verbatim description/matcher strings (`SpringSecurityService.java`):
- `"BootUI endpoints are hidden from this report"` (explain on a BootUI path; sharpit: `"sharpit endpoints are hidden from this report"`).
- `"Chain " + i + " matcher threw " + SimpleName + " — requires more request context than available"`.
- `"No chain matched"`; `"No Spring Security filter chains configured"`; `"No Spring Security filter chain matched"`;
  `"Chain matcher threw " + SimpleName`; `"Chain has no AuthorizationFilter"`; `"Managed by " + managerSimpleName`.
- Matcher of a non-default chain: `"(custom chain: " + SimpleName + ")"`.

```json
{"springSecurityPresent":true,"chains":[{"order":0,"requestMatcher":"any request","requestMatcherType":"AnyRequestMatcher",
 "filters":["DisableEncodeUrlFilter","SecurityContextHolderFilter","CsrfFilter","LogoutFilter","AuthorizationFilter"],
 "csrfEnabled":true,"corsEnabled":false,"sessionManagementPresent":false}],
 "auth":{"authenticationProviderTypes":[],"userDetailsServiceTypes":["org.springframework.security.provisioning.InMemoryUserDetailsManager"],"configuredUsername":"user"}}
```

### Errors
None specific (no 4xx thrown). Unavailable reasons (`AC/web/PanelsController.java:390-402`): `"Spring Security not on the classpath"`,
`"No Spring Security filter chains are available"`, reactive `"No reactive Spring Security filter chains are available (no SecurityWebFilterChain bean found)"`.

### Panel flags and settings
`actionCapable=false`, view-only. `bootui.panels.spring-security.enabled` (true) "Show Spring Security filter chains and
best-effort endpoint rule explanations." (`DOCS/PROPERTIES.md:324-328`). No other settings; exposure mode from `bootui.expose-values`.

### Side effects — **flag**
- `GET /endpoints` and `GET /explain` **call user code on a GET**: `SecurityFilterChain.matches(request)` (application
  request matchers) and `AuthorizationManager.authorize(...)` with synthetic anonymous/authenticated/role principals
  (`SpringSecurityService.java:126-140,305-389`). Exceptions are swallowed. No caching: each GET recomputes.
- No socket, no file, no logger change.
- sharpit must not copy this: classify statically from the dependency tree; never call a dependency callable or a
  `Security(...)` scheme. Route matching may use Starlette `Route.matches(scope)` on a synthetic scope (framework code;
  a custom `BaseRoute` subclass is user code → treat as `unknown`, `bestEffort=true`). [AMBIG] whether that is acceptable on GET.

### Streams / MCP / CLI
- No stream. MCP `get_spring_security` (NONE, read; Spring MVC + WebFlux only) returns `security()`; description:
  `"Return the current Spring Security filter-chain and authentication configuration report. This passive read does not authenticate, authorize, or send a request through a chain."`
  (`ENG/mcp/McpToolDescriptions.java:661-663`, `AC/mcp/BootUiMcpTools.java:706-711`). CLI `bootui security config`.

### UI
`UI/views/SpringSecurity.vue` (462 lines): `apiFetch('api/spring-security')`, `apiFetch('api/spring-security/endpoints')`,
`apiFetch(\`api/spring-security/explain?${params}\`)`; uses `api.js`, `utils/loadError.js`, `PanelHeader`, `PanelSkeleton`, `SpinnerButton`.

### Tests to port (`.../autoconfigure/web/SpringSecurityControllerTests.java`)
`twoFilterChainsProducedTwoDtoEntriesInOrder`, `singleChainFiltersListedBySimpleClassName`,
`bootUiSecurityChainsAreHiddenByDefault`, `absentFilterChainProxyReturnsDisabledReport`,
`explainEndpointWithAbsentProxyReturnsUnmatchedResult`, `configuredUsernameIsExposedButPasswordIsNot`,
`configuredUsernameHiddenUnderMetadataOnlyExposure`, `authenticationProviderTypeListed`,
`noAuthProvidersResultsInEmptyLists`, `explainMatchesChainWhenPathMatches`.

### Python mapping
- `chains`: one entry for the app's middleware stack (`order` 0, `requestMatcher` `"any request"`, `requestMatcherType`
  `"ASGI middleware stack"`, `filters` = middleware class names outermost first, `csrfEnabled` = a known CSRF middleware
  (`starlette_csrf.CSRFMiddleware`, `asgi_csrf`), `corsEnabled` = `CORSMiddleware`, `sessionManagementPresent` =
  `SessionMiddleware`); one more per `Mount` of a sub-application with its own `user_middleware`.
- `auth.authenticationProviderTypes` = distinct FQCNs of `fastapi.security.*` schemes found in Depends trees;
  `userDetailsServiceTypes` = `AuthenticationMiddleware` backend FQCNs; `configuredUsername` = null (no analogue).
- `endpoints`: per route × method: `secured` = any scheme dependency; `rule` = `authenticated` (scheme with
  `auto_error=True`), `hasAuthority` + `roles` = scopes from `Security(dep, scopes=[...])`, `permitAll` (scheme with
  `auto_error=False` only), `unsecured` (no scheme), `custom` (route-level dependencies of unknown type), `bestEffort`
  = true whenever an unrecognised dependency is present; `handler` = `module:qualname` (sharpit convention).
- Gatekeeper: none; reading lives in `sharpit/fastapi/introspector.py` behind the `AppIntrospector` port; DTO assembly in
  `engine/collectors/appsecurity.py` (one module per collector).

### [JVM] / [AMBIG]
- [JVM] `FilterChainProxy`, `AuthorizationFilter`, `RequestMappingInfo`, synthetic `HttpServletRequest` stub, WebFlux variant.
- [AMBIG] panel id: keep `spring-security` (UI/MCP parity) or rename (`fastapi-security`, tool `get_fastapi_security`).
  Proposal: rename and log it; nothing in sharpit consumes the Spring name.

### Size: **M** — three GET DTOs over the security model built for §2; the explain matcher is the only new logic.

---

## 4. Security Logs — `security-logs`

Sources: `AC/web/SecurityLogsController.java`, `ENG/security/SecurityLogsService.java`,
`ENG/security/CapturedSecurityEvent.java`, `ENG/security/SecurityJournal.java`, `ENG/security/SecurityEventBuffer.java`
(Quarkus buffer), `AC/stream/BootUiChangeStream.java`, `DTO/SecurityLogsReport.java`, `DTO/SecurityLogEventDto.java`,
`DTO/SecurityLogDataDto.java`, `DTO/SecurityLogTypeSummaryDto.java`.

### Endpoints
- `GET /bootui/api/security-logs?principal=&type=&after=&offset=&limit=`
  - `principal`, `type`: trimmed, blank → no filter, **exact** match (case-sensitive).
  - `after`: ISO-8601 instant (`Instant.parse`, e.g. `2026-10-23T18:32:48Z`); events strictly after it.
  - `offset`/`limit`: `PagedList` semantics (MVP §1: offset<0→0; limit null → all, else clamp 1..1000).
- `GET /bootui/api/security-logs/stream` (SSE, see Streams).

### Response DTOs
```
SecurityLogsReport { auditEventsPresent: bool, unavailableReason: str|null, maxLogs: int,
                     typeSummaries: {type: str, count: int}[], events: SecurityLogEventDto[], page: PageMetadata }
SecurityLogEventDto { timestamp: str /* ISO-8601 Instant.toString(), NOT epoch ms */, principal: str|null, type: str,
                      data: SecurityLogDataDto[], traceId: str|null, requestId: str|null }
SecurityLogDataDto { name: str, value: str|null, masked: bool, truncated: bool }
```
Behaviour (`SecurityLogsService.java`):
- Filter → sort newest first → keep at most `maxLogs` → `typeSummaries` over the kept set (count desc, then type asc)
  → map → page. `maxLogs` = clamp(`bootui.security-logs.max-logs`, 1, 10000).
- `data`: entries sorted by key, at most 20; beyond that one extra row `{"name":"...","value":"<n> more entries omitted","masked":false,"truncated":false}`.
- Value display: `METADATA_ONLY` → value null (principal too); null → null; masked when exposure `MASKED` and
  `mask-secrets` and (secret key name **or** normalised key (non-alphanumerics removed, lower case) contains `sessionid`,
  `remoteaddress`, `remoteaddr`, `ipaddress`) → `"******"`, `masked=true`; else `String.valueOf`, > 256 chars → first
  256 + `"..."`, `truncated=true`.
- Unavailable: `{"auditEventsPresent":false,"unavailableReason":"No AuditEventRepository bean is available","maxLogs":500,"typeSummaries":[],"events":[],"page":{"total":0,"matched":0,"offset":0,"limit":0,"returned":0,"hasMore":false}}`.
- `traceId` is null on Spring MVC; `requestId` = BootUI request id stamped at publish time.

```json
{"auditEventsPresent":true,"unavailableReason":null,"maxLogs":500,
 "typeSummaries":[{"type":"AUTHENTICATION_FAILURE","count":2},{"type":"AUTHENTICATION_SUCCESS","count":1}],
 "events":[{"timestamp":"2026-11-01T10:15:30.120Z","principal":"alice","type":"AUTHENTICATION_FAILURE",
   "data":[{"name":"details","value":"******","masked":true,"truncated":false},{"name":"type","value":"BadCredentialsException","masked":false,"truncated":false}],
   "traceId":null,"requestId":"r-42"}],
 "page":{"total":3,"matched":3,"offset":0,"limit":3,"returned":3,"hasMore":false}}
```

### Errors
- `DateTimeParseException` or `IllegalArgumentException` → **400** `{"error": ex.getMessage()}` or `{"error":"Invalid request"}`
  when the message is null (`SecurityLogsController.java:164-168`; `SecurityLogsControllerTests.invalidAfterParameterReturnsBadRequest`).
  The message is Java's (`"Text 'x' could not be parsed at index 0"`). [AMBIG] sharpit text: use `"Invalid request"` or
  the Python `ValueError` text; never echo more than the parameter name.
- Too many streams: emitter completes with error `"Too many concurrent BootUI security-logs streams"` (no JSON body).
- Panel unavailable reason: `"No AuditEventRepository bean is available"` (`PanelsController.java:210-211`).

### Panel flags and settings
- `actionCapable=false`, view-only. `bootui.panels.security-logs.enabled` (true); `bootui.security-logs.max-logs` (500)
  (`DOCS/PROPERTIES.md:330-335`). Disabling it also removes the source from Live Activity (`:557-558`).
- When enabled and no `AuditEventRepository` exists, BootUI contributes an in-memory one [JVM].
- sharpit env: `SHARPIT_SECURITY_LOGS_MAX_LOGS` (int, fail-safe 500).

### Side effects
GET reads an in-memory repository only. Capture happens on host threads (`onApplicationEvent`), which only stamps,
publishes to the journal and flips the stream's dirty flag. No socket/file/logger/env change.

### Streams
`GET /security-logs/stream` → `text/event-stream` (`BootUiChangeStream("security-logs")`):
- No initial event; the browser does its own first GET.
- Event name `update`, data `{"ts": <epoch ms>}`, no `id:`, **no heartbeat**, no timeout (`SseEmitter(0L)`).
- Signals coalesced over 750 ms into one flush; at most 20 concurrent streams per panel; scheduler thread
  `bootui-security-logs-stream` (daemon) starts on first subscriber, stops after the last; all streams complete on
  context close. sharpit already has a change-event SSE (`src/sharpit/fastapi/sse.py`, `engine/capture` `change_events`): reuse.

### MCP / CLI
- `get_security_logs` (schema LIMIT, read): `logs(null,null,null,null,limit)` (`AC/mcp/BootUiMcpTools.java:447-451`);
  guide default `limit` 20 (`ENG/mcp/McpToolGuide.java:50`); description: `"Return a bounded, newest-first snapshot of authentication and authorization audit events. Correlate timestamps and principals with live activity."`
- CLI `bootui security logs --limit`.

### UI
`UI/views/SecurityLogs.vue` (264 lines): `apiFetch(\`api/security-logs?${params}\`)`, `useEventStreamRefresh('api/security-logs/stream')`,
`LowFootprintBanner`, `PanelHeader`, `PanelSkeleton`, `SpinnerButton`, `utils/loadError.js`.

### Tests to port
`ENG/../security/SecurityLogsServiceTests`: `carriesTheRequestIdEachEventWasPublishedUnder`, `clampsMaxLogsIntoSafeRange`,
`sortsNewestFirstSummarizesAndPages`, `masksSensitiveDataEntries`, `passesTraceIdThroughToTheDto`, `filtersByPrincipalTypeAndAfter`.
`AC/../web/SecurityLogsControllerTests`: `absentAuditRepositoryReturnsUnavailableReport`,
`eventsAreNewestFirstAndBoundedByConfiguredMaximum`, `anEventPublishedDuringARequestCarriesItsRequestId`,
`filtersByPrincipalTypeAndAfter`, `masksSensitiveEventDataAndHidesValuesInMetadataOnlyMode`,
`invalidAfterParameterReturnsBadRequest`. Stream: `AC/../stream/BootUiChangeStreamTests` (12, e.g.
`coalescesMultipleSignalsIntoASingleFlush`, `rejectsStreamsBeyondTheConcurrencyLimit`).

### Python mapping
- FastAPI has no audit-event bus. Event types to keep: `AUTHENTICATION_SUCCESS`, `AUTHENTICATION_FAILURE`,
  `AUTHORIZATION_FAILURE` (the three Quarkus emits, `DOCS/features/security.md:52-58`).
- Sources, in order of preference [AMBIG, owner call]:
  1. the existing capture middleware: a 401 → `AUTHENTICATION_FAILURE`, a 403 → `AUTHORIZATION_FAILURE`, principal
     null, data `{method, path (masked), status}`; no new hook in the host;
  2. a public `sharpit.record_security_event(type, principal=None, **data)` the app may call (success events only come from here);
  3. Starlette `AuthenticationMiddleware` `on_error` wrapping [AMBIG: patches user middleware, likely reject].
- A bounded ring buffer (`engine/collectors/securitylogs.py`), sized by `max_logs`, fed off the hot path; overhead
  budget test as for capture. Optional library: none. Gatekeeper: none.
- `after` parsing: `datetime.fromisoformat` with a required offset (`Z` accepted); naive → 400.

### [JVM] / [AMBIG]
- [JVM] `AuditEventRepository`, `AuditApplicationEvent`, `management.auditevents.enabled`, contributed in-memory repository.
- [AMBIG] availability: always available when capture runs (unavailable reason then = the capture's own reason).
- [AMBIG] the timestamp stays an ISO string (contract) even though sharpit's convention is epoch ms elsewhere; keep it.

### Size: **M** — service and paging are pure ports; the event source and its overhead budget are the new part.

---

## 5. Pentesting — `pentesting`

Sources: `AC/pentesting/PentestingController.java`, `AC/pentesting/SpringPentestingObservationCollector.java`,
`ENG/pentesting/PentestingScanner.java`, `PentestingChecks.java` (2972 lines), `PentestingCheckRegistry.java`,
`PentestingLocalHttpResponse.java`, `JavaPentestingLocalHttpClient.java`, `PentestingResponsePolicies.java`,
`DTO/PentestingReport.java`, `DTO/PentestingFindingDto.java`, `DTO/PentestingScanStatusDto.java`,
`DTO/PentestingSeverityCountDto.java`, `DTO/PentestingCoverageDto.java`, `CONF/PentestingDismissalContract.java`,
`DOCS/PENTEST-CHECKS.md`.

### Endpoints
- `GET /bootui/api/pentesting` → `applyDismissals(lastReport)`; `lastReport` initialised to `initialReport()` in the constructor.
- `POST /bootui/api/pentesting/scan` → scan (single-flight), cache, dismissals.
- No violations route; no request bodies.

### Response DTOs
```
PentestingReport { localOnly: true, disclaimer: str, checksRun: int, findingsFound: int,
  severityCounts: {severity, count}[], scan: PentestingScanStatusDto, coverage: PentestingCoverageDto[],
  findings: PentestingFindingDto[], evidence: AdvisorEvidenceDto }   /* no violationDetails */
PentestingScanStatusDto { scanner: str /* note: "scanner", not "analyzer" */, status, message, scannedAt: long|null, checksRun: int, findingsFound: int }
PentestingCoverageDto { category: "A01".."A10", title: str, status: str, description: str }
PentestingFindingDto { id: "PT-…", title, owaspCategory, severity, confidence: "Low"|"Medium"|"High", target: str,
                       evidence: str, recommendation, learnMoreUrl, heuristic: bool, dismissed: bool }
```
- One check can emit several findings (one per cookie/target); `findings` sorted by severity rank then id.
- Coverage status: `NOT_RUN` (initial), `REVIEW`, `INFO`, `INDETERMINATE`, `NOT_APPLICABLE`, `HANDOFF`, `SKIPPED`
  (`DOCS/PENTEST-CHECKS.md:198-203`, `PentestingCheckRegistry.java:89-181`). Categories and titles: A01 Broken Access
  Control, A02 Security Misconfiguration, A03 Software Supply Chain Failures (HANDOFF), A04 Cryptographic Failures,
  A05 Injection (SKIPPED), A06 Insecure Design (SKIPPED), A07 Authentication Failures, A08 Software or Data Integrity
  Failures (SKIPPED), A09 Security Logging and Alerting Failures (SKIPPED), A10 Mishandling of Exceptional Conditions.
  Each category's initial/scanned descriptions are verbatim in `PentestingCheckRegistry.java:89-181`.
- Verbatim strings (`PentestingScanner.java:38-41,77-84,266-279`):
  - scanner: `"BootUI local OWASP hygiene"`
  - disclaimer: `"Heuristic local checks only against the host application; BootUI /bootui paths are excluded. An explicit scan sends at most one GET and one OPTIONS request directly to 127.0.0.1. This panel does not replace a manual security review or a full pentesting."`
  - NOT_SCANNED: `"Pentesting checks have not run yet. Run local checks in the panel, or call pentest_scan (bootui pentest scan), to evaluate OWASP-oriented hygiene."`
  - SCANNED: `"Local OWASP hygiene checks completed against bounded host-application metadata and two direct loopback requests outside BootUI."`
  - PARTIAL: `"Local checks completed with incomplete evidence: " + gaps joined "; " + ". Findings from evaluated evidence remain valid; dependent no-finding results are indeterminate."`
    Gap strings: `"GET probe unavailable"`, `"GET response headers exceeded a bounded retention limit"`,
    `"GET response body exceeded the 8 KiB inspection limit"`, `"OPTIONS probe unavailable"`,
    `"OPTIONS response headers exceeded a bounded retention limit"`,
    `"endpoint metadata was incomplete or exceeded the 4096-pattern inspection limit"`,
    `"authentication framework metadata exceeded an inspection limit"`, `"framework configuration lists exceeded an inspection limit"`,
    `"default-user provenance or generated-password metadata was incomplete"`, `"HTTP firewall metadata inspection was incomplete"`,
    `"servlet CSRF metadata inspection was incomplete"`.
  - Target rejection: `"Local probe target rejected: " + reason` with reasons `"server port is unavailable"`,
    `"server port must be an integer between 1 and 65535"`, `"server port must be between 1 and 65535"`,
    `"context path exceeds 256 characters"`, `"context path contains an ambiguous or encoded path component"`,
    `"context path contains a control character"`, `"context path contains a dot segment"`,
    `"target must remain a literal loopback HTTP URI"`.
  - Evidence: `usable` = any check produced usable evidence; `coverageComplete` = not partial and no gaps; limitation
    when partial without gaps: `"Required local probe or framework evidence was incomplete; see scan diagnostics."`.
- Dismissal: by exact `PT-*` id (rule-level; covers every finding of that check). Dismissed findings stay with
  `dismissed=true`; `findingsFound`, `scan.findingsFound`, `severityCounts` recomputed; `checksRun`, `coverage`,
  `evidence`, `scan.status`, `scannedAt` unchanged; dismissing the INFO notices `PT-A05-001`/`PT-A05-069` cannot make
  evidence usable (`PentestingScanner.java:92-115`, `DOCS/PENTEST-CHECKS.md:86-110`).

```json
{"localOnly":true,"disclaimer":"Heuristic local checks only ...","checksRun":77,"findingsFound":1,
 "severityCounts":[{"severity":"CRITICAL","count":0},{"severity":"HIGH","count":0},{"severity":"MEDIUM","count":0},{"severity":"LOW","count":1},{"severity":"INFO","count":0}],
 "scan":{"scanner":"BootUI local OWASP hygiene","status":"SCANNED","message":"Local OWASP hygiene checks completed ...","scannedAt":1793560000000,"checksRun":77,"findingsFound":1},
 "coverage":[{"category":"A02","title":"Security Misconfiguration","status":"REVIEW","description":"..."}],
 "findings":[{"id":"PT-A05-002","title":"Missing X-Content-Type-Options nosniff header","owaspCategory":"A02:2025 Security Misconfiguration","severity":"LOW","confidence":"Medium","target":"GET /__bootui_pentesting__/missing-resource","evidence":"...","recommendation":"...","learnMoreUrl":"...","heuristic":true,"dismissed":false}],
 "evidence":{"usable":true,"coverageComplete":true,"limitations":[]}}
```
(`owaspCategory` exact format: see `PentestingChecks.java`; not verified here.)

### Errors
No 4xx of its own (busy scan → the shared action-busy error). Panel always available (`PanelsController.java:151-165`).

### Panel flags and settings
`actionCapable=true`. `bootui.panels.pentesting.enabled` (true), `bootui.panels.pentesting.read-only` (false: "Disable
the explicit local scan action.") (`DOCS/PROPERTIES.md:344-349`). No `bootui.pentesting.*` settings.

### Side effects — **flag**
- GET: none (cached report).
- POST scan: **opens a loopback socket** — `JavaPentestingLocalHttpClient` (JDK `HttpClient`, HTTP/1.1, 2 s connect and
  request timeout, no redirects, `NO_PROXY`) sends `GET` (`Accept: text/html`) and `OPTIONS` (`Origin: https://evil.example`,
  `Access-Control-Request-Method: GET`) to `http://127.0.0.1:<port>/<context>/__bootui_pentesting__/missing-resource`.
  Body retained ≤ 8 KiB, headers ≤ 64 names / 128 values / 16 KiB text, name ≤ 256 / value ≤ 4096 chars.
  The probe runs the host's filters and handlers (catch-alls, sessions, metrics may react).
- POST also reads `Environment`, MVC mappings (≤ 64 handler mappings / 4096 patterns), Spring Security beans by reflection.
- sharpit rule: no socket ever (`socket` imported nowhere). Use the existing in-process ASGI probe
  (`src/sharpit/engine/probe.py` `run_probe`) to call the host app below sharpit's mount, on POST only.

### Streams
None. MCP `pentest_scan` is not a progress tool (`McpToolCatalog.java:346`).

### MCP / CLI
- `pentest_scan` (action) → `McpScanSummaries.pentest` (`reportTool: "get_pentest_report"`, `detailsTool: null`, one
  `topFindings` row per check id: count = active findings, severity = worst). Description: `"Actively send bounded synthetic probes to this application's loopback endpoint and return security findings. Run only with permission and verify findings before remediation."`
- `get_pentest_report` (read): `"Return the last completed Pentesting advisor report without sending any HTTP probes. Use this cached evidence before deciding whether an active pentest_scan is necessary."`
- CLI `bootui pentest report|scan` (`--fail-on`). Reports name the array `findings`, not `results` (`DOCS/CLI.md:156`).

### Checks (77; `DOCS/PENTEST-CHECKS.md`, titles verbatim). Port column: **Y** port as-is (synthetic HTTP),
**M** map to a FastAPI signal, **–** [JVM] drop.

| id | sev / conf | title | port |
|---|---|---|---|
| PT-A01-001 | INFO/Low | All Spring Security filter chains have CSRF disabled | M (cookie auth without CSRF middleware; or hand off to §2 SEC-CSRF-001) |
| PT-A02-001 | MEDIUM\|INFO/Medium | Cookie is missing HttpOnly | Y |
| PT-A02-002 | INFO/Low | Cookie is missing Secure | Y |
| PT-A02-003 | MEDIUM/Medium | Cookie uses SameSite=None without Secure | Y |
| PT-A02-004 | LOW/Medium | Session cookie Secure flag is explicitly disabled | M (`SessionMiddleware(https_only=False)`) |
| PT-A02-005 | MEDIUM/High | Session cookie HttpOnly flag is explicitly disabled | – |
| PT-A02-006 | MEDIUM/High | Session cookie SameSite=None is paired with Secure=false | M (`same_site="none"`, `https_only=False`) |
| PT-A05-064 | INFO/Medium | Session cookie is missing a __Host-/__Secure- name prefix | Y |
| PT-A05-001 | INFO/Low | Synthetic GET evidence is incomplete | Y |
| PT-A05-069 | INFO/Low | Synthetic OPTIONS evidence is incomplete | Y |
| PT-A05-002 | LOW/Medium | Missing X-Content-Type-Options nosniff header | Y |
| PT-A05-003 | LOW/Medium | Missing clickjacking protection header | Y |
| PT-A05-046 | LOW/Medium | X-Frame-Options uses an unsupported value | Y |
| PT-A05-004 | INFO/Medium | Missing Referrer-Policy header | Y |
| PT-A05-047 | LOW/High | Referrer-Policy leaks full URLs cross-origin | Y |
| PT-A05-005 | LOW/Medium | Cookie is missing SameSite | Y |
| PT-A05-006 | MEDIUM/Low | Error response appears to expose implementation details | Y (markers: add Python traceback markers [AMBIG]) |
| PT-A05-007 | HIGH\|…/Medium | CORS allows credentialed cross-origin requests | Y |
| PT-A05-008 | LOW/Low | CORS allows a broad cross-origin request | Y |
| PT-A05-065 | LOW/Low | CORS allows the literal 'null' origin | Y |
| PT-A05-010 | LOW/Medium | Missing Content-Security-Policy header | Y |
| PT-A05-060 | dynamic/Low | Content-Security-Policy is present but weakened | Y |
| PT-A05-061 | LOW/Low | Unsafe X-XSS-Protection header is enabled | Y |
| PT-A05-066 | MEDIUM/Medium | Content-Security-Policy frame-ancestors is overly permissive | Y |
| PT-A05-067 | LOW/Low | Content-Security-Policy is missing object-src or base-uri | Y |
| PT-A05-011 | dynamic/Low | Response discloses server technology | Y (`server: uvicorn` is added by the server, not the ASGI app: in-process probes never see it [AMBIG]) |
| PT-A05-048 | INFO/Low | Local HTTP response advertises disabled HSTS | Y |
| PT-A05-063 | INFO/Low | Local HTTP response advertises weak HSTS | Y |
| PT-A05-013 | INFO/Low | Missing Permissions-Policy header | Y |
| PT-A05-021 | INFO/Low | Missing Cross-Origin-Opener-Policy header | Y |
| PT-A05-022 | INFO/Low | Missing Cross-Origin-Resource-Policy header | Y |
| PT-A05-068 | INFO/Low | Missing Cross-Origin-Embedder-Policy header | Y |
| PT-A05-023 | LOW/Medium | CORS preflight allows any method or header for a permissive origin | Y |
| PT-A05-024 | LOW/Low | TRACE or TRACK method advertised | Y |
| PT-A05-014 | MEDIUM/Medium | Error responses are configured to expose details | M (`app.debug=True`) |
| PT-A05-025 | MEDIUM/High | spring.web.error.include-exception is enabled | – |
| PT-A05-026 | MEDIUM/Medium | spring.web.error.include-binding-errors reveals validation details | – |
| PT-A05-015, -016, -018, -019, -028, -029, -032..-040, -049, -050, -052..-056 | | Actuator checks (21) | – |
| PT-A05-017 | dynamic | H2 database console is enabled | – |
| PT-A05-020 | INFO/Low | Spring Boot DevTools is on the classpath | M (reloading dev server signal, `src/sharpit/fastapi/signals.py`) |
| PT-A05-062 | dynamic | Spring Boot DevTools remote support is configured | – |
| PT-A05-027 | dynamic | Jolokia JMX-over-HTTP bridge is configured or present | – |
| PT-A05-030 | INFO/Low | spring.jpa.show-sql is enabled | M (SQLAlchemy `engine.echo` via `engine/sqla.py`) |
| PT-A05-031 | INFO/Low | Verbose logging level configured for framework packages | M (logger levels, read only) |
| PT-A05-051 | INFO/High | Request detail logging is enabled | – |
| PT-A05-041 | INFO/Medium | API documentation or developer console is exposed | M (`docs_url`, `redoc_url`, `openapi_url`) |
| PT-A05-042 | MEDIUM/High | A Spring Security DefaultHttpFirewall bean is present | – |
| PT-A05-043 | dynamic | Management interface potentially externally reachable | – |
| PT-A05-044 | INFO/Low | server.forward-headers-strategy trusts X-Forwarded-* headers | M (`ProxyHeadersMiddleware(trusted_hosts="*")` in the stack) |
| PT-A07-001 | INFO/Low | Spring Security is not on the classpath | M ("No route uses a fastapi.security scheme") |
| PT-A07-002 | INFO/Low | No Spring Security filter chain is configured | – (merged into A07-001) |
| PT-A07-003 | INFO/Medium | Spring Security user password is set in configuration | – |
| PT-A07-004 | MEDIUM/High | Servlet session tracking modes include URL | – |
| PT-A07-005 | MEDIUM/Medium | Spring Boot auto-generated security password is in use | – |
| PT-A07-006 | HIGH/Medium | OAuth2/OIDC issuer URI uses plaintext HTTP | M (`OpenIdConnect`/`OAuth2AuthorizationCodeBearer` URLs) |
| PT-A07-007 | HIGH/High | OAuth2 client uses the implicit grant | M (`fastapi.security.OAuth2(flows=…implicit…)`) |

Count: ~31 Y, ~13 M, ~33 dropped. `checksRun` must count the checks sharpit registers, not 77.

### UI
`UI/views/Pentesting.vue` (237 lines): `useAdvisorPanel('api/pentesting')`, `AdvisorSummary`, `PanelHeader`, `PanelSkeleton`,
`SpinnerButton` (no `AdvisorRuleViolations`: findings render inline with coverage).

### Tests to port (`ENG/../pentesting/`, test root `bootui-engine/src/test/java/.../engine/pentesting/`)
`PentestingScannerTests` (76): `initialReportIsNotScanned`, `scanUsesOnlySyntheticLoopbackRequestsAndDoesNotExposeResponseBody`,
`scanTargetsTheApplicationContextPath`, `scanSanitizesFailedLocalRequestEvidence`,
`scanReportsOptionsProbeFailureSeparatelyFromGetProbeFailure`, `invalidTargetsNeverReachTheHttpClient`,
`targetValidationAcceptsPortAndPathBoundaries`, `truncatedProbeEvidenceMakesTheScanPartialAndCoverageIndeterminate`,
`registryDefinesUniquePentestingIds`, `scanFindingsComeFromRegisteredPentestingChecks`,
`httpProbeChecksFlagWildcardCorsAndTraceAndMissingIsolationHeaders`, `credentialedCorsDistinguishesBrowserBlockedWildcardFromReflectedOrigin`,
`cookiesUsePresenceFlagsAndLastSameSiteAttribute`, `incompleteFieldsDoNotInventMissingCookieFlagsOrEffectivePolicies`,
`cspPoliciesIntersectAndFirstDuplicateDirectiveWins`, `weakContentSecurityPolicyCheckStaysSilentForNonceProtectedPolicy`,
`verboseErrorCheckIgnoresTraceIdentifiers`, `nonDocumentsAndSuccessfulDocumentationDoNotProduceDocumentOrErrorFindings`,
`scannedCoverageUsesInformationalReviewPromptsWhenNoFindingIsProduced`.
`PentestingDismissalTests`: `restoringTheLastIdRebuildsOriginalCountsEvenFromAnAlreadyMarkedReport`,
`unrelatedSecurityAndUnknownIdsDoNotDismissPentestingFindings`, `dismissingMissingEvidenceNoticesCannotEstablishUsabilityOrCompleteCoverage`.
`PentestingLocalHttpResponseTests` (9, header/body bounds). `PentestingDocumentationTests`. Conformance:
`CONF/PentestingDismissalContract.verify`.

### Python mapping
- Probes: `engine/probe.run_probe` in-process (no socket; a `# shortcut`-free deviation from BootUI's loopback client).
  Path [AMBIG]: `/<root_path>/__sharpit_pentesting__/missing-resource`. Probe bounds: reuse BootUI's (8 KiB body, header caps).
- Metadata: the security model from §2 + `docs_url`/`openapi_url` + logger levels + `engine/sqla.py` echo flag.
- Optional library: none. Gatekeeper: none (`probe.py` already owns in-process HTTP; `socket` stays banned).
- Engine package: `engine/collectors/pentesting/` (checks.py may exceed 1000 lines → split by OWASP group to respect the
  code-shape ratchet: `cookies.py`, `headers.py`, `cors.py`, `csp.py`, `config.py`, plus `registry.py`, `scanner.py`).

### [JVM] / [AMBIG]
- [JVM] Actuator, H2, DevTools remote, Jolokia, DefaultHttpFirewall, servlet session tracking, Spring error properties.
- [AMBIG] disclaimer/SCANNED text say "loopback"/"127.0.0.1"; sharpit must say in-process (e.g. "…sends at most one GET and
  one OPTIONS request in process through the ASGI application; no socket is opened."). Log it.
- [AMBIG] in-process probes miss server-added headers (`server`, `date`) and any proxy/TLS edge; PT-A05-011 and HSTS checks
  see less than BootUI.
- [AMBIG] the probe runs the host's middleware and handlers with a synthetic request on POST; same as BootUI, but it is
  user code: keep it POST-only and single-flight.

### Size: **L** — ~44 checks with RFC-level header/cookie/CSP/CORS parsing (`PentestingResponsePolicies`) and 76 tests to mine.

---

## 6. Architecture (advisor) — `architecture` → Python import-graph rules

Sources: `AC/architecture/ArchitectureController.java`, `AC/architecture/ArchitecturePackages.java`,
`ENG/architecture/ArchitectureScanner.java`, `ArchitectureRules.java`, `ArchitectureRuleRegistry.java`,
`ArchitectureCategory.java`, `ArchitectureGeneratedCode.java`, `DTO/ArchitectureReport.java`,
`DTO/ArchitectureRuleResultDto.java`, `DTO/ArchitectureScanStatusDto.java`, `DTO/ArchitectureSeverityCountDto.java`,
`DOCS/ARCHITECTURE-CHECKS.md`.

### Endpoints
`GET /bootui/api/architecture`, `POST /bootui/api/architecture/scan`, `GET /bootui/api/architecture/rules/{ruleId}/violations?scanId=&offset=&limit=`.

### Response DTOs
§1 shape with `basePackages: str[]`, `classesAnalyzed: int` (also in `scan`), and
`ArchitectureRuleResultDto` adds `sampleLocations: AdvisorViolationLocationDto[]` aligned index-for-index with
`sampleViolations` (`DTO/ArchitectureRuleResultDto.java`); violation pages also carry `locations` (`DOCS/CLI.md:233`).
- `category` labels: `Package structure`, `Coding practices`, `Spring stereotypes`.
- Verbatim (`ArchitectureScanner.java:41-45,148-290`):
  - analyzer `"BootUI ArchUnit hygiene"`; disclaimer `"Heuristic, project-agnostic architecture rules run against the host application's own classes only. These checks complement, but do not replace, a project-specific ArchUnit test suite or an architecture review."`
  - NOT_SCANNED: `"Architecture rules have not run yet. Run architecture checks in the panel, or call architecture_scan (bootui architecture scan), to analyse the application classes."`
  - no base package: status `SCANNED`, `"No application base package was detected, so there were no classes to analyse."`
  - no classes: `SCANNED`, `"No application classes were found under the detected base package(s) to analyse."`, evidence `{usable:false, coverageComplete:true, limitations:[]}` (confirmed-empty).
  - done: `"Architecture rules completed against " + n + " application class(es) under the detected base package(s)."`
  - errors: status `PARTIAL` if any rule passed or violated, else `ERROR`; `"Architecture analysis is incomplete: " + e + " rule(s) could not be evaluated against " + n + " application class(es)."`
  - failures: `"Application base packages could not be detected"`, `"Application classes could not be imported for analysis"` (+ exception simple name).
  - limitations (≤ 20): `"<id>: evaluator did not supply observation evidence."`, `"<id>: required architecture observations could not be resolved."`, `"<id>: architecture evaluation failed."`.
- Progress phases (MCP progress tool): `"Importing application classes"`, `"Checking generated code"`, `"Evaluating architecture rules"`,
  `"Locating violations"`, total = rules + 3. A cancelled scan never replaces the previous report.

### Errors
Unavailable reasons (`PanelsController.java:684-692`): `"Architecture advisor is not applicable when running as a GraalVM native image"`,
`"ArchUnit is not on the classpath"`, `"No application base package was detected"`.

### Panel flags and settings
`actionCapable=true`. `bootui.panels.architecture.enabled` (true), `.read-only` (false: "Disable the on-demand
architecture scan action.") (`DOCS/PROPERTIES.md:875-880`). No `bootui.architecture.*` settings.
MCP execution timeout `bootui.mcp.execution-timeout` (30 s) stops the scan at its next step and keeps the previous report.

### Side effects
GET: `initialReport()` calls `basePackages()` (bean-factory metadata only) and never imports classes
(`ArchitectureScannerTests.initialReportNeverImportsOrEvaluatesRules`). POST: reads `.class` files of the base
packages from the classpath and, for locations, source files. sharpit: reading source files is allowed on POST only.

### Streams / MCP / CLI
- No SSE. MCP `architecture_scan` (action, **progress-reporting**, `McpToolCatalog.java:346`), `get_architecture_report`,
  `get_architecture_rule_violations`. Description: `"Actively scan application classes for architecture and dependency violations. Use for structural reviews; verify each finding against intended module boundaries before changing code."`
- CLI `bootui architecture report|scan|violations`.

### Rules (`DOCS/ARCHITECTURE-CHECKS.md`; titles verbatim) and Python analogues

| id | sev | title | Python | signal (AST over the app package, on POST) |
|---|---|---|---|---|
| ARCH-PKG-001 | HIGH | Packages should be free of cycles | Y | strongly connected components of the module import graph (package level) |
| ARCH-MOD-001 | HIGH | Internal packages should not be accessed from other modules | Y | importing a `_private` module or an `internal` package from outside its parent package |
| ARCH-CODE-001 | LOW | Classes should not access standard streams | Y | `print(`, `sys.stdout`/`sys.stderr` |
| ARCH-CODE-002 | LOW | Classes should not throw generic exceptions | Y | `raise Exception(...)` / `raise BaseException` |
| ARCH-CODE-003 | LOW | Classes should not use java.util.logging | – | |
| ARCH-CODE-004 | INFO | Classes should not use Joda-Time | P | `import pytz` (→ `zoneinfo`) |
| ARCH-CODE-006 | HIGH | Classes should not forcibly terminate the JVM | Y | `sys.exit`, `os._exit`, `exit()`, `quit()` outside `__main__` |
| ARCH-CODE-007 | MEDIUM | Classes should not access JDK-internal APIs | P | importing `_private` names of third-party packages (`from starlette._utils import …`) |
| ARCH-CODE-008 | INFO | Classes should not use legacy date and time classes | P | `datetime.utcnow()` / `utcfromtimestamp()` (deprecated in 3.12) |
| ARCH-CODE-009 | INFO | Classes should not use deprecated APIs | – | [AMBIG] no reliable static source |
| ARCH-CODE-010 | INFO | Exceptions should be named ending with Exception | Y | `Exception` subclasses not ending in `Error`/`Exception` (PEP 8) |
| ARCH-CODE-012 | LOW | Loggers should be private final or container-managed | P | `logging.getLogger()` with no name or a literal instead of `__name__` |
| ARCH-CODE-013 | MEDIUM | Application classes should not depend on test frameworks | Y | app modules importing `pytest`, `unittest.mock`, `hypothesis` |
| ARCH-CODE-014 | MEDIUM | Classes should not have public mutable static fields | P | `global` rebinding of a public module-level name inside functions |
| ARCH-CODE-015 | LOW | Utility classes should be final with a private constructor | – | |
| ARCH-CODE-016 | MEDIUM/LOW | Classes should not use standard-annotation field injection | – | |
| ARCH-CODE-017 | MEDIUM | Classes should not directly instantiate Thread | Y | `threading.Thread(` in app code |
| ARCH-CODE-018 | INFO | Assertions should have a detail message | Y | `assert x` without message (also stripped by `-O`) |
| ARCH-SPRING-001 | MEDIUM | Classes should not use field injection | – | |
| ARCH-SPRING-002 | LOW | Controllers should not depend on repositories | P | layer by package name: `routers`/`api`/`endpoints` importing `repositories`/`crud` |
| ARCH-SPRING-003 | MEDIUM | Repositories should not depend on controllers | P | `repositories`/`crud` importing `routers`/`api` |
| ARCH-SPRING-007 | MEDIUM | Repositories should not depend on services | P | `repositories` importing `services` |
| ARCH-SPRING-006 | MEDIUM | Services should not depend on controllers | P | `services` importing `routers` |
| ARCH-SPRING-008 | MEDIUM | Services and repositories should not depend on web request types | Y | `services`/`repositories` importing `fastapi`/`starlette.requests`/`Request` |
| ARCH-SPRING-004, -009..-025 | | Spring proxy/async/transactional/bean rules (18) | – | [JVM] |
| (SPRING-025) | LOW | HTTP clients should be built from Spring Boot's auto-configured builder | P | N-ish: `httpx.Client()`/`AsyncClient()` constructed inside a request handler |

N rule option [AMBIG]: **ARCH-PY-001** honour an `[tool.importlinter]` contract set (layers/forbidden/independence) if the
project declares one; findings name the broken contract. Needs `import-linter` (gatekeeper below).

### UI
`UI/views/Architecture.vue` (242 lines): `useAdvisorPanel('api/architecture')`, `AdvisorSummary`, `AdvisorRuleViolations`,
`SourceLocationPreference` (open-in-editor location preference), `PanelHeader`, `PanelSkeleton`, `SpinnerButton`.

### Tests to port (`bootui-engine/src/test/java/.../engine/architecture/ArchitectureScannerTests.java`, 26)
`initialReportIsNotScanned`, `initialReportNeverImportsOrEvaluatesRules`, `scanWithNoBasePackagesProducesEmptyScannedReport`,
`nullImportIsAnErrorButGenuinelyEmptyImportRemainsScanned`, `importFailuresAreSanitizedErrorsAndReleaseSingleFlightForRetry`,
`partialScanRetainsViolationsAndErrorsThroughDismissal`, `errorsWithoutSuccessfulEvaluationsAreNotPartialEvenWithSkippedRules`,
`passingEvaluationMakesRuleFailurePartialEvenWithoutViolations`, `skippedAndVacuousRulesDoNotEstablishCompletedEvidence`,
`laterScanCanRecoverFromRuleFailure`, `scanEvaluatesAllRulesAndReturnsOnlyViolationsOrderedByImportance`,
`duplicateScanFailsFastAndLaterRetryRuns`, `ruleEvaluationWrapsRuntimeExceptionAsErrorResult`,
`ruleThatIsNotApplicableSurfacesSkippedStatus`, `analysisErrorsKeepsOnlyErrorResultsSortedById`,
`cancellingBetweenRulesStopsTheScanAndKeepsThePreviousReport`, `aBoundProgressReceivesEveryPhaseInOrderWithAStableTotal`.
`ArchitectureControllerTests`: `getReturnsCachedInitialReportWithDismissalsApplied`, `scanRefreshesCachedReportAndAppliesDismissals`.
Also `ArchitectureRulesTests`, `ArchitectureViolationLocationTests`, `ArchitectureRuleCatalogueTests` (docs ↔ registry).

### Python mapping
- Base packages: top-level packages of the route handlers' modules (`RouteInfo` `module:qualname` from the introspector),
  excluding `sharpit`, `fastapi`, `starlette` and site-packages. Files: `importlib.util.find_spec(pkg).submodule_search_locations`.
- Graph: stdlib `ast` parse of each `.py` (no import, no execution), bounded (file count/size caps → PARTIAL).
  `sampleLocations` = `{path, line}` from AST nodes (sharpit already emits locations for REST API? not verified).
- Optional libraries: none required. Optional `grimp` (faster graph) or `import-linter` (contracts) [AMBIG]: if adopted,
  gatekeeper `engine/importgraph.py` is the only module importing them.
- Engine package `engine/collectors/architecture/` (`graph.py`, `rules.py`, `service.py`, `report.py`).

### [JVM] / [AMBIG]
- [JVM] ArchUnit, bytecode import, generated-code (OpenAPI Generator) detection, Kotlin fixtures, Spring proxy rules, GraalVM gate.
- [AMBIG] category labels: keep `Package structure`, `Coding practices`; rename `Spring stereotypes` → `Layering`.
- [AMBIG] layer detection by package-name convention is a guess; INFO severity unless the project declares layers.

### Size: **L** — a bounded AST import-graph builder, cycle detection, ~20 rules, locations, progress phases.

---

## 7. Spring (advisor) — `spring` → FastAPI advisor

Sources: `AC/spring/SpringController.java`, `AC/spring/SpringScanner.java`, `AC/spring/SpringRules.java`,
`AC/spring/SpringRuleRegistry.java`, `AC/spring/SpringCategory.java`, `AC/spring/SpringContext.java`,
`DTO/SpringReport.java`, `DTO/SpringRuleResultDto.java`, `DTO/SpringScanStatusDto.java`, `DOCS/SPRING-CHECKS.md`.

### Endpoints
`GET /bootui/api/spring`, `POST /bootui/api/spring/scan`, `GET /bootui/api/spring/rules/{ruleId}/violations?scanId=&offset=&limit=`.

### Response DTOs
§1 shape with `inspected: str[]` and `componentsAnalyzed: int` (also in `scan`). Category labels: `Bean wiring`,
`Configuration`, `Profiles and environment`, `Performance and concurrency`, `Web and HTTP`, `Data and persistence`,
`Actuator and management`, `Reactive`.
- Verbatim (`SpringScanner.java:26-30,58-135`):
  - analyzer `"BootUI Spring Advisor"`; disclaimer `"Bounded Spring metadata and configuration checks are review prompts, not runtime or deployment verdicts. Unknown observations are unevaluated; validate advice against the application's requirements."`
  - NOT_SCANNED: `"Spring Advisor has not run yet. Run Spring checks in the panel, or call spring_scan (bootui spring scan), to inspect the application context."`
  - DISABLED: `"The application context could not be inspected safely."` (inspected `["Context inspection failed; no rules evaluated."]`) or `"No application context was available to inspect."`.
  - SCANNED: `"Spring Advisor completed against " + n + " bean definition(s); see unevaluated observations and analysis errors."`
  - `inspected` lines: `"Bean definitions: " + n + "; bounded, non-eager metadata only."`, `"Configuration is not proof of execution, authorization, or network reachability."`,
    `"Unevaluated rules (inapplicable or required evidence unavailable): " + k + "."`, then up to 38 `"<id>: <first sample>"` for SKIPPED rules, then incomplete observations.
  - limitation when discovery incomplete: `"Bounded Spring context discovery was incomplete; see inspected observations."`
  - Status is always `SCANNED` after a successful inspection (no PARTIAL path in `doScan`; completeness lives in `evidence`).

### Errors / flags / settings
No panel-specific errors; always available (`PanelsController.java:160`). `actionCapable=true`;
`bootui.panels.spring.enabled` (true) "Show read-only Spring application-context best-practice checks.",
`bootui.panels.spring.read-only` (false) "Disable the explicit Spring Advisor scan action." (`DOCS/PROPERTIES.md:317-322`).

### Side effects
GET: none (cached). POST: bounded, non-eager bean metadata; "does not create lazy beans, invoke application customizers,
open database connections, or probe remote services" (`DOCS/SPRING-CHECKS.md` "Availability and bounds").

### Streams / MCP / CLI
No SSE. MCP `spring_scan`, `get_spring_report`, `get_spring_rule_violations` (`McpToolCatalog.java:93-95`); `spring_scan`
description: `"Actively inspect Spring configuration and bean usage for correctness and maintainability risks. Verify each finding against effective configuration before changing code."`.
CLI `bootui spring report|scan|violations`.

### Rules: BootUI → FastAPI analogue (`DOCS/SPRING-CHECKS.md`, titles verbatim)

| id | sev | title | FastAPI analogue |
|---|---|---|---|
| SPRING-WIRING-001 | MEDIUM | Review bean definition overriding permission | P → FAPI-DEP-001 (`app.dependency_overrides` non-empty outside a test session) |
| SPRING-WIRING-002 | MEDIUM | Review circular-reference permission | – |
| SPRING-WIRING-003..006 | INFO | Review default JSON mapper / async executor / DataSource / transaction manager selection | – |
| SPRING-WIRING-007 | LOW | Review RestTemplate migration | P → covered by FAPI-ASYNC-002 (`requests` in async code) |
| SPRING-WIRING-008 | LOW | Review default-package application beans | – |
| SPRING-WIRING-009 | LOW | Review public mutable singleton fields | – (Architecture ARCH-CODE-014 analogue) |
| SPRING-CONFIG-002 | LOW | Review broad verbose logging configuration | Y (root logger at DEBUG) |
| SPRING-CONFIG-003 | MEDIUM | Review renamed or removed Boot 4 properties | P → FAPI-PYD-001 (Pydantic v1 API) |
| SPRING-CONFIG-004 | INFO | Consider a stable application name | Y (`app.title == "FastAPI"`, the default) |
| SPRING-CONFIG-005..008 | | Ignored missing config, Jackson 2 defaults/auto-config, properties migrator | – |
| SPRING-PROFILE-002 | INFO | Review DevTools packaging for production-like profiles | P (reloading dev server with a production-like profile) |
| SPRING-PROFILE-003 | INFO | Review disabled profile-name validation | – |
| SPRING-PERF-001 | INFO | Consider virtual threads for applicable blocking work | P → FAPI-ASYNC-001 |
| SPRING-PERF-002/003/005/006/007 | | Executor routing, async fallback, scheduler overlap, unbounded queue, virtual threads < JDK 24 | – (P: FAPI-ASYNC-004 threadpool capacity) |
| SPRING-CACHE-001 | INFO | Review concurrent-map cache capacity | – |
| SPRING-WEB-001 | INFO | Consider origin response compression | Y (no `GZipMiddleware`) |
| SPRING-WEB-002 | MEDIUM | Review immediate or zero-grace shutdown | – (server setting, not visible to the app) |
| SPRING-WEB-003 | INFO | Consider origin HTTP/2 | – |
| SPRING-WEB-004 | MEDIUM | Review configured fallback error details | Y (`app.debug=True`) |
| SPRING-WEB-005 | INFO | Review Boot HTTP client timeout policy | P → FAPI-HTTP-001 |
| SPRING-WEB-007 | LOW | Review a Tomcat cap with a virtual executor | – |
| SPRING-WEB-008 | LOW | Review an unlimited multipart request size | [AMBIG] (python-multipart / Starlette `max_part_size` defaults) |
| SPRING-JPA-001 | MEDIUM | Review servlet Open Session in View | – |
| SPRING-DATA-001 | MEDIUM | Review in-memory JDBC with production-like profiles | Y (SQLAlchemy URL `sqlite://` / `:memory:` with a production-like profile, via `engine/sqla.py`) |
| SPRING-DATA-002 | MEDIUM | Review in-memory R2DBC with production-like profiles | – |
| SPRING-MGMT-001..004 | | Actuator exposure (4) | – |
| SPRING-REACTIVE-001 | INFO | Review reactive handlers alongside JDBC | Y → FAPI-ASYNC-003 |
| SPRING-REACTIVE-003 | LOW | Review explicitly unlimited codec aggregation | – |

New FastAPI rules (**N**; ids/severities proposed, [AMBIG]):

| id | sev | title | signal (on POST; AST via `inspect.getsourcefile` + `ast`, no execution) |
|---|---|---|---|
| N FAPI-ASYNC-001 | INFO | Sync `def` endpoints run on the threadpool | route endpoint `not inspect.iscoroutinefunction` (count; INFO, often right) |
| N FAPI-ASYNC-002 | HIGH | Blocking call inside `async def` endpoint or dependency | AST call to `time.sleep`, `requests.*`, `urllib.request.urlopen`, `subprocess.run/call/check_output`, `open(` file I/O, `socket.*` inside an `async def` endpoint/dependency body |
| N FAPI-ASYNC-003 | MEDIUM | Async endpoint uses a synchronous database session | `async def` route depending on a dependency that yields a sync SQLAlchemy `Session` (≈ SPRING-REACTIVE-001) |
| N FAPI-ASYNC-004 | INFO | Many sync endpoints share a 40-thread pool | sync endpoint count above a threshold; anyio default limiter is 40 [AMBIG threshold] |
| N FAPI-PYD-001 | MEDIUM | Pydantic v1 API in use | AST: `from pydantic.v1`, `@validator`, `@root_validator`, inner `class Config:`, `orm_mode`, `.dict()`/`.json()`/`.parse_obj(` on models, `from pydantic import BaseSettings` |
| N FAPI-EVT-001 | LOW | Deprecated `on_event` startup/shutdown handlers | `app.router.on_startup`/`on_shutdown` non-empty instead of `lifespan` |
| N FAPI-HTTP-001 | LOW | Outbound HTTP call without a timeout | AST `requests.<verb>(` without `timeout=` (httpx has a 5 s default) |
| N FAPI-DEP-001 | MEDIUM | Dependency overrides left in place | `app.dependency_overrides` non-empty at scan time outside a pytest session |
| N FAPI-CONF-001 | INFO | Default application title | `app.title == "FastAPI"` (= SPRING-CONFIG-004, keep that id instead?) |

### UI
`UI/views/Spring.vue` (256 lines): `useAdvisorPanel('api/spring')`, `AdvisorSummary`, `AdvisorRuleViolations`, `PanelHeader`,
`PanelSkeleton`, `SpinnerButton`.

### Tests to port (`bootui-spring-boot-starter/src/test/java/.../autoconfigure/spring/SpringScannerTests.java`, 14)
`initialReportIsNotScanned`, `scanReportsFindingsAcrossCategories`, `scanReportsNoFindingsForAWellConfiguredContext`,
`applyDismissalsReturnsTheSameReportWhenNothingIsDismissed`, `applyDismissalsFlagsDismissedRulesAndExcludesThemFromCounts`,
`analysisErrorsKeepsOnlyErrorResultsSortedById`, `unknownFailedAndVacuousRulesDoNotCountAsCompleted`,
`evaluatorOwnedApplicabilityDistinguishesEmptyAndObservedCandidates`, `scanEvidenceIsResetAndInfoFindingsRemainObservedAfterDismissal`,
`singleFlightRejectsOverlappingScanAndReleasesAdmission`, `retiredDismissalsDoNotSuppressNewCodecRuleAndRestoreIsStable`.

### Python mapping
- Data: the introspector's routes (endpoint callables, `iscoroutinefunction`, dependants), `app.title`, `app.debug`,
  `app.dependency_overrides`, `app.router.on_startup/on_shutdown`, `user_middleware`, logger levels (read), SQLAlchemy
  engines (`engine/sqla.py`), activation/test-session state (`engine/testsession`). Source via `inspect.getsourcefile` +
  `ast.parse` on POST only, bounded; a missing source (C extension, `exec`) → SKIPPED, never an error.
- Optional library: none (`ast`, `inspect` are stdlib; Pydantic detection is syntactic, no `pydantic` import).
  Gatekeeper: none. Engine package `engine/collectors/fastapi_advisor/`; adapter facts via `AppIntrospector`.
- `componentsAnalyzed` = routes + dependencies inspected; `inspected` lines adapted ("Routes: n; source parsed, never executed.").

### [JVM] / [AMBIG]
- [JVM] bean definitions, executors, Jackson, DataSource selection, Tomcat, Actuator, R2DBC, Boot 4 property migration.
- [AMBIG] panel id: keep `spring` (UI parity) or `fastapi` (tools `fastapi_scan`, `get_fastapi_report`,
  `get_fastapi_rule_violations`). Proposal: `fastapi`, rule prefix `FAPI-`, BootUI ids kept where a rule is a direct analogue.
- [AMBIG] FAPI-ASYNC-002 overlaps 0.2.0's runtime blocking detection if any; check before adding.

### Size: **L** — ~13 rules, an AST visitor shared with §6 (build §6's AST layer first and this drops to M).

---

## 8. Cross-cutting notes for the port

- **GET purity.** Every BootUI GET in this wave is cached or in-memory, except `spring-security/endpoints` and `/explain`,
  which call application request matchers and authorization managers on a GET (§3). Pentesting opens a loopback socket
  on POST (§5). sharpit: static classification for §3; in-process ASGI for §5.
- **Single-flight.** Each scan has its own lock; reuse `engine/singleflight.py`.
- **Dismissal ownership.** Add `AdvisorSpec` rows: `security` (`SEC-*`), `pentesting` (`PT-*`, no fingerprint shape in
  BootUI; [AMBIG] add per-finding fingerprints like 0.3.0 §5.6), `architecture` (`ARCH-*`), `fastapi` (`FAPI-*` + kept `SPRING-*` ids).
- **Code shape.** `SecurityRules.java` (1864 lines) and `PentestingChecks.java` (2972) exceed sharpit's 1000-line module cap:
  split by category from the start.
- **Docs tables.** BootUI pins docs ↔ registry with `*DocumentationTests`; sharpit should add one per advisor
  (catalogue tables under `docs/`), as for REST API.

## Summary

| panel | endpoints | DTO count | GET side effects? | optional lib | gatekeeper | size |
|---|---|---|---|---|---|---|
| security | GET, POST scan, GET rules/{id}/violations | 4 (+3 shared advisor DTOs) | No | none | none (adapter reads FastAPI) | L |
| spring-security | GET, GET /explain, GET /endpoints | 6 | **Yes in BootUI** (matchers + authorization managers on GET); sharpit: none (static) | none | none (adapter) | M |
| security-logs | GET, GET /stream (SSE) | 4 (+PageMetadata) | No | none | none | M |
| pentesting | GET, POST scan | 5 | No (POST opens loopback socket in BootUI; sharpit: in-process ASGI) | none | none (`engine/probe.py`) | L |
| architecture | GET, POST scan, GET rules/{id}/violations | 4 (+location DTO) | No (POST reads files) | none; optional `grimp`/`import-linter` [AMBIG] | `engine/importgraph.py` if adopted | L |
| spring → fastapi | GET, POST scan, GET rules/{id}/violations | 3 (+severity count) | No (POST parses source) | none | none | L (M after §6) |
