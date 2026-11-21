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
| D9 Scale and limits | Active: response retention and cooperative async deadline are bounded. The probe runs on the request event loop; synchronous code that blocks it stalls the host and cannot be interrupted. |
| D10 MCP and CLI parity | Active: BootUI exposes `get_pentest_report` and `pentest_scan` through MCP and `pentest report` and `pentest scan` through CLI. Port these with the normal gates. |

## Worst-case trace (input, file:line steps, what it found or why a finding was withdrawn)

**Input:** a scan POST runs against a host that emits a listener-only `Server` header, rejects the synthetic Host, then blocks synchronously on another request.

1. `src/sharpit/fastapi/adapter.py:96` installs the guard middleware; `src/sharpit/fastapi/routes/__init__.py:702` composes the current routes. No pentesting route exists yet, so current behavior remains the mount's 404 (`adapter.py:226-231`).
2. BootUI `PentestingScanner.java` at v2.5.0 builds the fixed missing-resource path and sends GET then OPTIONS. GET uses `Accept: text/html`; OPTIONS uses `Origin: https://evil.example` and `Access-Control-Request-Method: GET` (`bootui-engine/.../PentestingScanner.java:40-45,151-171`). Its test asserts the two methods in order (`PentestingScannerTests.java:562-563`). The one-GET description is incorrect.
3. The in-process ASGI call bypasses Uvicorn's response layer. Uvicorn adds `Server` when configured (`uvicorn/config.py:499`); BootUI's PT-A05-011 checks `Server` and `X-Powered-By` (`PentestingChecks.java:860-906`). Missing listener-only headers therefore mean unobserved evidence, not a clean result.
4. Starlette `TrustedHostMiddleware` returns 400 for an unparseable Host (`starlette/middleware/trustedhost.py:42-47`) and also rejects a parsed Host that is not in `allowed_hosts` (`:58-62`). Treat either rejection as incomplete evidence before evaluating missing-header rules.
5. `src/sharpit/engine/singleflight.py:61-75` keeps a flight until caller and workers finish; its `Flight` helper retains a worker-backed flight until that worker ends. Running the probe as a cooperative async task on the request event loop avoids creating an uninterruptible worker for this probe: cancellation releases the action in `finally`, then the next scan can acquire it. Synchronous host code blocking the loop stalls the host and prevents deadline delivery. (The implementation pattern for async tool calls is visible at `src/sharpit/engine/tools04/database_advisor.py:55-61`.)
6. BootUI checks PT-A05-002 only for statuses other than 1xx, 204, 205, and 3xx, while PT-A05-006 requires an error status or stack marker (`PentestingChecks.java:250-253,535-538`). A catch-all 200 at the fixed missing path could therefore look clean for error-body checks; require 404, otherwise mark those checks indeterminate.

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
| 10 | D9 | Oversized body/header or cooperative async handler exceeds deadline | High | Apply BootUI bounds; cancellation releases single-flight so a subsequent scan can proceed. | Integration |
| 11 | D10 | MCP and CLI report/scan requests | High | Catalog, compact MCP/CLI scan summary, read-only report shape, gates, and parity membership match BootUI. | Integration |
| 12 | D2/D9 | Scans overlap or a cooperative probe exceeds deadline | High | Concurrent action receives busy response; timed-out cooperative probe releases the flight and the next scan succeeds. | Integration |
| 13 | D4 | Listener-only disclosure header is absent in ASGI | High | Report the dependent result as incomplete, never as a clean pass. | Integration |
| 14 | D4 | Check registry order is changed | Medium | Independent assertion catches order drift. | Unit |
| 15 | D4 | Report content is dismissed | Medium | PT rule ownership and cached/initial/scanned dismissal application match advisor behavior. | Integration |
| 16 | D4/D8 | Catch-all host route returns non-404 for the fixed path | High | Mark PT-A05-006 and other error-body-derived checks indeterminate and include response status in evidence. | Integration |
| 17 | D5/D8 | Probe passes through middleware layers | High | Invoke the outermost host ASGI app as served; host middleware runs and sharpit's mount `GuardMiddleware` does not run on the probe path. | Integration |
| 18 | D4 | BootUI socket capture compared with in-process ASGI evidence | Medium | Compare a hand-derived ASGI golden byte-for-byte; compare BootUI-derived rule fields and order separately. | Golden |
| 19 | D4 | Synthetic response is a redirect | Medium | Follow BootUI no-follow semantics: evaluate the returned 3xx according to each rule; do not label 3xx alone incomplete. | Unit |
| 20 | D10 | Scan tool result shape or CLI fail-on classification drifts | Medium | Return the compact summary from MCP/CLI; include both tools in advisor gate and CLI parity classifications. | Integration |
| 21 | D10 | Pentest tools are omitted from CLI fail-on and parity inventories | Medium | Both tools are gated/classified and carry the BootUI CLI parity marker. | Integration |

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
- `test_probe_response_limits_and_cooperative_deadline_release_singleflight`
- `test_scan_after_host_handler_outlives_deadline_succeeds`
- `test_non_404_synthetic_response_makes_error_rules_indeterminate`
- `test_probe_uses_outermost_host_asgi_app_without_sharpit_guard_middleware`
- `test_listener_only_headers_are_incomplete_not_clean`
- `test_pentesting_mcp_and_cli_actions_match_bootui_gates`
- `test_pentesting_scan_singleflight_releases_after_probe_failure`
- `test_pentest_scan_tools_return_bootui_compact_summary`
- `test_pentest_tools_are_classified_for_cli_fail_on_and_bootui_parity`

