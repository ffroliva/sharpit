# Scenario: framework-exposure checks of the pentesting scan (A13)

Scope: the BootUI v2.5.0 pentesting checks that read the host framework's own metadata (the route table, the
middleware stack, configuration) rather than a synthetic HTTP response, ported to FastAPI/Starlette. The scan action,
its gates and the bounded probe are the existing pentesting scan (A10); this change adds route-table and middleware
evidence to that scan and nothing else.

## BootUI source map

Pinned tag `v2.5.0`. Registry order: `PentestingCheckRegistry.java:35-105`. Definitions: `PentestingChecks.java`.
Observation: `SpringPentestingObservationCollector.java` (marker prefixes `:49-50`, inventory loop `:890-975`, limits
`:44-48`). Evaluation journal: `PentestingAssessment.java`; completeness: `PentestingScanner.java:118-150, 256-292`;
coverage: `PentestingCheckRegistry.java:409-425`.

BootUI defines 70 active checks. Thirty-eight of them take `PentestingSource.SPRING_METADATA` instead of a synthetic
response. Those 38 are the framework-evidence family and are partitioned below.

| Disposition | IDs | BootUI definition | Python equivalent |
|---|---|---|---|
| Implemented (adapted) | PT-A05-041 API documentation or developer console is exposed (INFO, Medium) | `PentestingChecks.java:2264-2293` | FastAPI's registered `openapi`, Swagger UI and ReDoc routes, found in the route table |
| Implemented (adapted) | PT-A05-044 forwarded headers are trusted (INFO, Low) | `PentestingChecks.java:2414-2447` | `ProxyHeadersMiddleware` on the application's own middleware stack |
| Other lane | PT-A02-004, PT-A02-006 session cookie configuration | `PentestingChecks.java:1675-1733` | A12 (`SessionMiddleware` facts) |
| n-a: Actuator | PT-A05-016, 019, 027-040, 049, 052-056 | `:1065-1135, 1209-1275, 1492-1553, 1886-2262` | none: no management-endpoint model in FastAPI/Starlette |
| n-a: Actuator CORS property | PT-A05-029 | `:1589-1627` | none: a Spring property; generic CORS checks belong to A11 |
| n-a: H2 console | PT-A05-017 | `:1137-1178` | none: no embedded database web console in the Python stack |
| n-a: request detail logging | PT-A05-051 | `:1766-1812` | none: logging verbosity is server configuration (uvicorn flags), not readable from the app object |
| n-a: DevTools remote secret | PT-A05-062 | `:1277-1308` | none: no remote-restart secret exists |
| n-a: servlet firewall | PT-A05-042 | `:2295-2330` | none: Starlette routing has no request firewall |
| n-a: management interface | PT-A05-043 | `:2332-2412` | none: no separate management port |
| n-a: Spring Security and session wiring | PT-A07-001..005, PT-A01-001 | `:71-136, 1180-1207, 1629-1766, 2449-2483` | none: Spring Security semantics are not ported |
| n-a: OAuth2 issuer and grant | PT-A07-006, PT-A07-007 | `:2485-2560` | not a framework-exposure condition; sharpit's OAuth2 scheme-URL facts stay with the security advisor |
| n-a: JVM serialization | PT-A08-001 | `:2978-3020` | none |

PT-A05-011 (technology disclosure) is an HTTP-response check already evaluated by A10; this lane does not touch it.

## Mapping of each Spring exposure to the Python stack

| Spring exposure | FastAPI / Starlette | Flask / Werkzeug | Decision |
|---|---|---|---|
| Actuator endpoints (`/actuator/*`, Jolokia, heapdump, env, mappings, shutdown) | no equivalent | no equivalent | n-a |
| `/actuator/prometheus` | `prometheus_client` ASGI app mounted by the host at a host-chosen path; BootUI binds the check to the Actuator base path | same | n-a (the path is not a framework convention) |
| springdoc `/v3/api-docs`, `/swagger-ui` | `/openapi.json`, `/docs`, `/redoc` registered by `FastAPI.setup` | none built in; extensions choose their own paths | implemented for FastAPI; Flask extensions are deferred |
| GraphiQL | the GraphQL library's own route; the route table cannot tell an IDE from an API | same | dropped |
| H2 console | none | none | n-a |
| DevTools remote | `uvicorn --reload` and `fastapi dev` are local development servers, with no remote endpoint | Werkzeug debugger at `/console` is WSGI middleware added by the dev server, not visible on the app object | n-a |
| `FastAPI(debug=True)` / `app.debug` | tracebacks reach the client; already reported by the security advisor rule on `debug` | same, with no pentesting wiring | no pentesting finding; a runtime traceback is already PT-A05-006 (A10) |
| `server.forward-headers-strategy` | `ProxyHeadersMiddleware` on the app stack; uvicorn's `--proxy-headers` / `--forwarded-allow-ips` are server flags and unobservable | `werkzeug.middleware.proxy_fix.ProxyFix` | implemented for FastAPI/Starlette; server flags stated as a limitation |

