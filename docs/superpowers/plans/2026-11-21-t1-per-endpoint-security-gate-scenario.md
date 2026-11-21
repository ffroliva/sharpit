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

**Input:** an opted-in pytest worker sends a request through an explicit wrapper to a FastAPI route under a root path. The request carries `Authorization` and a query token; the response sets a session cookie. An outer ASGI wrapper hides route metadata.

1. `pytest_runtest_protocol` starts a sink attempt for the test node at `src/sharpit/pytest_plugin/__init__.py:384-400`. This provides a possible attribution boundary; the current hook records no HTTP facts.
2. `CaptureMiddleware.__call__` passes non-HTTP requests through at `src/sharpit/fastapi/capture.py:631-633`. It strips sharpit's private probe header and passes through when capture wiring is absent, detached or suspended at `:635-665`.
3. Requests under sharpit's own mount are counted but not captured at `src/sharpit/fastapi/capture.py:666-676`. Other requests enter the existing host-capture path at `:678-697`; any new observer must not change this mount exclusion or the guard chain.
4. `capture_send` records the response status and temporarily holds the complete response-header list at `src/sharpit/fastapi/capture.py:712-725`; it forwards each message immediately and does not buffer response bodies.
5. On completion, route attribution is attempted at `src/sharpit/fastapi/capture.py:763-768`. The exchange row receives request and response headers plus query data at `:769-789`.
6. `exchange_row` converts headers through `_headers` at `src/sharpit/engine/capture/exchanges.py:53-61, 80-130`; masking happens before the existing exchange buffer stores rows. This buffer serves a different contract and must not become a source of raw data for the test advisor.

**Finding:** The current pytest attempt lifecycle does not capture or attribute HTTP exchanges. The explicit registration fixture wraps the exact app in a separate ASGI/WSGI callable used by the test client; it does not mutate Starlette's middleware stack. Requests before registration are not observed. Facts contain only an opaque per-attempt attribution key, method, canonical route when known, response status and response-header names, and travel through existing `PhaseFacts`/`TestFacts` serialization to controller-side evaluation after all xdist workers merge. Unmatched 404 routes are known not-found observations and do not degrade coverage unless a configured expectation targets that route. Unknown paths are represented as `None`, never copied raw. No response body, raw header value, query value, exception message or HTTP-observer node ID is retained. Existing masked exception facts remain governed by the current test-session contract.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D1 | `--sharpit` is enabled but the dedicated HTTP observer option is absent | Critical | No HTTP observer attaches and the app's request/response behavior remains unchanged. | Integration |
| 2 | D1, D8 | Explicitly enabled observer cannot find a unique app or attach to its request path | High | A configured expectation with no matching observation is strictly `UNKNOWN`; it never reports `PARTIAL` or a clean pass. | Integration |
| 3 | D2, D8 | A test request targets sharpit's own mounted console | Critical | No extra request is generated; the observer does not bypass or weaken the console guard and does not treat console traffic as host endpoint coverage. | Integration |
| 4 | D3, D6 | Authorization, cookie, query and response-cookie values contain secrets | Critical | Facts and all report sinks contain only allowed metadata; no values, query string, body or exception text are retained. | Integration |
| 5 | D5, D8 | FastAPI request uses root path and wrapped/mounted routes | High | A known canonical route is attributed to the correct test attempt; an opaque route produces unknown coverage. | Integration |
| 6 | D5, D8 | Flask request runs through the ordinary in-process test client | High | The same bounded facts are attributed without changing the response; unsupported wrappers degrade to unknown. | Integration |
| 7 | D8 | Host middleware changes or short-circuits the response | High | The observer sees only the response that the test client received and does not reorder or bypass host middleware. | Integration |
| 8 | D4 | A route misses a response header listed in explicit policy | High | A stable finding is emitted for that route and header name; no universal header policy is assumed. | Unit + Integration |
| 9 | D8 | An observed endpoint returns 500, including when an invalid-looking input was sent | Medium | The bounded observation may remain internal evidence; it creates no finding or separate diagnostic report and never claims the input was invalid. | Integration |
| 10 | D4, D9 | Multiple legitimate statuses are configured for one route, such as 200, 401 and 403 | High | Any configured status is accepted; a status outside the set emits `HTTP-SEC-002` at HIGH severity. | Unit |
| 11 | D9 | Many requests and long route/header names are observed | Medium | Per-request work and retained metadata stay bounded; truncation or unsupported data cannot create an unbounded report. | Unit + Integration |
| 12 | D9 | Observer-on overhead is measured against observer-off using the production seam | High | The mandatory budget passes without increasing an existing budget. | Unit |
| 13 | D4, D9 | Facts and expectations span xdist workers | High | Workers serialize facts without evaluating expectations; the controller evaluates once after merging all worker facts. Existing report, severity, report-only and baseline semantics remain intact; unstable or unknown coverage is not waived. | Integration |
| 14 | D3, D5 | An unmapped route contains a token or email in its path | Critical | Store `None` for unknown routes; raw paths never enter findings or report sinks. | Integration |
| 15 | D4, D9 | Multiple required headers are absent on one route | High | Each header has a distinct stable finding identity and fingerprint. | Unit |
| 16 | D4, D9 | A configured route expectation receives no matching test traffic | High | Coverage is strictly UNKNOWN and baseline writing is refused. | Integration |
| 17 | D5, D8 | A shared or already-started app is registered, a second app is unregistered, or a client bypasses the wrapper | High | A wrapper around the exact registered app remains reusable across tests without changing the app's middleware stack; only requests observed after registration count, and a bypassed expectation is UNKNOWN. | Integration |
| 18 | D4 | A declared expected status does not match the response | High | `HTTP-SEC-002` emits a HIGH finding with a stable route/status identity. | Unit |
| 19 | D4, D9 | A finding is generated after different test names or parameterizations | Medium | The fingerprint stays stable because attempt attribution is separate from finding identity and `test_node_id` is unset. | Unit |
| 20 | D5 | FastAPI and Flask expose the same route with different parameter syntax | Low | Both adapters use the framework-free normalizer and produce the same `{name}` route template, including for Werkzeug converters. | Unit |
| 21 | D4 | A request occurs outside an active test attempt, such as during a session fixture | Medium | Observation records it as unassociated session evidence without raising or attributing it to another test; it cannot satisfy a configured expectation. | Integration |
| 22 | D4 | Expected-status configuration contains a blank route, non-integer status or status outside 100–599 | Low | Pytest reports a configuration error before test execution. | Unit |
| 23 | D4 | An expectation uses a lower-case HTTP method | Low | Parsed and observed methods normalize to uppercase and match. | Unit |

