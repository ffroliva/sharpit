# Scenario: A12 cookie and session-cookie pentesting checks

Port of the BootUI v2.5.0 cookie-flag and session-cookie checks onto the bounded synthetic probe of lane A10, merged
after lane A11. The probe responses of A10 are reused: the checks add no request. BootUI sources are at tag `v2.5.0`,
package `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/pentesting/` (`Checks` is `PentestingChecks.java`,
`Support` is `PentestingCheckSupport.java`, `Assessment` is `PentestingAssessment.java`, `Registry` is
`PentestingCheckRegistry.java`).

## Scope

Nine active BootUI checks, in registry order (`Registry.java:57-65`, entries `CookieMissingHttpOnlyCheck` through
`SessionCookieSameSiteNoneWithSecureDisabledCheck`). All nine IDs are already in `RULE_ORDER` of `report.py`; A10
reports the seven GET-derived ones as pending.

| ID | Source | Evidence | BootUI lines (`Checks.java`) |
|---|---|---|---|
| PT-A02-001 Cookie is missing HttpOnly | HTTP | GET `Set-Cookie` | 389-440 |
| PT-A05-005 Cookie is missing SameSite | HTTP | GET `Set-Cookie` | 442-473 |
| PT-A02-002 Cookie is missing Secure | HTTP | GET `Set-Cookie` | 475-503 |
| PT-A02-003 Cookie uses SameSite=None without Secure | HTTP | GET `Set-Cookie` | 992-1023 |
| PT-A02-007 Cookie with `__Host-` or `__Secure-` prefix violates browser prefix requirements | HTTP | GET `Set-Cookie` | 2568-2632 |
| PT-A02-008 Response setting a cookie permits shared or public HTTP caching | HTTP | GET `Set-Cookie` and `Cache-Control` | 2634-2808 |
| PT-A05-064 Session cookie is missing a `__Host-`/`__Secure-` name prefix | HTTP | GET `Set-Cookie` | 1025-1064 |
| PT-A02-004 Session cookie Secure flag is explicitly disabled | metadata | session middleware configuration | 1671-1698 |
| PT-A02-006 Session cookie SameSite=None is paired with Secure=false | metadata | session middleware configuration | 1700-1728 |

PT-A02-007 and PT-A02-008 are active, not retired or pending: `Registry.java:61-62` registers
`CookiePrefixRequirementsCheck` and `CacheableSetCookieCheck`, both declare `PentestingSource.HTTP_SYNTHETIC`
(`Checks.java:2568-2582`, `2634-2645`) and read only the GET's `Set-Cookie` and `Cache-Control`. Only PT-A02-004 and
PT-A02-006 are `SPRING_METADATA`. PT-A02-005 is retired (`RETIRED_CHECK_IDS`) and stays retired.

Helpers read for the port: `Support` `cookieName` (90-98), `stripCookiePrefix` (138-150), `isSessionOrAuthCookieName`
(152-160), `isDeletionCookie` (162-184), `hasCookieAttribute` (257-271), `cookieAttributeValue` (273-290),
`boundedLabel` (327-334); `Assessment` `retainedHeaders` (59-65), `cookies` (85-91), `configuration` (41-44);
`Registry` `scopeLimitations` (319-330); `PentestingLocalHttpResponse` header limits and per-name incompleteness
(20-135).

Reused from lane A11 (not copied): `SyntheticResponse.incomplete_header_names`, `header_inventory_incomplete`,
`headers_complete(*names)`; `headers.bound_headers`, `headers.joined`, `java_trim`, `java_is_blank`;
`assessment.retained_headers` and `required_headers`; the evidence sanitiser, `make_echo(masker)` and the required
`masker` of `PentestingService.scan`. This lane's first task moves the sanitiser and `make_echo` from A11's `cors.py`
into the shared module `pentesting/echo.py` (behaviour unchanged); lane A13 merges after this one and reuses that module
without a move of its own. Every finding of this lane passes through the sanitiser (BootUI `evidence()`,
`PentestingCheckSupport.java:51-63`). This lane creates `fastapi/pentesting_exposure.py::read_security_facts`, the single
per-scan read, and lane A13 extends it.

Out of scope: any request beyond A10's GET and OPTIONS; cookie value decoding or a general cookie parser; the OPTIONS
and CORS checks (A11); the Flask adapter, which has no pentesting scan and whose `app.config` always carries the session
cookie defaults (`flask/app.py:194,196`), so an explicit false cannot be detected.

## Coverage map (active dimensions, and why the others are skipped)

