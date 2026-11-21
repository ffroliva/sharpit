# Scenario: A11 CORS preflight checks

## Coverage map (active dimensions, and why the others are skipped)

| Dimension | Coverage |
|---|---|
| D1 Safe mode fails closed | Active: the CORS checks run only inside the existing gated scan action; an inactive mount still answers 404 and sends no probe. |
| D2 Activation and access guard | Active: no new route, tool or action; the existing scan gates (enabled panel, not read-only, guard chain, single-flight) are the only way to reach the checks. |
| D3 Secret masking | Active: CORS response headers are host-controlled; evidence may name only a fixed vocabulary, never an arbitrary host value. |
| D4 BootUI contract parity | Active: IDs, titles, severities, confidence, evidence text, registry order, thresholds and the preflight-incomplete diagnostic of BootUI v2.5.0. |
| D5 Framework drift | Active: `CORSMiddleware` answers a preflight differently across Starlette versions and when configured with `allow_origin_regex`; hosts without CORS middleware answer 405 or 200 without headers. |
| D6 Read purity | Active: report GET, MCP report read and CLI report read must still send no probe; no new GET path exists. |
| D7 OSV/EPSS failures | Skipped: no vulnerability feed is used. |
| D8 Host integration | Active: the OPTIONS probe already exists (A10); host middleware order, TrustedHost rejection and catch-all OPTIONS handlers change what the preflight observes. |
| D9 Scale and limits | Active: per-header retention limits decide whether a CORS header is known; oversized or missing values must not read as absent. |
| D10 MCP and CLI parity | Active but unchanged in shape: the compact scan summary counts findings; only the finding set grows. |

## Starting point (what A10 already provides)

- The scan already sends exactly one GET then one OPTIONS (`Origin: https://evil.example`,
  `Access-Control-Request-Method: GET`) to the fixed missing-resource path (`src/sharpit/fastapi/pentesting_probe.py`).
  A11 therefore adds **no request**; it consumes the OPTIONS response and, for PT-A05-073, the GET response that A10 already
  retains.
- `RULE_ORDER` already lists PT-A05-007, -008, -065, -023, -073 and -024 in BootUI registry order; PT-A05-024 and
  PT-A05-069 are already emitted. The report states CORS checks as "pending" in three places (`report.py` limitation,
  `_SCANNED_DESCRIPTIONS["A02:2025"]`, and the matrix row `pentesting:cors-pending`).
- `SyntheticResponse` records only a single `headers_truncated` flag. BootUI v2.5.0 records which header names are
  incomplete (`PentestingLocalHttpResponse.incompleteHeaderNames`, `headerInventoryIncomplete`), and its CORS checks depend
  on that distinction (`PentestingScannerTests.unrelatedIncompleteOptionsFieldsDoNotSuppressSupportedPolicySignals`).

## BootUI v2.5.0 rules in scope

| ID | Title | Severity / confidence | Evaluation (BootUI source) |
|---|---|---|---|
| PT-A05-069 | Synthetic OPTIONS evidence is incomplete | INFO / Low | `PentestingChecks.java` `OptionsProbeFailedCheck`: fires when the request failed or its headers were truncated; names PT-A05-007, -008, -023, -024, -065 as indeterminate. |
| PT-A05-007 | CORS allows credentialed cross-origin requests | HIGH (LOW for `*`) / Medium | `CredentialedCorsCheck`: successful preflight, permissive origin (`*` or the exact probe origin), `Access-Control-Allow-Credentials` exactly `true`. |
| PT-A05-008 | CORS allows a broad cross-origin request | LOW / Low | `BroadCorsCheck`: successful preflight, no credentials, origin `*` or the exact probe origin. |
| PT-A05-065 | CORS allows the literal 'null' origin | LOW / Low | `CorsNullOriginAllowedCheck`: `Access-Control-Allow-Origin` is exactly `null`. |
| PT-A05-023 | CORS preflight allows any method or header for a permissive origin | LOW / Medium | `BroadCorsMethodsHeadersCheck`: permissive origin and `Access-Control-Allow-Methods: *` or `Access-Control-Allow-Headers: *`, each only when that header is complete. |
| PT-A05-073 | CORS exposes sensitive authentication headers via Access-Control-Expose-Headers | MEDIUM / Medium | `CorsExposeHeadersCheck`: both probes; permissive origin, and an exposed fixed sensitive header or an effective non-credentialed `*`; `Set-Cookie` and `Set-Cookie2` ignored. |
| PT-A05-024 | TRACE or TRACK method advertised | LOW / Low | Already implemented in A10; unchanged. |