The pentesting scan is wired to the FastAPI adapter only; the Flask adapter has an introspector but no pentesting
route, tool or probe, so Flask rows are recorded as deferred, not implemented.

## Coverage map (dimensions)

- D1 activation: skipped; inactive and guard behaviour is unchanged and covered by the A10 route tests.
- D2 guard: skipped as a new surface; the scan action and its gates are reused. One regression row asserts the new
  evidence is built only inside the action.
- D3 masking: active. Route paths come from the host and can carry a secret.
- D4 parity: active. Two findings, one coverage rule and one completeness message are ported.
- D5 introspection drift: active. This is the main risk of the change.
- D6 no side effects on GET: active.
- D7 network failures: skipped; no network, file or process use is added.
- D8 host integration: active.
- D9 scale: active (the 4096-pattern inspection bound).
- D10 MCP and CLI: active; the same scan action serves both.

## Worst-case trace

Input: `FastAPI(openapi_url=None)` (docs disabled in production, a common hardening step) while `docs_url` keeps its
default `"/docs"`.

1. `src/sharpit/fastapi/introspector.py:427-437` (`app_info`) returns `docs_url="/docs"`: it reads the attribute
   with `_attrs(self.app).get("docs_url")` and never checks the route table.
2. `FastAPI.setup` (verified on fastapi 0.136.1) registers the documentation routes only under
   `if self.openapi_url and self.docs_url` and `if self.openapi_url and self.redoc_url`.
3. A measurement on that app: `routes()` returns `[]` while `app_info().docs_url` is `"/docs"` and
   `security_facts().openapi_url` is `None`.
4. A check that reads the configured attribute reports PT-A05-041 for an app that serves no documentation.

