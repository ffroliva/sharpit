# Scenario: A11 CORS preflight checks

## Coverage map (active dimensions, and why the others are skipped)

| Dimension | Coverage |
|---|---|
| D1 Safe mode fails closed | Active: the CORS checks run only inside the existing gated scan action; an inactive mount still answers 404 and sends no probe. |
| D2 Activation and access guard | Active: no new route, tool or action; the existing scan gates (enabled panel, not read-only, guard chain, single-flight) are the only way to reach the checks. |
| D3 Secret masking | Active: CORS response headers are host-controlled; evidence may name only a fixed vocabulary, never an arbitrary host value or the host's spelling of one. |
| D4 BootUI contract parity | Active: IDs, titles, severities, confidence, evidence text, registry order, thresholds, the trimmed and untrimmed comparisons, and the preflight-incomplete diagnostic of BootUI v2.5.0. |
| D5 Framework drift | Active: `CORSMiddleware` answers a preflight differently across Starlette versions and when configured with `allow_origin_regex`; hosts without CORS middleware answer 405 or 200 without headers. |
| D6 Read purity | Active: report GET, MCP report read and CLI report read must still send no probe; no new GET path exists. |
| D7 OSV/EPSS failures | Skipped: no vulnerability feed is used. |
| D8 Host integration | Active: the OPTIONS probe already exists (A10); host middleware order, TrustedHost rejection and catch-all OPTIONS handlers change what the preflight observes. |
| D9 Scale and limits | Active: per-header retention limits decide whether a CORS header is known; oversized or missing values must not read as absent, and a retained-header flag must never read as "complete". |
| D10 MCP and CLI parity | Active but unchanged in shape: the compact scan summary counts findings; only the finding set grows. |

## Starting point (what A10 already provides)

- The scan already sends exactly one GET then one OPTIONS (`Origin: https://evil.example`,
  `Access-Control-Request-Method: GET`) to the fixed missing-resource path (`src/sharpit/fastapi/pentesting_probe.py`).
  A11 therefore adds **no request**; it consumes the OPTIONS response and, for PT-A05-073, the GET response that A10
  already retains.
- `RULE_ORDER` already lists PT-A05-007, -008, -065, -023, -073 and -024 in BootUI registry order; PT-A05-024 and
  PT-A05-069 are already emitted. The report states CORS checks as "pending" in three places (`report.py` limitation,
  `_SCANNED_DESCRIPTIONS["A02:2025"]`, and the matrix row `pentesting:cors-pending`).
- A10 treats a truncated OPTIONS **body** like a failed OPTIONS request (PT-A05-069, scan `PARTIAL`, A02
  `INDETERMINATE`). BootUI does not: its OPTIONS incompleteness is a failed request or truncated headers
  (`PentestingChecks.java` lines 214 to 221, `PentestingScanner.java` lines 255 to 259, `PentestingCheckRegistry.java`
  lines 415 to 423), and no CORS rule reads the OPTIONS body. A11 aligns with BootUI and changes that A10 behaviour;
  no A10 test pins it.
- `SyntheticResponse` records only a single `headers_truncated` flag. BootUI v2.5.0 records which header names are
  incomplete (`PentestingLocalHttpResponse.incompleteHeaderNames`, `headerInventoryIncomplete`), and its CORS checks
  depend on that distinction (`PentestingScannerTests.unrelatedIncompleteOptionsFieldsDoNotSuppressSupportedPolicySignals`).
  Its legacy constructor makes a bare truncated flag mean an incomplete inventory (`PentestingLocalHttpResponse.java`
  line 38); the Python record keeps that rule.

## BootUI v2.5.0 rules in scope

