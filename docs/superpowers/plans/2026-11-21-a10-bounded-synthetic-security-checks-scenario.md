# Scenario: A10 bounded synthetic security checks

## Coverage map (active dimensions, and why the others are skipped)

| Dimension | Coverage |
|---|---|
| D1 Safe mode fails closed | Active: scan POST must be unreachable while sharpit is inactive. |
| D2 Activation and access guard | Active: preserve guard order, enabled panel, and read-only refusal. |
| D3 Secret masking | Active: host response headers and error bodies may contain credentials. |
| D4 BootUI contract parity | Active: preserve report DTO, rule order, IDs, severities, and evidence within the documented transport adaptation. |
| D5 Framework drift | Active: ASGI scope, middleware, and response behavior vary across supported versions. |
| D6 Read purity | Active: report GET never invokes the host or probe. MCP reads share this property. |
| D7 OSV/EPSS failures | Skipped: this lane does not use vulnerability feeds. |
| D8 Host integration | Active: middleware, root path, and mounted route interactions affect the synthetic request. |
| D9 Scale and limits | Active: response retention and cooperative async deadline are bounded. A synchronous host callable that blocks the event loop cannot be interrupted in-process; report this limit and do not claim a hard deadline. |
| D10 MCP and CLI parity | Active: BootUI exposes `get_pentest_report` and `pentest_scan` through MCP and `pentest report` and `pentest scan` through CLI. Port these with the normal gates. |

## Worst-case trace (input, file:line steps, what it found or why a finding was withdrawn)

**Input:** a scan POST runs against a host that emits a listener-only `Server` header, rejects the synthetic Host, then blocks synchronously on another request.

1. `src/sharpit/fastapi/adapter.py:96` installs the guard middleware; `src/sharpit/fastapi/routes/__init__.py:702` composes the current routes. No pentesting route exists yet, so current behavior remains the mount's 404 (`adapter.py:226-231`).
2. BootUI `PentestingScanner.java` at v2.5.0 builds the fixed missing-resource path and sends GET then OPTIONS. GET uses `Accept: text/html`; OPTIONS uses `Origin: https://evil.example` and `Access-Control-Request-Method: GET` (`bootui-engine/.../PentestingScanner.java:40-45,151-171`). Its test asserts the two methods in order (`PentestingScannerTests.java:562-563`). The one-GET description is incorrect.
3. The in-process ASGI call bypasses Uvicorn's response layer. Uvicorn adds `Server` when configured (`uvicorn/config.py:499`); BootUI's PT-A05-011 checks `Server` and `X-Powered-By` (`PentestingChecks.java:860-906`). Missing listener-only headers therefore mean unobserved evidence, not a clean result.
4. Starlette `TrustedHostMiddleware` returns `400 Invalid host header` when the synthetic Host is not allowed (`starlette/middleware/trustedhost.py:42-47`). Treat this response as incomplete evidence before evaluating missing-header rules.
5. `src/sharpit/engine/singleflight.py:61-75` keeps a flight until caller and workers finish. Async cancellation can release only cooperative work. A synchronous callable blocking the event loop prevents timeout delivery; the in-process guarantee must state this limitation and must not promise that such code is stopped.

**Finding:** the design needs the BootUI two-request contract, incomplete results for evidence the ASGI layer cannot observe, explicit Host rejection handling, and a cooperative-only deadline statement. No current behavior is withdrawn because the endpoint is not implemented.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D1 | Inactive sharpit receives scan POST | Critical | All mount paths return 404; no probe runs. | Integration |
| 2 | D2 | Scan targets disabled or read-only panel | Critical | Existing panel denial; no host invocation. | Integration |
| 3 | D2 | Cross-site request or rejected Host reaches scan | Critical | Guard rejects before action. | Integration |
| 4 | D3 | Probe response contains secrets and stack text | Critical | Raw values and exception text never leave the probe. | Unit |
| 5 | D4 | Report includes null DTO fields and stable rule order | High | Complete camelCase contract and BootUI order/IDs/severities. | Golden |
| 6 | D5/D8 | Probe runs with root path and host middleware | High | Explicit ASGI scope; unsupported behavior is incomplete. | Integration |
| 7 | D6 | Report GET before and after scan | Critical | No host invocation, probe, socket, filesystem, logger, or environ side effect. | Integration |
| 8 | D6/D8 | Explicit scan invokes host middleware | Medium | One GET and one OPTIONS may produce host-side access logs, telemetry, metrics, or cookies as ordinary host request effects; only the explicit gated action permits them. | Integration |
| 9 | D8 | Host raises or returns a TrustedHost 400 | High | Report incomplete evidence; no false header findings; host remains usable. | Integration |
| 10 | D9 | Oversized body/header or cooperative async handler exceeds deadline | High | Apply BootUI bounds and report truncation/timeout as incomplete. Synchronous event-loop blocking remains an explicit transport limit. | Unit |
| 11 | D10 | MCP and CLI report/scan requests | High | Catalog matches BootUI; reads are passive; actions require enablement, guard, panel, read-only, and single-flight gates. | Integration |
| 12 | D2/D9 | Scans overlap or a probe fails | High | Concurrent action receives busy response; failed cooperative probe releases the flight. | Integration |
| 13 | D4 | Listener-only disclosure header is absent in ASGI | High | Report the dependent result as incomplete, never as a clean pass. | Integration |
| 14 | D4 | Check registry order is changed | Medium | Independent assertion catches order drift. | Unit |
| 15 | D4 | Report content is dismissed | Medium | PT rule ownership and cached/initial/scanned dismissal application match advisor behavior. | Integration |

## Must-cover before merge (Critical + High): one pytest name per row

- `test_inactive_pentesting_scan_is_not_found_and_does_not_probe`
- `test_pentesting_scan_respects_disabled_and_read_only_panel_gates`
- `test_pentesting_scan_is_rejected_by_guard_before_probe`
- `test_findings_never_echo_response_secrets_or_exception_text`
- `test_pentesting_report_golden_has_complete_dto_and_bootui_order`
- `test_asgi_probe_scope_handles_root_path_and_unsupported_response_as_incomplete`
- `test_pentesting_report_get_does_not_invoke_host_or_probe`
- `test_explicit_scan_invokes_only_the_two_expected_host_requests`
- `test_host_probe_exceptions_and_trusted_host_rejections_become_incomplete`
- `test_probe_response_limits_and_cooperative_deadline_report_incomplete_evidence`
- `test_listener_only_headers_are_incomplete_not_clean`
- `test_pentesting_mcp_and_cli_actions_match_bootui_gates`
- `test_pentesting_scan_singleflight_releases_after_probe_failure`

## Deferred (Medium + Low): file as issues

- Browser presentation details beyond the report contract.
- Route inventory or broad security-advisor checks outside the fixed synthetic request.

## Known-issues cross-reference

No A10 known-issue entry exists in the checked-in registry. The in-process ASGI transport cannot observe headers added below the application by a server listener and cannot interrupt synchronous host code that blocks the event loop. These limits are explicit in the report and deviation matrix.