`successfulPreflight` is: request not failed, `Access-Control-Allow-Origin` complete, status 200 to 299
(`PentestingResponsePolicies.java`). `matchesOrigin` and the credentials token are exact, case-sensitive string
comparisons.

## Worst-case trace (input, steps, what it found or why a finding was withdrawn)

**Input:** a host with `CORSMiddleware(allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
expose_headers=["X-Api-Key"])` and a TrustedHost-free stack, scanned once; then the same host with a response header
of more than 4,096 characters on the preflight.

1. The gated scan sends the fixed OPTIONS request with the synthetic origin. Starlette `CORSMiddleware` answers a
   preflight (`Origin` plus `Access-Control-Request-Method`) itself with status 200 and reflects the origin when
   credentials are allowed with `allow_origins=["*"]` (it never sends `*` together with credentials), so the observed
   `Access-Control-Allow-Origin` is the probe origin and `Access-Control-Allow-Credentials` is `true`.
2. PT-A05-007 evaluates `permissiveOrigin` against the fixed probe origin constant and the credentials token and
   reports HIGH with the "reflected the untrusted probe origin" evidence; PT-A05-008 is suppressed because credentials
   are present; PT-A05-023 stays silent because Starlette sends an explicit method list, not `*`.
3. PT-A05-073 sees `Access-Control-Expose-Headers` on the actual GET response (the GET probe has no `Origin`, so the
   host may answer `*` or omit the header) and on the preflight; the sensitive name `X-Api-Key` is reported by name.
4. In the second run the oversized header makes one header name incomplete. BootUI keeps the supported signals (the
   other CORS headers are still complete and still evaluated) and also raises PT-A05-069, so a missing finding is
   never read as clean. A10's single `headers_truncated` flag cannot express this: either every CORS rule is
   suppressed or the oversized value is silently ignored. Per-name completeness is therefore a prerequisite.