## Deferred (Medium + Low): file as issues

- Browser presentation details beyond the report contract.
- Route inventory or broad security-advisor checks outside the fixed synthetic request.

## Known-issues cross-reference

No A10 known-issue entry exists in the checked-in registry. The in-process ASGI transport cannot observe headers added below the application by a server listener and cannot interrupt synchronous host code that blocks the event loop. These limits are explicit in the report and deviation matrix.

## Finding reconciliation

| Finding | Found by | Verdict | Evidence | Resolution |
|---|---|---|---|---|
| Non-404 answer to the fixed path can look like a clean error-page result | Review A | VERIFIED | BootUI `PentestingChecks.java:250-254,535-538`; scenario trace step 6 | Require 404; non-404 makes body-derived checks indeterminate with status evidence; named test added; matrix row `pentesting:non-404`. |
| Probe execution location determines cancellation and single-flight behavior | Review A | VERIFIED | `src/sharpit/engine/singleflight.py:27-75`; `engine/tools04/database_advisor.py:51-61` | Run cooperative async work on request loop, acquire with `try_acquire`, cancel/release in `finally`; test deadline then successful next scan; document synchronous blocking limit; matrix row `pentesting:event-loop`. |
| ASGI entry point must include host middleware and bypass Sharpit's mount guard | Review A | VERIFIED | `src/sharpit/fastapi/adapter.py:91-110`; route composition `src/sharpit/fastapi/routes/__init__.py:702` | Specify outermost host ASGI app and test middleware traversal/guard absence. |
| BootUI socket capture cannot be the exact ASGI golden | Review A | VERIFIED | BootUI `PentestingChecks.java:860-906` evaluates `Server`/`X-Powered-By`; `PentestingLocalHttpResponse.java:19-125` captures response metadata, while direct ASGI invocation has no Uvicorn listener layer | Keep a hand-derived ASGI exact golden and a separate BootUI-derived rule projection. |
| Treating every redirect as incomplete differs from BootUI | Review A | VERIFIED | BootUI `PentestingChecks.java:250-254`; `JavaPentestingLocalHttpClient.java:23-35` sets `Redirect.NEVER` | Evaluate returned 3xx under individual BootUI checks; 3xx alone is not incomplete; add test, no matrix deviation needed. |
| TrustedHost citation omitted the allowed-host rejection branch | Review A | VERIFIED | Starlette `middleware/trustedhost.py:42-62` | Cite malformed and disallowed-host branches; pin literal loopback rejection as incomplete. |
| High-tier review disposition was not explicitly a prerequisite | Review A | VERIFIED | Root `AGENTS.md` safety model; plan review gate and Definition of done | Retain a neutral required-review gate before implementation; disposition remains pending for the coordinator's review. |
| Current artifacts must not retain a one-request probe or shared-runner claim | Review B | VERIFIED | Scenario trace steps 2–3 and plan Task 1 step 1 define GET then OPTIONS; the current plan has no shared-runner commitment | Keep the current scenario and plan as the implementation contract; the obsolete claims are absent from public artifacts. |
| MCP/CLI scan tools need BootUI compact summary, distinct from HTTP report DTO | Review C | VERIFIED | BootUI `McpScanSummaries.java:175-201,353-362`; CLI catalogue `bootui-cli/src/main/resources/bootui-tools.json:1001-1021` | Specify full DTO for POST and compact summary for MCP/CLI; add response-shape test. |
| Empty-list pentesting golden cannot be marked matched | Review C | VERIFIED | `tests/parity/test_routes_parity.py:52-60`; 2.3.0 `meta.json:584-587` classifies empty `pentesting/captured.json` | Plan sets `n-a` with the specified reason if the route golden remains empty; otherwise classify the actual fixture. |
| CLI fail-on and parity memberships are required for both tools | Review C | VERIFIED | `tests/cli/test_fail_on.py:521-530`; `tests/parity/test_tools_parity.py:44-177,285-328` | Add both tool names to `ADVISOR_TOOLS`, `MATCHED_TOOLS`, CLI BootUI markers, and update the pin. |
| Tool execution must dispatch to the host event loop when available | Review C | VERIFIED | `src/sharpit/engine/tool_dispatch.py:31-90`; `engine/tools04/database_advisor.py:51-61` | Specify established loop submission pattern and use `asyncio.run` only when no host loop runs. |