| Dimension | Coverage |
|---|---|
| D1 Safe mode fails closed | Active: the checks run only inside the scan action; an inactive console answers 404 and never reaches the probe (re-asserted with a cookie-setting host). |
| D2 Activation and access guard | Active: scan refusal on a read-only or disabled panel, cross-site, and MCP-off paths refuse before any host call. |
| D3 Secret masking | Active and decisive: `Set-Cookie` values are credentials. Values never reach an observation, report, error, log, MCP or CLI output or persisted file produced by the scan, in every exposure. Capture records of the probe exchange hold no cookie value in `MASKED` and `METADATA_ONLY`; the capture middleware shows header values for every captured exchange by design under `FULL`, so the probe's cookie is shown there, and `Cache-Control` values are recorded as sent in `MASKED` and `FULL` (stated exception, row 39; deviation row `pentesting:cookie-capture-full`, owner to confirm). |
| D4 BootUI contract parity | Active: IDs, titles, severities, confidence, categories, recommendation text, registry order, gap strings and scope suffixes of the nine checks. |
| D5 Framework drift | Active: duplicate `Set-Cookie` header tuples; `SessionMiddleware` keyword, positional and mounted options across Starlette versions; the `null` clear cookie. |
| D6 No side effects on GET or MCP | Active: report reads never call the host and never read security facts. |
| D7 OSV/EPSS network failures | Skipped: no vulnerability feed and no network. |
| D8 Host-app integration | Active: host middleware that sets cookies, `TrustedHostMiddleware` rejection, a mounted sub-app with its own `SessionMiddleware`. |
| D9 Scale and limits | Active: the 4096-character, 128-value, 64-name and 16 KiB budgets apply to raw `Set-Cookie` text before parsing; the 20-limitation cut. |
| D10 MCP and CLI parity | Active: the compact MCP/CLI scan summary and the full report read carry the same value-free evidence. |

## Worst-case trace (input, file:line steps, what it found or why a finding was withdrawn)

**Input:** a host response carrying `Set-Cookie: session=<canary>; Path=/; HttpOnly`, `Set-Cookie: <canary2>; Secure`
(no `=`), `Set-Cookie: =<canary3>; Secure` (empty name), a 152-character JWT-shaped name, `SameSite=<canary4>`,
`Path=/<canary5>`, `Cache-Control: public, x-token=<canary6>`, and an over-long `Set-Cookie` value. Line numbers for the
A10 code are as of its head; after the A11 rebase the retention loop lives in `headers.bound_headers`.

1. `pentesting_probe.py:81-83` decodes every raw header tuple to text; `_Capture._retain` (`:104-122`) keeps each retained
   value in `capture.headers["set-cookie"]` and `:160` freezes it into `SyntheticResponse.headers`. The raw values live
   on the evidence object for the whole scan and in its `repr`.
2. `report.py` and `checks.py` read only named headers and build evidence from static strings (`checks.py:3-4`), so no
   value is echoed today. The risk is in the port, not in A10.
3. `Support.cookieName` (`:90-98`) on `<canary2>; Secure` and `=<canary3>; Secure` returns the whole first segment
   (`end > 0` is false); `Checks.java:416, 498, 1018, 1051` build the target `"Set-Cookie " + name` from it.
4. `boundedLabel` (`:327-333`) shortens the JWT-shaped name to 77 characters plus `...`; `masking.is_secret_value`
   fullmatches the stripped text (`masking.py:92`), so the cut no longer matches and its prefix would be shown. The
   secret test must run on the full name first.
5. `Checks.java:2668, 2678, 2693` echo the joined `Cache-Control` text (with `x-token=<canary6>`) into PT-A02-008
   evidence.
6. `SameSite=` and `Path=` values are read only as a classification (`Checks.java:458-467`, `2603-2608`), so no value has
   to be kept.
7. `PentestingLocalHttpResponse.java:111-124` drops an over-long value and records its header name as incomplete; A11's
   `bound_headers` ports that, so a dropped cookie never reads as "no cookie".