**Finding:** the checks themselves are small; the risk sits in (a) distinguishing "header absent" from "header
unknown" per name, (b) never echoing a host-controlled value, and (c) wording that stays an observation about the
synthetic in-process preflight, not about a deployed browser-facing edge.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D1/D2 | Inactive sharpit, disabled panel or read-only panel receives a scan | Critical | Unchanged A10 refusals; no OPTIONS request; the CORS checks never run. | Integration (existing gates re-asserted with a CORS-enabled host) |
| 2 | D6 | Report GET, MCP report read and CLI report read after a CORS-bearing scan | Critical | Cached report returned; host call count unchanged; no socket, file, logger or environ effect. | Integration |
| 3 | D3 | Host returns `Access-Control-Allow-Origin: Bearer s3cret-token` (or any non-matching value) | Critical | No finding names the value; the serialized report does not contain it. | Unit and integration |
| 4 | D3 | Host returns an oversized or secret-bearing `Access-Control-Expose-Headers` list | Critical | Only fixed sensitive header names appear in evidence; other tokens are never echoed. | Unit |
| 5 | D3 | Preflight fails with an exception whose text contains a credential | Critical | PT-A05-069 states a fixed incomplete reason; exception text is never retained. | Unit |
| 6 | D4 | Wildcard origin with credentials | High | PT-A05-007 LOW with the browser-rejects wording; PT-A05-008 suppressed. | Unit |
| 7 | D4 | Reflected probe origin with credentials | High | PT-A05-007 HIGH with the reflected-origin wording. | Unit |
| 8 | D4 | Preflight status 302, 400, 403 or 500 carrying permissive headers | High | No PT-A05-007, -008, -023 finding; scan status `SCANNED` unless evidence is incomplete. | Unit |
| 9 | D4 | Origin differs in case, has a trailing slash or is a comma list; credentials token `True` | High | Exact comparison: no match; `True` is not credentials, so PT-A05-008 reports and PT-A05-007 does not. | Unit |
| 10 | D4 | Literal `null` allowed origin | High | PT-A05-065 LOW; no escalation to credentials; non-`null` origins silent. | Unit |
| 11 | D4 | `Allow-Methods: *` and/or `Allow-Headers: *` with a permissive origin; trusted (non-matching) origin | High | PT-A05-023 evidence names exactly the wildcard fields; silent for a non-permissive origin. | Unit |
| 12 | D4 | Exposed `Authorization`, `X-Api-Key`, CSRF token names; `Set-Cookie`; `*` with and without credentials | High | PT-A05-073 reports sensitive names once each; ignores `Set-Cookie` and `Set-Cookie2`; wildcard counts only when non-credentialed and credentials completeness is known. | Unit |
| 13 | D4/D9 | PT-A05-073 evaluated on both probes | High | Preflight half requires a successful preflight; GET half does not; one finding per probe, each naming its own method. | Unit |
| 14 | D9 | One unrelated CORS header name is incomplete (oversized `Access-Control-Allow-Headers`, `Allow`) | High | Supported signals still reported; PT-A05-069 raised; scan `PARTIAL`. | Unit |
| 15 | D9 | The header inventory is incomplete (more than 64 names or 16 KiB of header text) | High | Every CORS rule returns no finding and records a gap; PT-A05-069 raised; A02 coverage `INDETERMINATE`. | Unit |
| 16 | D8/D4 | Preflight request fails, times out or TrustedHost rejects it | High | PT-A05-069 with a fixed reason and the five dependent IDs named as indeterminate; none of those five rules reports. | Integration |
| 17 | D4 | Preflight succeeds with no CORS headers (host without CORS middleware answers 200 or 405) | High | No CORS finding; A02 limitation says actual CORS resource responses and deployed edge behaviour were not tested. | Integration |
| 18 | D5 | Starlette `CORSMiddleware` configured with `allow_origin_regex` or `allow_origins=["*"]` plus credentials | High | Observed headers drive the result; no assumption about configuration; reflected origin classified as in row 7. | Integration against the installed Starlette |
| 19 | D8 | Host catch-all OPTIONS handler returns 200 with wildcard headers | Medium | Reported as the headers observed; evidence is labelled a synthetic preflight of the ASGI app, not a browser result. | Unit |
| 20 | D4 | Registry order and report golden | Medium | CORS findings appear in BootUI order (-007, -008, -065, -023, -073, -024) and match the extended hand-derived golden. | Golden |
| 21 | D4 | Disclaimer and A02 coverage text | Medium | The "pending" wording is removed; the A02 limitation states that actual CORS resource responses and deployed behaviour were not tested; cookie checks remain stated as pending. | Unit |
| 22 | D8 | Duplicate header names with different case in the preflight | Medium | First value is used, as in BootUI; names are matched case-insensitively. | Unit |
| 23 | D10 | MCP and CLI scan summaries after the finding set grows | Medium | Shape unchanged; counts include CORS findings; severity gating in `fail-on` unchanged. | Integration |

## Must-cover before merge (Critical + High): one pytest name per row

