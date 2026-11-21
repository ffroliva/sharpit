# Scenario: framework-exposure checks of the pentesting scan (A13)

Scope: the BootUI v2.5.0 pentesting checks that read the host framework's own metadata (the route table, the
middleware stack, configuration) rather than a synthetic HTTP response, ported to FastAPI/Starlette. The scan action,
its gates and the bounded probe are the existing pentesting scan (A10); this change adds route-table and middleware
evidence to that scan and nothing else. The whole pentesting scan is wired to the FastAPI adapter only (the Flask
adapter has no pentesting route, tool or probe), so every row below is FastAPI/Starlette scope.

## BootUI source map

Pinned tag `v2.5.0`. Registry order and retired ids: `PentestingCheckRegistry.java:14-27, 35-105`. Definitions:
`PentestingChecks.java`. Observation: `SpringPentestingObservationCollector.java` (marker prefixes `:49-50`, inventory
loop `:890-975`, limits `:44-48`). Evaluation journal: `PentestingAssessment.java`; completeness:
`PentestingScanner.java:118-150, 256-292`; coverage: `PentestingCheckRegistry.java:270-286, 409-433`.

BootUI defines 70 active checks (PT-A05-030 and PT-A05-031 are retired, `PentestingCheckRegistry.java:26-27`).
Thirty-eight of them take `PentestingSource.SPRING_METADATA`; they are the framework-evidence family and are
partitioned below by explicit id (2 + 2 + 19 + 1 + 1 + 1 + 1 + 2 + 5 + 1 + 2 + 1 = 38). No range notation is used.