| ID | Title | Severity / confidence | Evaluation (BootUI source) |
|---|---|---|---|
| PT-A05-069 | Synthetic OPTIONS evidence is incomplete | INFO / Low | `OptionsProbeFailedCheck`: fires when the OPTIONS request failed or its headers were truncated (any incomplete name or an incomplete inventory); names PT-A05-007, -008, -023, -024, -065 as indeterminate. A truncated body alone does not fire it. |
| PT-A05-007 | CORS allows credentialed cross-origin requests | HIGH (LOW for `*`) / Medium | `CredentialedCorsCheck`: requires `Access-Control-Allow-Origin` and `-Credentials` complete; successful preflight, permissive origin (`*` or the exact probe origin, compared untrimmed), credentials exactly `true`. |
| PT-A05-008 | CORS allows a broad cross-origin request | LOW / Low | `BroadCorsCheck`: same required names; successful preflight, no credentials, trimmed origin `*` or the exact probe origin. |
| PT-A05-065 | CORS allows the literal 'null' origin | LOW / Low | `CorsNullOriginAllowedCheck`: requires `Access-Control-Allow-Origin` complete; trimmed value is exactly `null`. |
| PT-A05-023 | CORS preflight allows any method or header for a permissive origin | LOW / Medium | `BroadCorsMethodsHeadersCheck`: requires `Access-Control-Allow-Origin` complete; successful preflight, trimmed permissive origin, and `Access-Control-Allow-Methods: *` or `Access-Control-Allow-Headers: *`, each only when that header is complete. |
| PT-A05-073 | CORS exposes sensitive authentication headers via Access-Control-Expose-Headers | MEDIUM / Medium | `CorsExposeHeadersCheck`: both probes; requires origin and expose-headers complete; permissive trimmed origin (`*`, the fixed probe origin constant, or a match to the request origin, which the GET probe does not send); an exposed fixed sensitive header, or an effective non-credentialed `*` that also needs the credentials header complete; `Set-Cookie` and `Set-Cookie2` ignored. |
| PT-A05-024 | TRACE or TRACK method advertised | LOW / Low | Already implemented in A10; unchanged. |

`successfulPreflight` is: request not failed, `Access-Control-Allow-Origin` complete, status 200 to 299
(`PentestingResponsePolicies.java` lines 28 to 33). `matchesOrigin` and the credentials token are exact,
case-sensitive string comparisons; the credentials token is not trimmed. Header values that occur more than once are
joined with `, ` (`PentestingCheckSupport.header`).

## Worst-case trace (input, steps, what it found or why a finding was withdrawn)

**Input:** a host with `CORSMiddleware(allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
expose_headers=["X-Api-Key"])` and a TrustedHost-free stack, scanned once; then the same host with
`Access-Control-Allow-Credentials` carrying a value of more than 4,096 characters on the preflight.

1. The gated scan sends the fixed OPTIONS request with the synthetic origin. Starlette `CORSMiddleware` answers a
   preflight (`Origin` plus `Access-Control-Request-Method`) itself with status 200 and reflects the origin when
   credentials are allowed with `allow_origins=["*"]` (it never sends `*` together with credentials), so the observed
   `Access-Control-Allow-Origin` is the probe origin and `Access-Control-Allow-Credentials` is `true`.
2. PT-A05-007 evaluates the permissive origin against the fixed probe origin constant and the credentials token and
   reports HIGH with the "reflected the untrusted probe origin" evidence; PT-A05-008 is suppressed because credentials
   are present; PT-A05-023 stays silent because Starlette sends an explicit method list, not `*`.
3. PT-A05-073 sees `Access-Control-Expose-Headers` on the actual GET response (the GET probe has no `Origin`, so the
   host may answer `*` or omit the header) and on the preflight; the sensitive name is reported by its fixed spelling.
4. In the second run the oversized credentials value makes that one name incomplete and absent from the retained
   headers. A rule that read only the retained dictionary would see no credentials and report PT-A05-008 LOW for a
   host that actually allows credentials. The rule requires `Access-Control-Allow-Credentials` complete, so
   PT-A05-007 and PT-A05-008 are withheld with a gap and PT-A05-069 is raised (headers truncated); PT-A05-065 and the
   other rules that do not require that name still evaluate. A single `headers_truncated` flag cannot express this:
   per-name completeness is a prerequisite.