**Finding:** four leak paths (a first segment without `=`, an empty name, a long secret-shaped name, the raw
`Cache-Control` text) and one retention path (raw headers on the response object). All are closed at the probe boundary
and in the label, evidence and echo rules, not by masking a whole string, which would destroy BootUI's evidence.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D3 | A cookie value is a unique canary (`name=<canary>`) | Critical | The canary appears in no observation, `SyntheticResponse` field or `repr`, report, MCP or CLI output, error body, log record or state file, in `MASKED`, `METADATA_ONLY` and `FULL`, and in no capture record in `MASKED` and `METADATA_ONLY` (the `FULL` capture exception is row 39) | Unit, Integration |
| 2 | D3 | A first segment without `=` (`<canary>; Secure`) | Critical | Label `(unnamed)`; flags still evaluated; token discarded | Unit |
| 3 | D3 | Empty name (`=<canary>; Secure`) | Critical | Label `(unnamed)`; value discarded | Unit |
| 4 | D3 | Extension attribute and `Domain` value carry the canary | Critical | Only the closed presence set is retained; no attribute value is echoed | Unit |
| 5 | D3 | Name with control characters, whitespace or over 80 characters | High | BootUI's `boundedLabel`: runs of ASCII control and whitespace (U+0000-U+0020, U+007F) to `_`, 77 characters plus `...`; Unicode whitespace such as U+00A0 and U+0085 is kept, as Java's `[\p{Cntrl}\s]` keeps it | Unit |
| 6 | D3 | Name matches a secret value pattern (JWT or vendor-token shape) | Critical | `(redacted)`; the finding still fires | Unit |
| 7 | D3 | Malformed, empty, huge or non-UTF-8 header text reaches the parser | Critical | Total: returns `(unnamed)` with no attributes, never raises, no input in any message | Unit |
| 8 | D3 | `repr`, `str`, assertion diff and logging of `SyntheticResponse` | Critical | No raw header text; `headers` carries no `set-cookie` key | Unit |
| 9 | D3, D10 | Planted value on each output surface (POST scan, cached GET, MCP scan and report, CLI scan and report) in three exposures | Critical | Absent on every surface; the expected finding is present | Integration |
| 10 | D6 | GET report, MCP report and CLI report on a host that sets cookies | Critical | No host call, no socket, no file, no `security_facts` read | Integration |
| 11 | D2 | Scan on a read-only or disabled panel, MCP off, cross-site, or while the single-flight is held (409) | Critical | Refused before any host call; `security_facts()` is read only after `run_probe` returns, so a busy scan reads nothing; no cookie evidence collected | Integration |
| 12 | D4 | HttpOnly missing on a session or authentication name | High | PT-A02-001 MEDIUM | Unit |
| 13 | D4 | HttpOnly missing on `XSRF-TOKEN` or `CSRF-TOKEN` (with or without prefix) | High | PT-A02-001 INFO with the "commonly intentional" text | Unit |
| 14 | D4 | HttpOnly missing on a non-session name, or on an `(unnamed)` or `(redacted)` label | High | PT-A02-001 INFO | Unit |
| 15 | D4 | Presence flags, `Secure=false` counts as present, last `SameSite` wins, whole-name attribute matching, Java `equalsIgnoreCase` names | High | Same results as BootUI | Unit |
| 16 | D4 | Deletion cookies (`Max-Age` at or below zero, blank value with 1970 `Expires`) | High | Ignored by every check except PT-A02-007 (`Checks.java:2584-2591`); quoted `Max-Age="-1"`, a 20-digit `Max-Age` and a positive `Max-Age` are not deletions | Unit |
| 17 | D4 | `SameSite=None` without `Secure` | High | PT-A02-003; PT-A05-064 silent for a non-Secure cookie | Unit |
| 18 | D4 | `__Secure-`/`__Host-` violations; compliant cookies; lowercase `__host-` | High | PT-A02-007 as BootUI; `Path=/` read as `path_is_root`; evidence names violations only | Unit |
| 19 | D4 | Secure session-like cookie without a recognised prefix; analytics cookie; already prefixed | High | PT-A05-064 only for a Secure session or authentication name without a prefix | Unit |
| 20 | D4 | `Cache-Control` with `public`, `s-maxage`, positive `max-age`, `private`, `no-store`, quoted `private="Set-Cookie"` and `no-cache="Set-Cookie"`, escaped quotes, numeric overflow | High | PT-A02-008 HIGH, MEDIUM for session names with a positive `max-age`, silent for the safe forms | Unit |
| 21 | D9 | `Set-Cookie` value over 4096 characters, more than 128 values, over 64 names, over 16 KiB | High | Over-limit value discarded; `set-cookie` incomplete; other cookies evaluated; scan PARTIAL with BootUI's gap `GET required response headers were incomplete.`; the dropped cookie is never named | Unit |
| 22 | D9 | `Cache-Control` incomplete while a cookie is present | High | PT-A02-008 not produced; both of BootUI's gaps (`GET required response headers were incomplete.` and `... were unavailable.`, `Assessment.headers`), also when no cookie is set | Unit, Integration |
| 23 | D4 | GET failed, timed out, Host rejected or unavailable | High | No cookie finding and no pass claim; A10's incomplete finding and limitation stand | Unit |
| 24 | D5 | Several `Set-Cookie` header tuples from one response | High | One observation each, in arrival order | Unit, Integration |
| 25 | D5 | `SessionMiddleware(https_only=False)` passed as a keyword | High | PT-A02-004 LOW | Unit |
| 26 | D5 | `SessionMiddleware` with no `https_only` keyword | High | PT-A02-004 silent: not explicit; SEC-SESSION-002 covers the default | Unit |
| 27 | D5 | `SessionMiddleware(same_site="none", https_only=False)` | High | PT-A02-006 MEDIUM; PT-A02-004 also fires | Unit |
| 28 | D5 | `same_site="none"` with `https_only=True`; `same_site="lax"` with `https_only=False` | High | PT-A02-006 silent | Unit |
| 29 | D5 | Positional options, facts unavailable, a non-FastAPI app, or any facts limitation | High | Both metadata checks indeterminate with BootUI's gap `Framework configuration evidence was incomplete.`; no limitation text copied; never a clean result | Unit |
| 30 | D8 | A mounted sub-app with its own `SessionMiddleware(https_only=False)` | Medium | The finding names the mount path through `echo`; the root app is evaluated separately | Unit |
| 31 | D4 | Registry order, DTO keys, nulls, camelCase, IDs, titles, severities, confidence, category, recommendation, learn-more URL | High | Equal to the BootUI-derived rule contract | Golden |
| 32 | D4 | The A10 pending text for cookie checks | High | Replaced; A02 and A04 coverage carry BootUI's scope suffixes (`Registry.java:319-330`); no pending wording remains | Unit |
| 33 | D8 | `TrustedHostMiddleware` rejects the synthetic Host | Medium | A10 incomplete evidence; no cookie finding | Integration |
| 34 | D8 | Host default `SessionMiddleware` emits no cookie on the probe path | Medium | No cookie finding; the A04 coverage text says no observed `Set-Cookie` does not establish that there are no sessions | Unit |
| 35 | D3 | A 152-character JWT-shaped name, in all exposures | Critical | `(redacted)` from the parser, so `FULL` (which shows text) still hides it; no 77-character prefix appears | Unit, Integration |
| 36 | D3 | `SameSite=<canary>` and `Path=/<canary>` | Critical | PT-A05-005 fires for the unrecognised value; the canary is in no field, `repr` or output; `path_is_root` is false | Unit |
| 37 | D3 | `Cache-Control: public, x-token=<canary>`, `public, private="<canary>"`, `private="<canary>"` alone and `max-age=<canary>`, each complete or over-long, set by a host with a session cookie, in `MASKED`, `METADATA_ONLY` and `FULL` on every pentesting output surface (capture records are row 39) | Critical | Complete `public, x-token=<canary>` and `public, private="<canary>"`: PT-A02-008 fires, evidence lists the recognised directives and counts the others; `private="<canary>"` alone (BootUI's private branch needs `public`, `s-maxage` or a positive `max-age` beside it) and `max-age=<canary>` (not positive): silent; over-long: no finding, both gap strings, scan PARTIAL; the canary is absent in every case | Unit, Integration |
| 38 | D3 | A nameless padded base64 value (`dGVzdA==; Secure`) | Medium | Label is the unpadded part, as RFC 6265bis reads a name; pinned by a test and listed as awaiting confirmation | Unit |
| 39 | D3 | Capture middleware records the probe exchange and trace | High | At `MASKED` and `METADATA_ONLY` the records hold no cookie-value canary (positive control first; the assertion searches for the cookie canary only). Stated exception: header masking shows values under `FULL` by design for every captured exchange, so the probe's cookie is shown there; `Cache-Control` is not a sensitive header name, so its value is recorded as the host sent it in `MASKED` and `FULL` (real `Masker`: unchanged in both, empty in `METADATA_ONLY`); pentesting evidence never echoes it. Decision, rationale and consequence are in the plan's Global Constraints, and two tests pin the behaviour | Integration |
| 40 | D3 | Name echoed in each exposure | High | `MASKED` shows the label, `METADATA_ONLY` shows `[masked]`, `FULL` shows the label; severity follows the unmasked label | Unit |
| 41 | D9 | Worst-case limitation set (A10, A11 and A12 strings), measured from the real pre-cut list | High | The pre-cut list has the claimed 15 entries (A10 5, A11 5, A12 1, A13 1, 3 trailing); after the 20-entry, 240-character cut the three trailing statements, the configuration gap and A11's header gaps are each present | Unit |
| 42 | D6 | `security_facts` calls per scan and per read | High | Exactly one per scan; zero on GET, MCP read and CLI read | Integration |
| 43 | D5 | Starlette clear cookie (`session=null; expires=1970`) | Medium | Not a deletion cookie; evaluated like any cookie (parity note) | Unit |
| 44 | D3 | A facts limitation or mount path carries a canary | Critical | Gap is the fixed BootUI string; the mount path is echoed only through `echo` | Unit |
| 45 | D3, D4 | PT-A02-007 on `__Host-session` with all three violations (no `Secure`, `Domain`, `Path` other than `/`) | High | BootUI's sentence is 233 characters plus the name, so the evidence is cut to 237 characters plus `...` (240) by the shared sanitiser, with no CR, LF or TAB; every other finding passes the same sanitiser | Unit |
| 46 | D6, D3 | `security_facts()` raises with a canary in its message, the attribute is absent or not callable, or it returns a value that is not `SecurityFacts` | Critical | `read_security_facts` returns `None`, logs nothing, copies no message; the scan reports BootUI's configuration gap; a valid object comes back unchanged | Unit |
| 47 | D3 | A name containing U+00A0, U+0085, U+2003 or U+3000, or U+007F | Medium | Java's ASCII class: the Unicode whitespace stays in the label, U+007F becomes `_` | Unit |
| 48 | D3, D4 | PT-A02-004 and PT-A02-006 on a mounted sub-app whose mount path is over 240 characters and contains LF | High | The two configuration findings pass through the same shared sanitiser as the seven observed rules: evidence is exactly 240 characters (237 and `...`) with no CR, LF or TAB; the mount path is echoed first | Unit |

## Must-cover before merge (Critical + High): one pytest name per row

Shared module (`tests/engine/collectors/pentesting/test_evidence_echo.py`):

- `test_sanitizer_collapses_cr_lf_and_tab_runs_to_one_space`, `test_sanitizer_trims_java_whitespace`,
  `test_sanitizer_cuts_at_240_characters_with_an_ellipsis`, and one echo case per exposure (row 45)

Observation boundary (`tests/engine/collectors/pentesting/test_cookie_observation.py`):

- `test_cookie_value_never_enters_an_observation` (rows 1, 8)
- `test_segment_without_equals_is_unnamed` (row 2)
- `test_empty_name_is_unnamed` (row 3)
- `test_attribute_values_are_never_retained` (rows 4, 36)
- `test_label_follows_bootui_bound_and_replaces_whitespace` (row 5)
- `test_label_keeps_unicode_whitespace_that_java_does_not_match` (row 47)
- `test_secret_shaped_name_is_redacted_before_shortening` (rows 6, 35)
- `test_padded_base64_without_a_name_keeps_the_unpadded_label` (row 38)
- `test_parser_is_total_on_malformed_input` (row 7)
- `test_attribute_parsing_uses_presence_whole_names_and_last_samesite` (row 15)
- `test_deletion_cookies_are_marked_and_non_deletions_are_not` (row 16)
- `test_starlette_session_clear_is_not_a_deletion_cookie` (row 43)

Probe boundary and surfaces (`tests/fastapi/test_pentesting_cookie_probe.py`, `test_pentesting_cookie_surfaces.py`):

- `test_set_cookie_values_never_reach_the_synthetic_response` (rows 1, 8)
- `test_synthetic_response_repr_holds_no_header_text` (row 8)
- `test_duplicate_set_cookie_headers_become_ordered_observations` (row 24)
- `test_overlong_cookie_value_marks_set_cookie_incomplete_only` (row 21)
- `test_header_budgets_apply_to_raw_cookie_text_before_parsing` (row 21)
- `test_planted_cookie_value_is_absent_from_every_output_surface`, parametrised by surface (POST scan, cached GET, MCP
  `pentest_scan`, MCP `get_pentest_report`, CLI `pentest scan`, CLI `pentest report`) and exposure (rows 9, 35, 36, 37, 40)
- `test_cache_control_canary_is_absent_from_every_output_surface`, same parametrisation (rows 22, 37)

Observed-cookie checks (`tests/engine/collectors/pentesting/test_cookie_checks.py`, `test_cache_control.py`):

- `test_missing_httponly_is_medium_for_session_names_and_info_for_csrf_and_other` (rows 12-14)
- `test_samesite_missing_or_unrecognised_is_flagged` (rows 15, 36)
- `test_missing_secure_is_flagged`, `test_samesite_none_without_secure_is_flagged` (row 17)
- `test_deletion_cookies_feed_no_flag_check` (row 16)
- `test_flag_findings_name_the_echoed_label_and_classify_the_unmasked_one` (row 40)
- `test_prefix_requirements_are_checked_for_host_and_secure_cookies` (rows 16, 18)
- `test_session_cookie_prefix_check_needs_secure_session_name_without_prefix` (row 19)
- `test_cacheable_set_cookie_distinguishes_public_shared_and_session_max_age` (row 20)
- `test_cache_control_evidence_is_rebuilt_from_directives` (row 37)
- `test_cache_control_incomplete_does_not_manufacture_a_finding` (row 22)
- `test_cookie_finding_evidence_is_sanitised_and_cut_at_240_characters`,
  `test_cookie_finding_evidence_goes_through_the_shared_sanitiser` (rows 45, 48; all nine rules, PT-A02-004 and
  PT-A02-006 included)
- `test_failed_or_rejected_get_leaves_cookie_checks_indeterminate` (row 23)
- `test_incomplete_set_cookie_inventory_keeps_cookie_result_partial` (row 21)

Session configuration (`tests/engine/collectors/pentesting/test_session_cookie_config.py`, plus
`tests/fastapi/test_introspector_security.py`):

- `test_explicit_https_only_false_is_flagged_and_default_is_not` (rows 25, 26)
- `test_same_site_none_with_secure_disabled_is_flagged` (rows 27, 28)
- `test_unreadable_session_options_leave_metadata_checks_indeterminate` (rows 29, 44)
- `test_mounted_sub_app_finding_names_the_echoed_mount_path` (row 30)
- `test_https_only_false_flag_is_read_from_keyword_only`
- `tests/fastapi/test_pentesting_exposure_adapter.py`: `test_read_security_facts_returns_the_object_the_introspector_gives`,
  `test_read_security_facts_returns_none_and_logs_nothing_when_the_reader_raises`,
  `test_read_security_facts_returns_none_when_the_attribute_is_absent`,
  `test_read_security_facts_returns_none_for_a_result_of_the_wrong_type` (row 46)

Report, hidden surfaces and gates:

- `test_cookie_rules_follow_registry_order_and_bootui_contract` (row 31)
- `test_cookie_pending_text_is_replaced_and_no_pending_wording_remains` (rows 32, 34)
- `test_planted_cookie_value_is_absent_from_every_hidden_surface` (rows 1, 9: error bodies, logs, state files)
- `test_probe_exchange_and_trace_records_are_free_of_the_canary` (row 39, `MASKED` and `METADATA_ONLY`),
  `test_full_exposure_capture_records_the_probe_exchange_like_any_other` (row 39, the `FULL` exception),
  `test_capture_records_hold_cache_control_as_sent_outside_metadata_only` (row 39, the `Cache-Control` exception)
- `test_cookie_checks_are_scan_action_only_and_read_only_denied` (rows 10, 11, 42), `test_one_scan_reads_security_facts_once`
- `test_limitations_added_by_this_lane_survive_the_cut` (row 41)

Every absence assertion is paired with the presence assertion of the finding or label it would appear in, and every
test is red against a wrong-value stub or a recorded mutation before its commit.

## Deferred (Medium + Low): file as issues

- A live run against a sample application with a real session cookie (rows 30 and 34 beyond the unit assertion).
- Python session cookie names common outside BootUI's list (`sessionid`, `connect.sid`, `access_token`) are not
  classified as session names; BootUI's list is ported unchanged. Extending it is a separate decision.
- Cookie names the host controls but that are not secrets stay visible by design.
- Flask session cookie configuration is not covered (see Scope).

## Known-issues cross-reference

- Masking: no change to `engine/masking.py` rules; the lane calls `is_secret_value` to decide a label and A11's `echo`
  for output.
- Introspection drift (`SessionMiddleware` option reading): the new flag is read from keyword options with the same
  defensive reader as `https_only` (`introspection_security.py:58-68`); positional options stay unread and are a gap.
- Lanes A11 and A13 edit neighbouring wording in `report.py`, `service.py`, the scan route and the A10 matrix; the A12
  edits touch only the cookie words and the `session` keyword, so the merge is mechanical.
