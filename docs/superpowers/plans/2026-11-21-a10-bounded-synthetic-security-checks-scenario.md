# Scenario: A10 bounded synthetic security checks

## Coverage map (active dimensions, and why the others are skipped)

| Dimension | Coverage |
|---|---|
| D1 Safe mode fails closed | Active: the new POST action must be unreachable while sharpit is inactive. |
| D2 Activation and access guard | Active: scan must follow the existing guard order and panel read-only rules. |
| D3 Secret masking | Active: host response headers and error bodies may contain credentials or implementation details. |
| D4 BootUI contract parity | Active: report DTO, rule order, IDs, severity, and evidence must match v2.5.0 within the documented transport adaptation. |
| D5 Framework introspection drift | Active: ASGI scope, middleware, and response handling vary by Starlette/FastAPI version; test supported floor and current dependency. |
| D6 No side effects on GET or MCP | Active: report GET must not invoke host handlers or probes; there is no MCP scan tool unless BootUI has one. |
| D7 OSV/EPSS network failures | Skipped: A10 does not use the vulnerability service or OSV/EPSS. |
| D8 Host-app integration | Active: middleware, root path, lifespan, and mounted route interactions affect an in-process ASGI request. |
| D9 Scale and limits | Active: response body/header retention and the probe deadline must remain bounded on large or slow host responses. |
| D10 MCP and CLI parity | Active: CLI exposure is only in scope if BootUI's catalogue exposes this action; MCP is read-only by default and must not gain a scan action without a BootUI counterpart. |

## Worst-case trace (input, file:line steps, what it found or why a finding was withdrawn)

**Input:** a local client sends `POST /sharpit/api/pentesting/scan` while the host app has broad CORS and an exception handler that returns a large body containing a credential.

1. `src/sharpit/fastapi/adapter.py:61-75` defines `SharpitMount`, which preserves ownership of the mount path; `adapter.py:249` constructs the mount. The host catch-all cannot take ownership of a path routed inside that mount.
2. `src/sharpit/fastapi/routes/__init__.py:682` assembles the current route set. It has no pentesting route, so the proposed POST currently reaches the active sub-app's 404 path (`adapter.py:226-231`); there is no scan, host invocation, or disclosure today.
3. For a future endpoint, `GuardMiddleware` is declared at `adapter.py:96` and its decision path must be followed before dispatch. The route must also use the existing panel gate/action pattern; current implementation cannot be traced because the feature does not exist.
4. Pinned BootUI v2.5.0 `PentestingScanner.java` builds a fixed synthetic path, sends GET with `Accept: text/html`, and sends OPTIONS with a fixed CORS preflight; it runs both only from `scan()` under `SingleFlightAction`. Its source says the action sends two requests. This contradicts the prediction's one-GET summary. Do not claim parity or implement probe count until the council resolves this against the source and its tests.
5. BootUI `PentestingChecks.java` turns failed/truncated observations into incomplete evidence; verbose error checks inspect markers in a bounded body. Returning the host's body or exception text would make a credential-containing failure leak, so sharpit output must contain only bounded sanitized evidence and must report truncation/failure as incomplete.

**Finding:** no current sharpit behavior is being withdrawn; the endpoint does not exist. The real pre-implementation gap is the predicted probe count versus BootUI's GET+OPTIONS contract. Record the resolution as a condition before code; preserve fail-closed and output-masking gates either way.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D1 | Inactive sharpit receives scan POST | Critical | Every path under the mount remains 404; no app probe runs. | Integration |
| 2 | D2 | Scan POST targets a disabled or read-only pentesting panel | Critical | Existing panel gate returns the contract denial; no host request runs. | Integration |
| 3 | D2 | Cross-site request or rejected Host reaches scan POST | Critical | Guard rejects in existing order before action execution. | Integration |
| 4 | D3 | Synthetic response includes `Authorization`, `Set-Cookie`, secret text, and a stack trace | Critical | Output omits raw body, exception text, and unsafe header values; findings retain only sanitized rule evidence. | Unit |
| 5 | D4 | Report serialization includes null DTO fields and stable rule order | High | Every contract key is present, camelCase, and findings preserve BootUI IDs/order/severity. | Golden |
| 6 | D5/D8 | Host has `root_path`, middleware, and lifespan; synthetic request is invoked | High | ASGI scope and middleware behavior are explicit; unsupported lifespan/stream behavior is incomplete, not a clean pass or host crash. | Integration |
| 7 | D6 | GET report is requested before and after scan | Critical | GET does not invoke host app, probe runner, socket, filesystem, logger mutation, or environ mutation. | Integration |
| 8 | D8 | Host GET handler raises and host middleware raises | High | Scan reports an incomplete probe and remains usable; host application continues serving requests. | Integration |
| 9 | D9 | Host returns oversized headers/body or stalls past deadline | High | Retention and elapsed time are bounded; truncation/timeout is explicit incomplete evidence. | Unit |
| 10 | D10 | CLI or MCP requests scan action | High | CLI is added only if BootUI has the corresponding tool; MCP stays without scan action unless BootUI exposes it. | Unit |
| 11 | D2/D9 | Two scan actions overlap; first raises during probe | High | Second gets the existing busy response; lock releases after failure and a later scan succeeds. | Integration |
| 12 | D4 | A BootUI rule includes raw server/version disclosure in evidence | High | Rule preserves ID and severity while evidence is sanitized and bounded. | Golden |

## Must-cover before merge (Critical + High): one pytest name per row

- `test_inactive_pentesting_scan_is_not_found_and_does_not_probe`
- `test_pentesting_scan_respects_disabled_and_read_only_panel_gates`
- `test_pentesting_scan_is_rejected_by_guard_before_probe`
- `test_findings_never_echo_response_secrets_or_exception_text`
- `test_pentesting_report_golden_has_complete_dto_and_bootui_order`
- `test_asgi_probe_scope_handles_root_path_and_unsupported_lifespan_as_incomplete`
- `test_pentesting_report_get_does_not_invoke_host_or_probe`
- `test_host_probe_exceptions_become_incomplete_evidence`
- `test_probe_response_and_deadline_limits_report_incomplete_evidence`
- `test_scan_action_catalogue_matches_bootui_without_read_only_mcp_action`
- `test_pentesting_scan_singleflight_releases_after_probe_failure`
- `test_server_disclosure_evidence_is_sanitized_and_bounded`

These names are acceptance criteria; task decomposition may combine tests only when one assertion still names each behavior.

## Deferred (Medium + Low): file as issues

- Cosmetic differences in how a browser renders the report: UI is not specified by A10's prediction; defer unless the 2.5.0 contract requires a new surface.
- Large-scale route metadata limits beyond the fixed synthetic request: A10 does not enumerate routes; do not broaden scope into the general security advisor.

## Known-issues cross-reference

No A10 known-issue entry exists in the checked-in known-issues registry. Resolve the GET+OPTIONS versus one-GET mismatch in the A10 council before implementation. The prediction's `A10-transport` and `A10-body` deviations are proposed, not yet accepted; if retained, record them in the A10 matrix fragment and spec §14.