**Finding:** the checks themselves are small; the risk sits in (a) distinguishing "header absent" from "header
unknown" per name, (b) never echoing a host-controlled value or spelling, and (c) wording that stays an observation
about the synthetic in-process preflight, not about a deployed browser-facing edge.

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
| 13 | D4/D9 | PT-A05-073 evaluated on both probes | High | Preflight half requires a successful preflight; GET half does not; one finding per probe, each naming its own method; the OPTIONS finding precedes the GET finding. | Unit |
| 14 | D9 | One unrelated CORS header name is incomplete (oversized `Access-Control-Allow-Headers`, `Allow`) | High | Supported signals still reported; PT-A05-069 raised through header truncation; scan `PARTIAL`. | Unit |
| 15 | D9 | The header inventory is incomplete (more than 64 names or 16 KiB of header text) | High | Every CORS rule returns no finding and records a gap; PT-A05-069 raised; A02 coverage `INDETERMINATE`. | Unit |
| 16 | D8/D4 | Preflight request fails, times out or TrustedHost rejects it | High | PT-A05-069 with a fixed reason and the five dependent IDs named as indeterminate; none of those five rules reports; a fixed limitation states that PT-A05-073 is indeterminate too. | Integration |
| 17 | D4 | Preflight succeeds with no CORS headers (host without CORS middleware answers 200 or 405) | High | No CORS finding; A02 limitation says actual CORS resource responses and deployed edge behaviour were not tested. | Integration |
| 18 | D5 | Starlette `CORSMiddleware` configured with `allow_origin_regex` or `allow_origins=["*"]` plus credentials | High | Observed headers drive the result; no assumption about configuration; reflected origin classified as in row 7. | Integration against the installed Starlette |
| 19 | D8 | Host catch-all OPTIONS handler returns 200 with wildcard headers | Medium | Reported as the headers observed; evidence is labelled a synthetic preflight of the ASGI app, not a browser result. | Unit |
| 20 | D4 | Registry order and report golden | Medium | CORS findings appear in BootUI order (-007, -008, -065, -023, -073, -024) and match the extended hand-derived golden. | Golden |
| 21 | D4 | Disclaimer and A02 coverage text | Medium | The "pending" wording is removed; the A02 limitation states that actual CORS resource responses and deployed behaviour were not tested; cookie checks remain stated as pending. | Unit |
| 22 | D8 | A CORS header sent twice (names differ in case) | High | Names match case-insensitively and the values are joined with `, ` as in BootUI, so a duplicated `Access-Control-Allow-Origin` is a comma list that matches nothing. | Unit |
| 23 | D10 | MCP and CLI scan summaries after the finding set grows | Medium | Shape unchanged; counts include CORS findings; severity gating in `fail-on` unchanged. | Integration |
| 24 | D4/D9 | OPTIONS body truncated, headers complete | Critical | No PT-A05-069, scan status `SCANNED` (when GET is complete), A02 coverage not `INDETERMINATE`, CORS rules evaluate; the existing body-limit limitation line stays. | Unit |
| 25 | D9 | A required name is incomplete, others complete: `Access-Control-Allow-Credentials` for -007/-008, `Access-Control-Allow-Origin` for -065/-023/-073, `Access-Control-Expose-Headers` for -073, credentials for the -073 wildcard | Critical | The rule is withheld with one fixed gap string and is never downgraded to a weaker finding; -073 still reports a sensitive name when only credentials is incomplete. | Unit (rule by required-name table) |
| 26 | D9 | A response built with only the legacy `headers_truncated=True`, and a response that carried HTTP trailers | Critical | The inventory counts as incomplete; every CORS rule returns no finding and records a gap. | Unit |
| 27 | D9 | Header retention boundaries (name count, name length, value count, value length, 16 KiB budget, blank name) | High | The pure bounding function reports the same incomplete names and inventory flag as BootUI for each boundary; an incomplete name is never reported as absent. | Unit |
| 28 | D3 | Origin padded with whitespace; `X-API-KEY` or `x-xsrf-token` in the expose list | High | Evidence shows the constant (`*`, `null` or the probe origin) and the fixed spelling of each sensitive name, never the host's spelling. | Unit |
| 29 | D4 | Padded `*` origin on the preflight; credentials ` true`; GET answers the fixed probe origin or another origin with an exposed sensitive header | High | PT-A05-007 compares the origin untrimmed and the credentials token untrimmed; -008, -023, -065 and -073 trim; the -073 GET half treats only `*` and the fixed probe origin constant as permissive. | Unit |
| 30 | D9 | Evidence limit reached: every CORS gap, every probe limitation and the standing statements at once | High | The standing limitations survive the 20-entry cap; gaps are deduplicated. | Unit |
| 31 | D4 | A scan is partial and also has A02 findings | Medium | A02 coverage stays `INDETERMINATE` (stricter than BootUI, which keeps the finding status); recorded as a deviation. | Unit |

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
- `test_expose_headers_withheld_states_a_limitation_naming_the_rule` (16)
- `test_preflight_without_cors_headers_is_clean_but_states_the_limit` (17)
- `test_cors_checks_follow_observed_starlette_cors_middleware_behaviour` (18)
- `test_duplicate_cors_header_values_are_joined_like_bootui` (22)
- `test_truncated_options_body_alone_is_complete_evidence_for_cors` (24)
- `test_incomplete_required_name_withholds_rule_and_records_gap` (25, parametrized rule by required name)
- `test_a_bare_headers_truncated_flag_implies_inventory_incomplete` (26)
- `test_trailers_response_marks_the_header_inventory_incomplete` (26)
- `test_bare_truncated_flag_suppresses_every_cors_rule` (26)
- `test_bound_headers_reports_incomplete_names_and_inventory_at_each_boundary` (27, parametrized)
- `test_an_incomplete_header_name_is_not_reported_as_absent` (27)
- `test_cors_evidence_echoes_only_constants_and_fixed_spellings` (28)
- `test_origin_is_untrimmed_for_credentialed_cors_and_trimmed_elsewhere` (29)
- `test_expose_headers_get_half_uses_the_fixed_probe_origin` (29)
- `test_standing_limitations_survive_when_every_cors_gap_is_present` (30)
- `test_cors_findings_keep_bootui_registry_order_and_golden` (20, Medium kept for the golden)
- `test_probe_request_uses_the_engine_probe_constants`
- `test_partial_scan_keeps_a02_indeterminate_when_a02_findings_exist` (31, Medium kept to pin the deviation)