Finding: real. A check must key on routes that are registered, never on the configured URL attributes. Conversely, an
app with `docs_url="/api/docs"` and `redoc_url=None` still registers `/docs/oauth2-redirect`, so a fixed `/docs`
prefix would flag an app whose documentation UI is off. The routes' handlers are the discriminator: the measured
handlers are `fastapi.applications:FastAPI.setup.<locals>.{openapi, swagger_ui_html, redoc_html, swagger_ui_redirect}`,
the same on a mounted sub-application (`/v1/docs`). The finding withdrawn in this trace: reading `routes()` for the
sharpit mount itself; `FastApiIntrospector(exclude_mount=...)` already removes it (`introspector.py:420-426`).

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D6 | GET report, MCP report tool and CLI report command after a scan | Critical | Return the cached or initial report; do not read the route table or middleware, do not call the host, open no socket | Integration (`no_side_effects`, call counts) |
| 2 | D3 | `docs_url` carries a secret-looking segment | Critical | The path in evidence passes the engine masker; the finding is still produced; the secret is absent from route, MCP and CLI output | Integration |
| 3 | D5 | `openapi_url=None`, `docs_url` default (worst case) | High | No PT-A05-041; scan is complete | Integration |
| 4 | D5 | `docs_url="/api/docs"`, `redoc_url=None` | High | Evidence lists `/api/docs` and `/openapi.json`; `/docs/oauth2-redirect` is not listed | Integration |
| 5 | D5 | Default FastAPI app | High | One PT-A05-041 with severity INFO, confidence Medium and evidence `Detected developer-tooling mapping(s): /docs, /openapi.json, /redoc. Anonymous reachability was not tested.` | Integration; Golden |
| 6 | D5 | A user route named `/users/docs` or a user endpoint called `swagger_ui_html` in another module | High | Not flagged: match on module and qualified name, not on path or bare name | Unit |
| 7 | D5 | Sub-application mounted at `/v1` with its own documentation | High | `/v1/docs`, `/v1/openapi.json`, `/v1/redoc` listed | Integration |
| 8 | D5 | Introspection raises, `routes` is missing, or the app is not FastAPI | High | No finding; scan PARTIAL; gap `route metadata was unavailable`; coverage A02 INDETERMINATE; never a clean pass | Unit; Integration |
| 9 | D5 | Documentation declared by the app attributes but no recognised handler present (framework drift) | High | Gap stated; scan PARTIAL; no finding invented | Unit |
| 10 | D9 | More than 4096 route patterns | High | Patterns past the bound are not inspected; gap `endpoint metadata was incomplete or exceeded the 4096-pattern inspection limit`; scan PARTIAL; A02 INDETERMINATE, other categories unchanged | Unit |
| 11 | D4 | PT-A05-041 and PT-A05-044 DTOs and registry position | High | Id, OWASP category, severity, confidence and order equal the BootUI contract projection; unchanged keys | Golden |
| 12 | D4 | Dismissing PT-A05-041 or PT-A05-044 | High | Applied to the initial, cached and scanned report | Integration |
| 13 | D8 | `ProxyHeadersMiddleware` on the root stack | High | PT-A05-044 INFO; evidence names the middleware and states that trusted proxies and direct reachability were not inspected | Integration |
| 14 | D8 | `ProxyHeadersMiddleware` only on a mounted sub-application | Medium | Reported, evidence names the mount | Integration |
| 15 | D8 | No such middleware | Medium | Silent; report limitation states that server-level forwarded-header flags are not observable | Integration |
| 16 | D8 | Trust flag `trust_any_proxy` set | Medium | PT-A05-044 unchanged (BootUI does not rank the strategy); the security advisor proxy rule is unchanged | Integration |
| 17 | D8 | Host catch-all route `/{path:path}`, a host `TrustedHostMiddleware`, a `root_path` | Medium | Documentation routes still found; route patterns are not prefixed with `root_path`; the sharpit mount never yields a finding | Integration |
| 18 | D10 | MCP `pentest_scan` and CLI `pentest scan` | High | Same evidence as the route action; read-only and disabled refusals unchanged; `checksRun` unchanged | Integration |
| 19 | D4 | Scan without route evidence (older caller) | Medium | No finding; limitation states that route checks were not evaluated | Unit |
| 20 | D4 | Report wording | Medium | Limitation states that route and middleware evidence is static declaration evidence, not authorization or reachability; no Spring or Actuator coverage is implied | Unit |
| 21 | D4 | n-a ledger | Medium | Every one of the 38 framework-evidence IDs is implemented, owned by another lane, or n-a with a reason, exactly once | Unit |
| 22 | D5 | Two documentation routes with the same path (mounts) | Low | Deduplicated and sorted as BootUI does (`LinkedHashSet`, sorted) | Unit |

## Must-cover before merge (Critical + High)

- `test_report_reads_do_not_build_route_evidence` (1)
- `test_docs_route_path_with_a_secret_is_masked_in_evidence` (2)
- `test_openapi_disabled_app_has_no_documentation_finding` (3)
- `test_custom_docs_url_is_reported_without_the_oauth2_redirect` (4)
- `test_default_fastapi_app_reports_developer_tooling` (5)
- `test_user_route_named_docs_is_not_documentation` (6)
- `test_mounted_subapp_documentation_is_reported` (7)
- `test_unavailable_route_metadata_is_incomplete_not_clean` (8)
- `test_unrecognised_documentation_handlers_are_incomplete_not_clean` (9)
- `test_route_inspection_bound_makes_the_scan_partial` (10)
- `test_framework_exposure_findings_match_bootui_contract` (11)
- `test_framework_exposure_findings_can_be_dismissed` (12)
- `test_proxy_headers_middleware_is_reported` (13)
- `test_mcp_and_cli_scan_include_framework_evidence` (18)

## Deferred (Medium + Low): file as issues

- Documentation routes registered by Flask extensions and the Werkzeug debugger, once the Flask adapter has a pentesting
  scan.
- A Python counterpart of PT-A05-040 for a mounted `prometheus_client` application.
- Rows 14, 15, 16, 17, 19, 20, 21 and 22 are covered by tests in the plan; they are not merge blockers.

## Known-issues cross-reference

Introspection drift (`/sharpit:known-issues`, activation and introspection rows): the plan reads only
`RouteInfo` and the existing duck-typed `security_facts`, and degrades to a stated gap. No change touches activation,
the guard chain or masking logic; masking is used, not modified.
