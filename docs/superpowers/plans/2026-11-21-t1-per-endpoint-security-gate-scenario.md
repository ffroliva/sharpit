# Scenario: T1 per-endpoint HTTP security gate

## Coverage map

| Dimension | Status | Reason |
|---|---|---|
| D1. Safe mode fails closed | Active | The observer must remain disabled unless explicitly opted in; it must not activate sharpit or install runtime capture merely because pytest is present. |
| D2. Activation and access guard | Active | Observation must not issue or bypass requests to sharpit's guarded mount; only host traffic already sent by tests is in scope. |
| D3. Secret masking | Active | Requests may carry credentials and response headers may carry cookies; values, query strings, bodies and exception text must never enter facts or reports. |
| D4. BootUI contract parity | Active | T1 has no BootUI counterpart; its new advisor and rules are an explicit sharpit-only deviation and must not claim ported tests or goldens. |
| D5. FastAPI/Starlette introspection drift | Active | ASGI wrappers, mounts and opaque route metadata can prevent reliable route attribution; unknown coverage must remain explicit. |
| D6. No side effects on GET or MCP | Active | The observer must not create network traffic, retain data in files, alter logger levels or mutate the environment. Existing report output remains governed by pytest plugin configuration. |
| D7. OSV/EPSS network failures | Skipped | T1 does not call the vulnerability scanner or perform network access. |
| D8. Host-app integration | Active | Host middleware, root paths, mounts and test-client behavior can change the observed response or hide the observation seam. |
| D9. Scale and limits | Active | Large test suites and route counts require bounded per-request work and an observer-on/off overhead budget. |
| D10. MCP and CLI parity | Skipped | T1 adds no MCP or CLI tool. The new advisor must use existing pytest report outputs only. |

## Worst-case trace

**Input:** an opted-in pytest worker sends an existing request to a FastAPI route under a root path. The request carries `Authorization` and a query token; the response sets a session cookie. An outer ASGI wrapper hides route metadata.

1. `pytest_runtest_protocol` starts a sink attempt for the test node at `src/sharpit/pytest_plugin/__init__.py:384-400`. This provides a possible attribution boundary; the current hook records no HTTP facts.
2. `CaptureMiddleware.__call__` passes non-HTTP requests through at `src/sharpit/fastapi/capture.py:631-633`. It strips sharpit's private probe header and passes through when capture wiring is absent, detached or suspended at `:635-665`.
3. Requests under sharpit's own mount are counted but not captured at `src/sharpit/fastapi/capture.py:666-676`. Other requests enter the existing host-capture path at `:678-697`; any new observer must not change this mount exclusion or the guard chain.
4. `capture_send` records the response status and temporarily holds the complete response-header list at `src/sharpit/fastapi/capture.py:712-725`; it forwards each message immediately and does not buffer response bodies.
5. On completion, route attribution is attempted at `src/sharpit/fastapi/capture.py:763-768`. The exchange row receives request and response headers plus query data at `:769-789`.
6. `exchange_row` converts headers through `_headers` at `src/sharpit/engine/capture/exchanges.py:53-61, 80-130`; masking happens before the existing exchange buffer stores rows. This buffer serves a different contract and must not become a source of raw data for the test advisor.