Characterization (green before the change; they stay as regression guards and are not red-first):
`test_options_uses_only_the_fixed_synthetic_origin_and_request_method` and
`test_scan_still_sends_exactly_one_get_and_one_options_request`.

## Deferred (Medium + Low): file as issues

- BootUI's Actuator CORS configuration checks (management endpoint origin and origin-pattern settings) have no Python
  equivalent and stay out of scope.
- Starlette's `CORSMiddleware` expands `allow_methods=["*"]` to an explicit method list and sends no
  `Access-Control-Allow-Headers` unless asked, so it does not emit a literal wildcard; PT-A05-023 is exercised with a
  hand-built ASGI preflight responder rather than with that middleware.
- A10's TRACE check reads the first value of a repeated header while BootUI joins the values; the CORS rules follow
  BootUI, and the TRACE check keeps its current accessor until it is revisited.

## Known-issues cross-reference

No known-issues entry covers the pentesting probe. The relevant standing limits are A10's: listener-added headers,
TLS and outer ASGI wrappers are not observed, and synchronous host code is not interruptible. They apply unchanged.

## Finding reconciliation

| Finding | Found by | Verdict | Evidence | Resolution |
|---|---|---|---|---|
| The OPTIONS probe already exists, so A11 adds no request | Source read | VERIFIED | `pentesting_probe.py` sends GET then OPTIONS; `tests/fastapi/test_pentesting_probe.py::test_probe_uses_bootui_get_then_options_request_sequence` | The plan reuses the existing request; a test pins the request count at two. |
| PT-A05-073 belongs to the CORS set and reads both probes | Source read | VERIFIED | `PentestingChecks.java` lines 2830 to 2833; `PentestingCheckRegistry.java` registry order -007, -008, -065, -023, -073, -024 | Included; evaluated on the OPTIONS then GET response. |
| Per-name header completeness is required by BootUI's CORS checks and absent in A10 | Source read | VERIFIED | `PentestingLocalHttpResponse.java` lines 60 to 70 (`headersComplete`); `PentestingChecks.java` lines 566, 606, 647, 1395, 2842 to 2852 (required names per rule) | A pure bounding function and per-name fields; the rules withhold on a missing required name (rows 25 to 27). |
| A truncated OPTIONS body raises PT-A05-069, makes the scan `PARTIAL` and A02 `INDETERMINATE` in A10; BootUI does not | Source read and a run on the A10 branch | VERIFIED | `report.py` lines 213, 228, 251; `evidence.py` line 19; BootUI `PentestingChecks.java` 214 to 221, `PentestingScanner.java` 255 to 259, `PentestingCheckRegistry.java` 395 to 399 and 415 to 423 (`optionsBodyTruncated` is not an input); no A10 test pins it | Port BootUI: OPTIONS incompleteness is a failed request or truncated headers; the body limit stays a limitation line only (row 24). |
| A bare `headers_truncated=True` or an HTTP trailers response must mean an incomplete inventory | Source read | VERIFIED | `PentestingLocalHttpResponse.java` line 38 (legacy constructor) and line 55; `pentesting_probe.py` lines 75 and 76 set only the flag | `SyntheticResponse` derives `header_inventory_incomplete` from a bare flag (row 26). |
| A rule reading the retained dictionary alone reads a missing required name as absent | Source read | VERIFIED | Required-name checks in `PentestingChecks.java` lines 566, 606, 647, 1395, 2842 to 2852, 2898 to 2899; the existing rows 14 and 15 cover only unrelated names | Rule-by-required-name table test (row 25). |
| `_retain` is at the complexity limit | Lint run | VERIFIED | `ruff --select C901` on `pentesting_probe.py` reports `_retain` at 10; `tests/test_code_shape.py` forbids a new function over 10 | BootUI's `boundedHeaders` (`PentestingLocalHttpResponse.java` 77 to 137) is ported as one pure function; the probe calls it (row 27). |
| BootUI echoes host header values in CORS evidence | Source read | REFUTED as stated | -007 echoes a value only after an exact `*` or probe-origin match (line 570 to 583); -008 and -023 echo the untrimmed value after a trimmed match (lines 613 to 625, 1402 to 1425); -073 echoes the trimmed origin and the host's spelling of a sensitive token after a fixed-name match (lines 2860 to 2910); -065 echoes nothing | Echo constants only: `*`, `null`, the probe origin, and a fixed spelling per sensitive name. The only change from BootUI is trimming and spelling (row 28). |
| -007 compares the origin untrimmed while -008, -023, -065 and -073 trim; the credentials token is untrimmed; the -073 GET half uses a fixed origin | Source read | VERIFIED | `PentestingChecks.java` lines 570 to 576, 617 to 618, 1406 to 1408, 2860 to 2863; `PentestingResponsePolicies.java` lines 35 to 38 and 44 to 50; the GET probe sends no `Origin` (`PentestingScanner.java` line 151) | Ported as is, each with a test (row 29). |
| PT-A05-069 omits PT-A05-073 from its dependent list | Source read | VERIFIED | `PentestingChecks.java` line 193 | The 069 text is reproduced; a fixed limitation names PT-A05-073 when its half is withheld (row 16). |
| BootUI joins repeated header values; the scenario assumed the first value | Source read | VERIFIED | `PentestingCheckSupport.header` joins values with `, `; A10 `checks.first` returns the first value | The CORS rules use a joined accessor (row 22). |
| A02 coverage turns `INDETERMINATE` whenever the scan is partial, while BootUI keeps the finding status when A02 findings exist | Source read | VERIFIED | `report.py` `_scanned_status`; `PentestingCheckRegistry.java` lines 269 to 290 | Kept stricter; logged as a deviation with a pinning test (row 31). |
| PT-A05-069 evidence includes the transport error text in BootUI | Source read | VERIFIED | `PentestingChecks.java` lines 214 to 221; test `scanReportsOptionsProbeFailureSeparatelyFromGetProbeFailure` | The fixed incomplete-reason string replaces the exception text (existing deviation `pentesting:body-evidence`). |
| The matrix generator reads no 0.8.0 fragment | Source read | VERIFIED | `scripts/dev/generate_parity_deviations.py` lines 15 to 35 list only the 0.7.0 fragments | The `pentesting:cors-pending` row is deleted, not retired. |