- `test_cors_scan_respects_existing_gates_and_sends_no_probe_when_refused` (1)
- `test_report_reads_after_cors_scan_do_not_invoke_host` (2)
- `test_cors_evidence_never_echoes_non_matching_or_secret_origin_values` (3)
- `test_expose_headers_evidence_names_only_fixed_sensitive_headers` (4)
- `test_options_failure_text_is_a_fixed_reason_not_exception_text` (5)
- `test_credentialed_wildcard_origin_is_low_and_browser_blocked` (6)
- `test_credentialed_reflected_origin_is_high` (7)
- `test_non_2xx_preflight_suppresses_origin_dependent_cors_rules` (8)
- `test_origin_and_credentials_comparisons_are_exact` (9)
- `test_null_origin_is_reported_without_credential_escalation` (10)
- `test_wildcard_methods_and_headers_need_a_permissive_origin` (11)
- `test_expose_headers_flags_sensitive_names_and_effective_wildcard_only` (12)
- `test_expose_headers_is_evaluated_per_probe_with_its_own_target` (13)
- `test_unrelated_incomplete_header_name_keeps_supported_cors_signals` (14)
- `test_incomplete_header_inventory_suppresses_cors_rules_with_a_gap` (15)
- `test_options_failure_and_header_truncation_mark_derived_rules_indeterminate` (16)
- `test_preflight_without_cors_headers_is_clean_but_states_the_limit` (17)
- `test_cors_checks_follow_observed_starlette_cors_middleware_behaviour` (18)
- `test_cors_findings_keep_bootui_registry_order_and_golden` (20, Medium kept for the golden)
- `test_options_uses_only_the_fixed_synthetic_origin_and_request_method`
- `test_scan_still_sends_exactly_one_get_and_one_options_request`

## Deferred (Medium + Low): file as issues

- Header-only versus header-and-body OPTIONS truncation: BootUI marks a scan partial for failed or header-truncated
  OPTIONS only; A10 also treats a truncated OPTIONS body as incomplete. A11 keeps A10's stricter rule (recorded as a
  deviation) and does not revisit it.
- BootUI's PT-A05-069 text names five dependent IDs and omits PT-A05-073, although PT-A05-073's preflight half also
  skips silently on a failed preflight. A11 reproduces BootUI's list exactly.
- BootUI's Actuator CORS configuration checks (management endpoint origin and origin-pattern settings) have no Python
  equivalent and stay out of scope.
- Starlette's `CORSMiddleware` expands `allow_methods=["*"]` to an explicit method list and echoes requested headers
  for `allow_headers=["*"]`, so it does not emit a literal `Access-Control-Allow-Methods: *`; PT-A05-023 is exercised
  with a hand-built ASGI preflight responder rather than with that middleware.

## Known-issues cross-reference

No known-issues entry covers the pentesting probe. The relevant standing limits are A10's: listener-added headers,
TLS and outer ASGI wrappers are not observed, and synchronous host code is not interruptible. They apply unchanged.

## Finding reconciliation

| Finding | Found by | Verdict | Evidence | Resolution |
|---|---|---|---|---|
| The OPTIONS probe already exists, so A11 adds no request | Source read | VERIFIED | `pentesting_probe.py` sends GET then OPTIONS; `tests/fastapi/test_pentesting_probe.py::test_probe_uses_bootui_get_then_options_request_sequence` | The plan reuses the existing request; a test pins the request count at two. |
| PT-A05-073 belongs to the CORS set and reads both probes | Source read | VERIFIED | `PentestingChecks.java` `CorsExposeHeadersCheck`; `PentestingCheckRegistry.java` registry line after PT-A05-023 | Included; evaluated on GET and OPTIONS responses. |
| Per-name header completeness is required by BootUI's CORS checks and absent in A10 | Source read | VERIFIED | `PentestingLocalHttpResponse.java` `headersComplete`; BootUI test `unrelatedIncompleteOptionsFieldsDoNotSuppressSupportedPolicySignals` | Task 2 adds `incomplete_header_names` and `header_inventory_incomplete` to the evidence record and the probe. |
| BootUI echoes host header values in CORS evidence | Source read | VERIFIED | `CredentialedCorsCheck`, `BroadCorsCheck`, `BroadCorsMethodsHeadersCheck` evidence strings | Echo only values equal to `*`, `null` or the fixed probe origin; these are already the only values that trigger the evidence. |
| PT-A05-069 evidence includes the transport error text in BootUI | Source read | VERIFIED | `OptionsProbeFailedCheck`; test `scanReportsOptionsProbeFailureSeparatelyFromGetProbeFailure` | Use the probe's fixed incomplete-reason strings; exception text stays out (existing deviation `pentesting:body-evidence`). |