| Disposition | IDs | BootUI definition | Python equivalent |
|---|---|---|---|
| Implemented (adapted) | PT-A05-041 API documentation or developer console is exposed (INFO, Medium) | `PentestingChecks.java:2264-2293` | FastAPI's registered `openapi`, Swagger UI and ReDoc routes, found in the route table |
| Implemented (adapted) | PT-A05-044 forwarded headers are trusted (INFO, Low) | `PentestingChecks.java:2414-2447` | uvicorn's `ProxyHeadersMiddleware` on the application's own middleware stack |
| Other lane | PT-A02-004, PT-A02-006 session cookie configuration | `PentestingChecks.java:1675-1733` | A12 (`SessionMiddleware` facts) |
| n-a: Actuator | PT-A05-016, PT-A05-019, PT-A05-027, PT-A05-028, PT-A05-032, PT-A05-033, PT-A05-034, PT-A05-035, PT-A05-036, PT-A05-037, PT-A05-038, PT-A05-039, PT-A05-040, PT-A05-049, PT-A05-052, PT-A05-053, PT-A05-054, PT-A05-055, PT-A05-056 (19) | `:1065-1135, 1209-1275, 1492-1553, 1886-2262` | none: no management-endpoint model in FastAPI/Starlette |
| n-a: Actuator CORS property | PT-A05-029 | `:1589-1627` | none: a Spring property; generic CORS checks belong to A11 |
| n-a: H2 console | PT-A05-017 | `:1137-1178` | none: no embedded database web console in the Python stack |
| n-a: request detail logging | PT-A05-051 | `:1766-1812` | none: no application-level request-detail logging toggle; server logging verbosity is outside the app object, and a logger level is process-global state a read must not touch |
| n-a: DevTools remote secret | PT-A05-062 | `:1277-1308` | none: no remote-restart secret exists |
| n-a: servlet firewall | PT-A05-042 | `:2295-2330` | none: Starlette routing has no request firewall |
| n-a: management interface | PT-A05-043 | `:2332-2412` | none: no separate management port |
| n-a: Spring Security and session wiring | PT-A07-001, PT-A07-002, PT-A07-003, PT-A07-004, PT-A07-005 | `:71-136, 1180-1207, 1629-1766, 2449-2483` | none: Spring Security semantics are not ported |
| n-a: default security password | PT-A01-001 | `:1629-1766` | none |
| Adapted elsewhere | PT-A07-006 OAuth2/OIDC issuer uses plaintext HTTP (HIGH, Medium) | `:2485-2540` | the security advisor's `SEC-OAUTH-004` and `SEC-OAUTH-006` (`rules_transport.py:78-88`, from `SchemeUrl.insecure`, `spi.py:155-161`); they exempt loopback hosts and are production-only, where BootUI flags any `http://` issuer |
| n-a: OAuth2 implicit grant | PT-A07-007 | `:2541-2560` | none: the OAuth2 flow type is not captured (`introspection_security.py:136-143` reads each flow's URLs, not its key) |
| n-a: JVM serialization | PT-A08-001 | `:2978-3020` | none |

PT-A05-011 (technology disclosure) is an HTTP-response check already evaluated by A10; this lane does not touch it.

## Mapping of each Spring exposure to the Python stack

| Spring exposure | FastAPI / Starlette | Flask / Werkzeug | Decision |
|---|---|---|---|
| Actuator endpoints (`/actuator/*`, Jolokia, heapdump, env, mappings, shutdown) | no equivalent | no equivalent | n-a |
| `/actuator/prometheus` (PT-A05-040) | a `prometheus_client` ASGI app is an opaque mount at a host-chosen path; BootUI binds the check to the Actuator base path inside its mapping partition (`SpringPentestingObservationCollector.java:951-960`) and the gatekeeper (`metrics/prometheus.py`) only reads the registry | same | n-a; nothing deferred |
| springdoc `/v3/api-docs`, `/swagger-ui` | `/openapi.json`, `/docs`, `/redoc` registered by `FastAPI.setup` | none built in; extensions choose their own paths | implemented for FastAPI; Flask is a `pending` row |
| GraphiQL | the GraphQL library's own route; the route table cannot tell an IDE from an API | same | dropped |
| H2 console | none | none | n-a |
| DevTools remote | `uvicorn --reload` and `fastapi dev` are local development servers, with no remote endpoint | Werkzeug debugger at `/console` is WSGI middleware added by the dev server, not visible on the app object | n-a |
| `FastAPI(debug=True)` / `app.debug` | tracebacks reach the client; already reported by the security advisor rule on `debug` | same, with no pentesting wiring | no pentesting finding; a runtime traceback is already PT-A05-006 (A10) |
| `server.forward-headers-strategy` | `ProxyHeadersMiddleware` on the app stack; uvicorn's `--proxy-headers` / `--forwarded-allow-ips` are server flags and unobservable | `werkzeug.middleware.proxy_fix.ProxyFix` | implemented for FastAPI/Starlette; server flags stated as a limitation |

The ReDoc page is reported because its route (`redoc_html`) is registered in the route table that `routes()` returns.
The scan makes no claim about a configured ReDoc URL: the introspector port exposes `AppInfo.docs_url`
(`spi.py:10-15`) and `SecurityFacts.openapi_url` (`spi.py:164-170`) and no ReDoc URL, and this lane does not extend it.

## Relation to the security advisor

PT-A05-041 and PT-A05-044 are emitted with BootUI's ids because the ids are the report, ordering and dismissal
contract (`PentestingCheckRegistry.java:35-105`). BootUI's Spring advisor has no documentation-exposure or
forwarded-header rule (`SecurityRules.java` mentions forwarded headers only in TLS text, `:248, 280, 1666`); the pair
exists in BootUI's Quarkus advisor (`QuarkusSecurityChecks.java:458`). `SEC-FAPI-002` and `SEC-FAPI-003` are sharpit
rules with different triggers (`rules_auth.py:100-106` needs secured routes; `rules_transport.py:99-103` needs
`trusted_hosts="*"`), the two advisors are disjoint (`registry.py:76-82`), and pentesting has no pytest gate
(`assess=None`). The two sets are therefore kept side by side and each is pinned unchanged, as A12 does for the
session rules.

## Coverage map (dimensions)

- D1 activation: skipped; inactive and guard behaviour is unchanged and covered by the A10 route tests.
- D2 guard: skipped as a new surface; the scan action and its gates are reused. One regression row asserts the new
  evidence is built only inside the action.
- D3 masking: active. Route and mount paths come from the host and can carry a secret. A11's rule applies: only
  host-echoed fragments pass through `echo = make_echo(masker)` (the required `masker` of `PentestingService.scan`),
  before the evidence is sanitised and cut at 240 characters; fixed BootUI text, gaps and limitations are never
  masked, and under `METADATA_ONLY` each path becomes `[masked]`. A whole-string pass is rejected because it rewrites
  BootUI's fixed text. This lane adds no second masker; `echo` and the sanitiser live in one shared module, created by A12's first task. The rule
  is proved in `MASKED`, `METADATA_ONLY` and `FULL`, including PT-A05-044's mount evidence.
- D4 parity: active. Two findings, one coverage rule and one completeness message are ported.
- D5 introspection drift: active. This is the main risk of the change.
- D6 no side effects on GET: active.
- D7 network failures: skipped; no network, file or process use is added.
- D8 host integration: active.
- D9 scale: active (the 4096-pattern inspection bound; one `security_facts()` read per scan).
- D10 MCP and CLI: active; the same scan action serves both.

## Worst-case trace

Input: `FastAPI(openapi_url=None)` (docs disabled in production, a common hardening step) while `docs_url` keeps its
default `"/docs"`.

1. `src/sharpit/fastapi/introspector.py:427-437` (`app_info`) returns `docs_url="/docs"`: it reads the attribute
   with `_attrs(self.app).get("docs_url")` and never checks the route table.
2. `FastAPI.setup` registers the documentation routes only under `if self.openapi_url and self.docs_url` and
   `if self.openapi_url and self.redoc_url`.
3. Measured on fastapi 0.162.0: `routes()` returns `[]` while `app_info().docs_url` is `"/docs"` and
   `security_facts().openapi_url` is `None`. With the defaults, `routes()` returns `/openapi.json`, `/docs`,
   `/docs/oauth2-redirect` and `/redoc`; with `docs_url="/api/docs", redoc_url=None` it returns `/openapi.json`,
   `/api/docs` and `/docs/oauth2-redirect`.
4. A check that reads the configured attribute reports PT-A05-041 for an app that serves no documentation.

Finding: real. A check must key on routes that are registered, never on the configured URL attributes. Conversely, an
app with `docs_url="/api/docs"` and `redoc_url=None` still registers `/docs/oauth2-redirect`, so a fixed `/docs`
prefix would flag an app whose documentation UI is off. The routes' handlers are the discriminator: the measured
handlers are `fastapi.applications:FastAPI.setup.<locals>.{openapi, swagger_ui_html, redoc_html, swagger_ui_redirect}`,
the same on a mounted sub-application (`/v1/docs`). The finding withdrawn in this trace: reading `routes()` for the
sharpit mount itself; `FastApiIntrospector(exclude_mount=...)` already removes it (`introspector.py:420-426`).

## Coverage and completeness rules

- Precedence is BootUI's (`PentestingCheckRegistry.java:270-286`): a finding, then a hand-off or not-applicable branch,
  then indeterminate. Endpoint truncation is an input of A02 (`:415-423`) and of A07 (`:428-433`).
- A02: truncation or unreadable route evidence makes A02 INDETERMINATE, through the A02 rule A11 already ports
  (found-first: a finding gives REVIEW with the limitation, `PentestingCheckRegistry.java:270-276`; otherwise a partial
  scan gives INDETERMINATE). A13 only sets `partial`. The default FastAPI app registers documentation, so PT-A05-041 is
  itself an A02 finding and gives REVIEW; the bound, unavailable and exception fixtures therefore use an app with no A02
  finding (a hardened app, proved by a baseline control), and a found-plus-truncated case asserts REVIEW.
- A07: BootUI's A07 definition carries a hand-off branch (`:165-175`) that is evaluated before the indeterminate
  branch (`:279-286`) on an adapter without Spring metadata, so truncation never makes A07 INDETERMINATE there; the
  ported test (`PentestingScannerTests.java:754-779`) runs with Spring metadata available. Sharpit's A07 is that
  branch (NOT_APPLICABLE, `report.py:355, 377-379`; REVIEW only when PT-A07-008 is found). The same rule applied to
  sharpit therefore leaves A07 NOT_APPLICABLE. Two differences are one deviation row,
  `pentesting:exposure-coverage-a07`: the label (sharpit NOT_APPLICABLE, BootUI HANDOFF) and the ported assertion
  (INDETERMINATE in BootUI's test, NOT_APPLICABLE here). A04 and A10 are unchanged (`:426, 435`).
- Where gaps land: BootUI appends them to the scan message and, with assessment gaps, to `evidence.limitations`
  (`PentestingScanner.java:132-148, 288-291`). Sharpit's scan message is fixed text and A11 sends gaps to
  `evidence.limitations`; A13 does the same, with BootUI's wording, and records row `pentesting:exposure-gap-placement`.
  `usable` stays the GET probe's usability (`report.py:272`; BootUI ORs per-check usability, `:124-129`), and
  `coverageComplete` stays as A10 sets it. The limitation list keeps 20 entries of 240 characters
  (`_unique_limitations`, `report.py:433-434` on A11's branch) and the count is measured on A11's code: in the worst case
  the real probe can produce, A10 contributes 5 entries, A11 5 gap strings, A12 1 new string (its configuration gap)
  and A13 1 new string (BootUI's endpoint-metadata gap), plus 3 trailing statements, 5 + 5 + 1 + 1 + 3 = 15; responses
  built by hand reach 7 + 7 + 1 + 1 + 3 = 19, still within 20. A13 therefore adds no standing
  entry; its statement is folded into the third trailing sentence (238 characters). A worst-case test captures the
  real pre-cut list, asserts its length against the claim, and asserts every promised statement and each lane's gap
  survives the cut.
- Opaque mounts and host-served documentation: the facts walk descends only into Starlette sub-applications
  (`introspector.py:878-884`); a WSGI or metrics ASGI mount is invisible to the route evidence, and documentation served
  by a host's own handler is not recognised. The third trailing sentence of every scan says so, with the server
  forwarded-header flags; it is a limitation, not a gap, so the scan is not PARTIAL for that reason.
- Wrapped mounts: `Mount("/x", ProxyHeadersMiddleware(sub))` is recorded by the introspector only as limitation text
  (`introspector.py:878-882`), with no `MiddlewareFacts`. A13 reads the boolean that the facts carry a limitation (A12's
  boolean) and reports BootUI's fixed gap `Framework configuration evidence was incomplete.`; the text is never read.
- Unavailable evidence fails closed (cross-lane decision, A12 agrees). BootUI treats an absent mapping provider as
  nothing to evaluate and a failed one as truncated (`SpringPentestingObservationCollector.java:895, 907-911`), and makes
  the scan PARTIAL with the configuration gap when configuration evidence is incomplete
  (`PentestingAssessment.java:41-44`, `PentestingScanner.java:265-267`). Here, when the security facts are absent, the
  read raises, the host is not FastAPI (the non-FastAPI marker) or the facts carry any limitation, the scan records the
  fixed gap `Framework configuration evidence was incomplete.` (the same string A12 records; one entry after
  deduplication) and is PARTIAL; documentation is still read from the route table and PT-A05-044 is not claimed. A
  missing `routes` method or an exception from `routes()` gives BootUI's endpoint gap, PARTIAL and A02 INDETERMINATE
  (when no A02 finding exists). A13's tests assert A13's own contribution only: the gap exactly once, the findings
  present or absent, and PARTIAL from A13's evidence alone; the whole scan's status is A12's to assert.
- `SecurityFacts.limitations` text is never copied, by A13 or any lane; only whether it is non-empty is read: its text can carry route paths and
  mount labels (`introspector.py:410, 878-884`; the positional-options note is `introspection_security.py:105`) and
  limitations are not masked. The non-FastAPI marker (`spi.py:133`) is handled as the absent case above. A12's revised
  plan already uses BootUI's fixed configuration gap and reads only whether the facts carry a limitation, never the
  text; A13 reads the same boolean and pins that against A12's merged code with a planted path. `fastapi/pentesting_exposure.py::read_security_facts`
  is A12's; this lane extends the module and does not recreate it.
- Reads happen after the single-flight is held: the scan action reads `routes()` and `security_facts()` only after
  `run_probe` (`pentesting_probe.py:59-65`) has acquired the flight and returned; a busy scan (409) or a refused scan
  reads neither.
- Pinned text: PT-A05-044's title, target, evidence and recommendation and PT-A05-041's target are fixed strings
  (plan Decision 11), compared exactly by tests.
- `--fail-on` evaluates a PARTIAL scan with a note (`fail_on.py:113, 256`); that is unchanged and pinned.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D6 | GET report, MCP report tool and CLI report command after a scan | Critical | Return the cached or initial report; call none of `routes()`, `app_info()` or `security_facts()`; open no socket | Integration (`no_side_effects`, call counts on all three surfaces) |
| 2 | D3 | `docs_url` carries a secret-looking segment; a sub-application with `ProxyHeadersMiddleware` is mounted at a secret-looking path (PT-A05-044 mount evidence) | Critical | The finding is still produced (positive control with a non-secret path); the secret is absent from the scan response, MCP output, CLI output and the cached GET in `MASKED`; each path is `[masked]` with the count kept in `METADATA_ONLY`; paths are verbatim in `FULL`; fixed BootUI text is intact in all three | Integration (real `Masker`) |
| 2a | D3 | Per-rule echo contract | High | Each rule passes every unique raw path (sorted, de-duplicated) through `echo` once and never passes fixed text or the middleware class name; `evaluate` without `echo` is a `TypeError` | Unit (recording echo) |
| 2b | D3 | Many long paths, one with a newline | High | Evidence is one line of at most 240 characters ending in `...`, sanitised after the echo | Unit; Integration |
| 3 | D5 | `openapi_url=None`, `docs_url` default (worst case) | High | No PT-A05-041; scan is complete | Integration |
| 4 | D5 | `docs_url="/api/docs"`, `redoc_url=None` | High | Evidence lists `/api/docs` and `/openapi.json`; `/docs/oauth2-redirect` is not listed | Integration |
| 5 | D5 | Default FastAPI app | High | One PT-A05-041 with severity INFO, confidence Medium and evidence `Detected developer-tooling mapping(s): /docs, /openapi.json, /redoc. Anonymous reachability was not tested.` | Integration; Golden |
| 6 | D5 | A user route named `/users/docs` or a user endpoint called `swagger_ui_html` in another module | High | Not flagged: match on module and qualified name, not on path or bare name | Unit |
| 7 | D5 | Sub-application mounted at `/v1` with its own documentation | High | `/v1/docs`, `/v1/openapi.json`, `/v1/redoc` listed | Integration |
| 8 | D5 | `routes()` raises or its method is missing; separately `security_facts()` raises | High | No finding, no crash, never a clean pass. A route failure gives BootUI's endpoint gap (`endpoint metadata was incomplete or exceeded the 4096-pattern inspection limit`), PARTIAL and, on a hardened app with no A02 finding, A02 INDETERMINATE. A facts failure gives the configuration gap and PARTIAL; documentation is still reported | Unit; Integration |
| 9 | D5 | Root `openapi_url` is set but no recognised handler is present (framework drift), or documentation is served by a host's own handler | High | Framework drift gives the endpoint gap, PARTIAL and no invented finding; a host's own handler is not recognised, with no gap, and the third trailing sentence says so | Unit |
| 10 | D9 | More than 4096 route patterns, on a hardened app with no A02 finding | High | Patterns past the bound are not inspected; the endpoint gap; scan PARTIAL; A02 INDETERMINATE; A07 stays NOT_APPLICABLE; A04 and A10 unchanged | Unit |
| 11 | D4 | PT-A05-041 and PT-A05-044 DTOs and registry position | High | Id, OWASP category, severity, confidence and order equal the BootUI contract projection; unchanged keys | Golden |
| 12 | D4 | Dismissing PT-A05-041 or PT-A05-044 | High | Applied to the initial, cached and scanned report | Integration |
| 13 | D8 | `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware` on the root stack | High | PT-A05-044 INFO with the pinned title, target, evidence (`... on the root application. Trusted proxy configuration and direct network reachability were not inspected.`) and recommendation | Integration |
| 14 | D8 | `ProxyHeadersMiddleware` only on a mounted sub-application | Medium | Reported; evidence names `the mount at <echoed path>` | Integration |
| 15 | D8 | No such middleware | Medium | Silent; the third trailing sentence states that server-level forwarded-header flags are not observable | Integration |
| 16 | D8 | Trust flag `trust_any_proxy` set | Medium | PT-A05-044 unchanged (BootUI does not rank the strategy); the security advisor proxy rule is unchanged | Integration |
| 17 | D8 | Host catch-all route `/{path:path}`, a host `TrustedHostMiddleware`, a `root_path` | Medium | Documentation routes still found; route patterns are not prefixed with `root_path`; the sharpit mount never yields a finding | Integration |
| 18 | D10 | MCP `pentest_scan` and CLI `pentest scan` | High | Same evidence as the route action; read-only and disabled refusals unchanged; `checksRun` unchanged | Integration |
| 19 | D4 | Scan without route evidence (older caller) | Medium | No finding; limitation states that route checks were not evaluated | Unit |
| 20 | D4 | Report wording | Medium | Limitation states that route and middleware evidence is static declaration evidence, not authorization or reachability; no Spring or Actuator coverage is implied | Unit |
| 21 | D4 | n-a ledger | Medium | Every one of the 38 framework-evidence ids is implemented, owned by another lane, adapted elsewhere or n-a with a reason, exactly once; the ledger checker fails on a planted duplicate, a planted missing id and a retired id | Unit (with controls) |
| 22 | D5 | Two documentation routes with the same path (mounts) | Low | Deduplicated and sorted as BootUI does (`LinkedHashSet`, sorted) | Unit |
| 23 | D5 | Middleware class `FakeProxyHeadersMiddleware`, or `ProxyHeadersMiddleware` from another module | High | Not matched: simple name and module both must match | Unit |
| 24 | D9 | One scan with A12 and A13 both active | High | `security_facts()` is called exactly once and `routes()` exactly once; a scale test with more than 4096 routes finishes within the overhead budget | Integration; Perf |
| 25 | D5 | Pure Starlette host (the non-FastAPI marker) | High | Documentation evaluated from the route table; PT-A05-044 not claimed; the configuration gap exactly once (fail closed, as A12); the test asserts only this lane's contribution | Integration |
| 26 | D4 | `--fail-on` over a PARTIAL scan from this lane | Medium | Evaluated with the existing PARTIAL note; exit code rule unchanged | Integration |
| 27 | D4 | A07 coverage on truncation | High | A07 stays NOT_APPLICABLE (REVIEW only with PT-A07-008); A04 and A10 unchanged; one deviation row records the label and the changed assertion | Unit; Matrix |
| 28 | D4 | Where gaps land and `usable` | High | Gaps are `evidence.limitations` entries with BootUI's wording; the scan message is the fixed A10 text; `usable` is the GET probe's whatever the route evidence | Integration |
| 29 | D4 | Twenty-entry limitation cap, worst case | High | With both probes rejected by Host with truncation and every lane's maximum present, the real pre-cut list has the claimed 15 entries (5 + 5 + 1 + 1 + 3), and after the cut every promised statement and gap is present, each named: A10's three trailing statements (the third in its final text), A11's gaps, A12's configuration gap, A13's endpoint gap; the length assertion fails when any lane adds a producer | Integration |
| 30 | D5 | A non-Starlette mount (WSGI or metrics ASGI app) | Medium | Not inspected, no crash, no gap; the third trailing sentence says non-Starlette mounts are not recognised | Integration |
| 31 | D3 | `SecurityFacts.limitations` carries a route path or mount label | Critical | The text is absent from every surface; the only effect is the configuration gap | Integration (planted path) |
| 32 | D4 | Matrix mapping of the ledger | Medium | `n-a` maps to `n-a`; `adapted-elsewhere` maps to an `adapted` row; `implemented` maps to the `adapted` rows; `other-lane` is A12's | Unit |
| 33 | D5 | `Mount("/x", ProxyHeadersMiddleware(sub))` (the introspector records it only as limitation text) | High | The configuration gap exactly once, never silence; no PT-A05-044 claim for that mount; the mount label never appears | Integration (planted label) |
| 34 | D2 | A scan that is busy (409) or refused (read-only panel, MCP or CLI off, inactive console, cross-site) | High | `routes()`, `app_info()` and `security_facts()` are called zero times; the evidence is read only after the probe has run | Integration (call counts) |
| 35 | D4 | Documentation found (default FastAPI app) and more than 4096 routes | High | PT-A05-041 present; A02 REVIEW (found-first) with the incomplete-evidence sentence; the endpoint gap; PARTIAL. Contrast: the bound and exception fixtures have no A02 finding, so A02 is INDETERMINATE | Integration |
| 36 | D4 | PT-A05-044 and PT-A05-041 text | High | Title, target, evidence and recommendation of PT-A05-044 and the target of PT-A05-041 equal the pinned strings (plan Decision 11); the recommendation never says that trust is unrestricted | Unit |

## Must-cover before merge (Critical + High)

- `test_report_reads_do_not_build_route_evidence` (1)
- `test_docs_route_path_with_a_secret_is_masked_in_evidence`, `test_mount_path_with_a_secret_is_masked_in_evidence` (2)
- `test_openapi_disabled_app_has_no_documentation_finding` (3)
- `test_custom_docs_url_is_reported_without_the_oauth2_redirect` (4)
- `test_default_fastapi_app_reports_developer_tooling` (5)
- `test_user_route_named_docs_is_not_documentation` (6)
- `test_mounted_subapp_documentation_is_reported` (7)
- `test_unavailable_route_metadata_is_incomplete_not_clean`, `test_introspector_exception_degrades_to_unavailable_evidence` (8)
- `test_unrecognised_documentation_handlers_are_incomplete_not_clean` (9)
- `test_route_inspection_bound_makes_the_scan_partial` (10)
- `test_framework_exposure_findings_match_bootui_contract` (11)
- `test_framework_exposure_findings_can_be_dismissed` (12)
- `test_proxy_headers_middleware_is_reported` (13)
- `test_mcp_and_cli_scan_include_framework_evidence` (18)
- `test_lookalike_proxy_middleware_is_not_matched` (23)
- `test_one_scan_reads_security_facts_and_routes_once` (24)
- `test_a07_coverage_is_unchanged_by_endpoint_truncation` (27)
- `test_forwarded_header_mount_evidence_masks_the_mount_path`, `test_long_path_list_evidence_is_sanitised_and_cut`,
  `test_documentation_rule_echoes_each_unique_raw_path_once_in_sorted_order` (2, 2a, 2b)
- `test_exposure_gaps_land_in_evidence_limitations_with_bootui_wording`,
  `test_usable_is_the_get_probe_whatever_the_route_evidence`, `test_exposure_limitations_survive_the_twenty_entry_cap`
  (28, 29)
- `test_security_facts_limitations_text_never_reaches_the_report` (31)
- `test_mount_wrapped_in_proxy_headers_middleware_gives_the_configuration_gap` (33)
- `test_busy_or_refused_scan_reads_no_route_or_facts`, `test_scan_reads_evidence_only_after_the_probe_has_run` (34)
- `test_documentation_found_with_truncated_routes_keeps_a02_review`, `test_hardened_app_baseline_has_no_a02_finding` (35)
- `test_forwarded_header_finding_text_is_pinned`, `test_documentation_finding_target_is_pinned` (36)
- `test_every_promised_trailing_statement_survives_the_worst_case` (29)

## Not merge blockers

Rows 14, 15, 16, 17, 19, 20, 21, 22, 26, 30 and 32 are covered by tests in the plan; they are not merge blockers.
Documentation routes registered by Flask extensions and the Werkzeug debugger stay `pending` until the Flask adapter
has a pentesting scan (matrix row `pentesting:exposure-flask`). No other work is deferred.

## Known-issues cross-reference

Introspection drift (`/sharpit:known-issues`, activation and introspection rows): the plan reads only `RouteInfo` and
the existing duck-typed `security_facts`, and degrades to a stated gap. No change touches activation or the guard
chain, and no masking logic changes: host-chosen paths pass through the `echo` A11 builds, reused from the shared module. The tool
descriptions and `cli/tools.json` are contract text and are not edited.