**Finding:** The current pytest attempt lifecycle does not capture or attribute HTTP exchanges. A naive observer connected to the response-start hook could retain cookie or authorization values before any later masking, while a wrapper with hidden route metadata could be misreported as complete coverage. The implementation must collect only method, canonical route when known, response status and response-header names; attach those facts to the current test attempt; and report unknown/partial when attribution is unavailable. No response body, raw header value, query value or exception message is needed.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D1 | `--sharpit` is enabled but the dedicated HTTP observer option is absent | Critical | No HTTP observer attaches and the app's request/response behavior remains unchanged. | Integration |
| 2 | D1, D8 | Explicitly enabled observer cannot find a unique app or attach to its request path | High | Coverage is `UNKNOWN` or `PARTIAL`; it never reports a clean pass. | Integration |
| 3 | D2, D8 | A test request targets sharpit's own mounted console | Critical | No extra request is generated; the observer does not bypass or weaken the console guard and does not treat console traffic as host endpoint coverage. | Integration |
| 4 | D3, D6 | Authorization, cookie, query and response-cookie values contain secrets | Critical | Facts and all report sinks contain only allowed metadata; no values, query string, body or exception text are retained. | Integration |
| 5 | D5, D8 | FastAPI request uses root path and wrapped/mounted routes | High | A known canonical route is attributed to the correct test attempt; an opaque route produces unknown coverage. | Integration |
| 6 | D5, D8 | Flask request runs through the ordinary in-process test client | High | The same bounded facts are attributed without changing the response; unsupported wrappers degrade to unknown. | Integration |
| 7 | D8 | Host middleware changes or short-circuits the response | High | The observer sees only the response that the test client received and does not reorder or bypass host middleware. | Integration |
| 8 | D4 | A route misses a response header listed in explicit policy | High | A stable finding is emitted for that route and header name; no universal header policy is assumed. | Unit + Integration |
| 9 | D8 | An observed endpoint returns 500, including when an invalid-looking input was sent | Medium | The report records a diagnostic observation only; it does not claim the input was invalid or infer a validation vulnerability. | Integration |
| 10 | D4, D9 | Expected status is explicitly configured for an exercised route | High | Matching observed status is accepted; unexpected status is reported only against declared intent. | Unit |
| 11 | D9 | Many requests and long route/header names are observed | Medium | Per-request work and retained metadata stay bounded; truncation or unsupported data cannot create an unbounded report. | Unit + Integration |
| 12 | D9 | Observer-on overhead is measured against observer-off using the production seam | High | The mandatory budget passes without increasing an existing budget. | Unit |
| 13 | D4, D9 | Findings merge across xdist workers and existing/new baseline entries | High | Existing report, severity, report-only and baseline semantics remain intact; unstable or unknown coverage is not waived. | Integration |

## Must-cover before merge (Critical + High)

- `test_http_security_observer_disabled_by_default`
- `test_http_security_observer_unknown_when_app_or_route_unobservable`
- `test_http_security_observer_excludes_sharpit_mount`
- `test_http_security_observer_omits_secrets_and_response_body`
- `test_http_security_observer_attributes_fastapi_request_to_test_attempt`
- `test_http_security_observer_attributes_flask_request_to_test_attempt`
- `test_http_security_observer_preserves_host_middleware_response`
- `test_http_security_missing_configured_response_header_finding`
- `test_http_security_expected_status_suppresses_finding`
- `test_http_security_observer_bounds_metadata_for_large_runs`
- `test_http_security_observer_overhead_within_budget`
- `test_http_security_report_merges_xdist_findings_and_baselines`

## Deferred (Medium + Low)

- Observed 500 diagnostics: `test_http_security_observed_500_is_diagnostic_only`.
- Truncation behavior for unusually long route/header names: include with the bounded-metadata tests if the final contract truncates instead of marking coverage partial.
- Production TLS termination, reverse-proxy headers and browser behavior: outside in-process test observation; track separately if deployment-edge coverage is required.
- Generic authentication, tenant ownership, fail-closed identity and response-body disclosure assertions: remain application-authored tests until the application supplies explicit intent and safe bounded evidence.

## Known-issues cross-reference

- `KNOWN_ISSUES.md` is absent in this worktree.
- The design spec §14 records T1's no-counterpart boundary; §15 coordinator calls #3-5 constrain activation, dev signals and guard behavior. T1 does not change those paths.
- T1 does not touch activation, the guard chain, masking, introspection or OSV implementation. Its BootUI difference is also recorded in `docs/reference/matrix-updates/0.8.0-t1.tsv`.