## Must-cover before merge (Critical + High)

- `test_http_security_observer_disabled_by_default`
- `test_http_security_observer_unknown_when_app_or_route_unobservable`
- `test_http_security_fixture_wraps_exact_app`
- `test_http_security_started_app_remains_observable`
- `test_http_security_shared_wrapper_attributes_multiple_test_attempts`
- `test_http_security_multiple_apps_observe_only_registered_app`
- `test_http_security_unobserved_expectation_is_unknown`
- `test_http_security_controller_evaluates_only_after_xdist_merge`
- `test_http_security_xdist_worker_unknown_does_not_fail_before_merge`
- `test_http_security_expected_status_set_accepts_any_listed_status`
- `test_http_security_unexpected_status_finding`
- `test_http_security_multiple_missing_headers_have_distinct_fingerprints`
- `test_http_security_finding_fingerprint_ignores_test_attempt`
- `test_http_security_facts_survive_json_round_trip`
- `test_http_security_unmapped_secret_path_is_not_retained`
- `test_http_security_observer_excludes_sharpit_mount`
- `test_http_security_observer_omits_secrets_and_response_body`
- `test_http_security_observer_attributes_fastapi_request_to_test_attempt`
- `test_http_security_observer_attributes_flask_request_to_test_attempt`
- `test_http_security_observer_preserves_host_middleware_response`
- `test_http_security_observer_handles_request_outside_test_attempt`
- `test_http_security_missing_configured_response_header_finding`
- `test_http_security_expected_status_suppresses_finding`
- `test_http_security_method_is_case_normalized`
- `test_http_security_route_templates_normalize_equally_across_adapters`
- `test_http_security_invalid_expectation_is_rejected`
- `test_http_security_observer_bounds_metadata_for_large_runs`
- `test_http_security_observer_overhead_within_budget`
- `test_http_security_report_merges_xdist_findings_and_baselines`

## Deferred (Medium + Low)

- Observed 500 remains bounded internal evidence without a finding or diagnostic report; no separate report assertion is required.
- Truncation behavior for unusually long route/header names: include with the bounded-metadata tests if the final contract truncates instead of marking coverage partial.
- Production TLS termination, reverse-proxy headers and browser behavior: outside in-process test observation; track separately if deployment-edge coverage is required.
- Generic authentication, tenant ownership, fail-closed identity and response-body disclosure assertions: remain application-authored tests until the application supplies explicit intent and safe bounded evidence.

## Known-issues cross-reference

- The design spec §14 records T1's no-counterpart boundary. T1 does not change activation, development-server signals or guard behavior.
- T1 does not touch activation, the guard chain, masking, introspection or OSV implementation. Its BootUI difference is also recorded in `docs/reference/matrix-updates/0.8.0-t1.tsv`.
