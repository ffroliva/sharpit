# Scenario: A12 cookie and session-cookie pentesting checks

Port of the BootUI v2.5.0 cookie-flag and session-cookie checks onto the bounded synthetic probe of lane A10. The
probe responses of A10 are reused: the checks add no request. BootUI sources are at tag `v2.5.0`, package
`bootui-engine/src/main/java/io/github/jdubois/bootui/engine/pentesting/`.

## Scope

Nine active BootUI checks, in registry order (`PentestingCheckRegistry.java`, `ACTIVE_CHECKS` entries
`CookieMissingHttpOnlyCheck` through `SessionCookieSameSiteNoneWithSecureDisabledCheck`). All nine IDs are already in
`RULE_ORDER` of `report.py`; A10 reports the seven GET-derived ones as pending.

| ID | Source | Evidence | BootUI lines (`PentestingChecks.java`) |
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

Helpers read for the port: `PentestingCheckSupport.java` `cookieName` (90-98), `stripCookiePrefix` (138-150),
`isSessionOrAuthCookieName` (152-160), `isDeletionCookie` (162-184), `hasCookieAttribute` (257-271),
`cookieAttributeValue` (273-290), `boundedLabel` (327-334); `PentestingAssessment.cookies` (85-91);
`PentestingLocalHttpResponse` header limits and per-name incompleteness (20-135).

The registry at `v2.5.0` registers `CookiePrefixRequirementsCheck` and `CacheableSetCookieCheck` (PT-A02-007 and
PT-A02-008) as active checks, and PT-A02-005 is retired (`RETIRED_CHECK_IDS`). All seven GET-derived checks and the two
metadata checks are therefore in scope; the retired ID stays retired.

Out of scope: any request beyond A10's GET and OPTIONS; cookie value decoding or a general cookie parser; the OPTIONS
and CORS checks (lane A11); the Flask adapter, which exposes only a pytest route model and has no installed console to
scan.

## Coverage map (active dimensions, and why the others are skipped)

| Dimension | Coverage |
|---|---|
| D1 Safe mode fails closed | Active: the checks run only inside the scan action; an inactive console answers 404 and never reaches the probe (A10 gate, re-asserted with a cookie-setting host). |
| D2 Activation and access guard | Active: scan refusal on a read-only or disabled panel, cross-site, and MCP-off paths still refuse before any host call. |
| D3 Secret masking | Active and decisive: `Set-Cookie` values are credentials. Values never reach an observation, a report, an error, a log or a persisted file. |
| D4 BootUI contract parity | Active: IDs, titles, severities, confidence, categories, recommendation text and registry order of the nine checks; evidence wording of BootUI's observed-cookie checks. |
| D5 Framework drift | Active: duplicate `Set-Cookie` header tuples in `http.response.start`, `SessionMiddleware` keyword and positional options across Starlette 0.40 and newer. |
| D6 No side effects on GET or MCP | Active: GET report and read tools never call the host and never read middleware facts to build a result. |
| D7 OSV/EPSS network failures | Skipped: the lane uses no vulnerability feed and no network. |
| D8 Host-app integration | Active: host middleware that sets cookies, `TrustedHostMiddleware` rejection (A10 incomplete evidence), a mounted sub-app with its own `SessionMiddleware`. |
| D9 Scale and limits | Active: per-value 4096-character, 128-value, 64-name and 16 KiB header budgets apply to `Set-Cookie` values before parsing. |
| D10 MCP and CLI parity | Active: the compact MCP/CLI scan summary and the full report read carry the same value-free evidence. |

## Worst-case trace (input, file:line steps, what it found or why a finding was withdrawn)

**Input:** a host response carrying `Set-Cookie: session=<canary>; Path=/; HttpOnly`, `Set-Cookie: <canary2>; Secure`
(no `=`), `Set-Cookie: =<canary3>; Secure` (empty name), and an over-long `Set-Cookie` value.

1. `src/sharpit/fastapi/pentesting_probe.py:81-83` decodes every raw header tuple to text, so `set-cookie` values are
   in memory as plain strings.
2. `pentesting_probe.py:104-122` (`_Capture._retain`) keeps each retained value in `capture.headers["set-cookie"]`;
   `:160` freezes that map into `SyntheticResponse.headers` (`evidence.py:8-15`). The raw values therefore live on the
   evidence object for the whole scan, and a dataclass `repr` of that object (an assertion failure, a debug log)
   prints them.
3. `src/sharpit/engine/collectors/pentesting/report.py:207-275` and `checks.py` read only named headers and build
   evidence from static strings (`checks.py:4`), so no value is echoed today. The risk is in the port, not in A10.
4. BootUI `PentestingCheckSupport.java:90-98` `cookieName("<canary2>; Secure")`: `split(";", 2)[0]` is the whole
   token, `indexOf('=')` is `-1`, `end > 0` is false, so the name is the whole first segment. For
   `"=<canary3>; Secure"` `indexOf('=')` is `0`, again the whole segment. `PentestingChecks.java:416,498,1018,1051`
   build the finding target `"Set-Cookie " + name` and the evidence from that name.
5. A literal port would therefore place the canaries in `target` and `evidence` of the report DTO, and from there in
   the POST body, the cached GET body, the MCP full report, the CLI output and the dismissal view.
6. `PentestingLocalHttpResponse.java:111-124` drops a value over 4096 characters and records its header name as
   incomplete; `pentesting_probe.py:111-113` drops it too but sets only the global `headers_truncated`. A12 needs the
   per-name state so a dropped cookie never reads as "no cookie" for the checks that depend on it.

**Finding:** two real leak paths (a first segment without `=` and an empty name) and one precision gap (per-name
header incompleteness). The claim "the cached report retains raw values" is withdrawn: `service.py:14-33` caches only
the report dictionary. The object-level retention of step 2 is closed at the capture boundary instead.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D3 | A cookie value is a unique canary (`name=<canary>`) | Critical | The canary appears in no observation, `SyntheticResponse` field or `repr`, report, MCP or CLI output, error body, log record or state file | Unit, Integration |
| 2 | D3 | A first segment without `=` (`<canary>; Secure`) | Critical | Treated as a cookie with no usable name: label `(unnamed)`, flags still evaluated, token discarded | Unit |
| 3 | D3 | Empty name (`=<canary>; Secure`) | Critical | Label `(unnamed)`; value discarded | Unit |
| 4 | D3 | Extension attribute and `Domain`/`Path` values carry the canary (`; Foo=<canary>`) | Critical | Only the closed attribute set is retained; no attribute value is echoed | Unit |
| 5 | D3 | Cookie name is not an RFC 6265 token, contains control characters, whitespace, or exceeds 80 characters | Critical | Label `(unnamed)` for non-token names; token names longer than 80 characters are shortened as BootUI's bounded label does | Unit |
| 6 | D3 | Cookie name matches a secret value pattern (JWT or vendor token shape) | Critical | Label `(redacted)`; the finding still fires | Unit |
| 7 | D3 | Malformed, empty, huge or non-UTF-8 header text reaches the parser | Critical | The parser is total: it never raises, its failure text never contains input, the probe does not fail | Unit |
| 8 | D3 | `repr`, `str`, assertion diff and logging of `SyntheticResponse` | Critical | No raw header text; `headers` carries no `set-cookie` key | Unit |
| 9 | D3, D10 | Planted value on each output surface: POST scan, cached GET report, MCP `pentest_scan` summary and `get_pentest_report`, CLI `pentest scan` and `pentest report`, error bodies, logs, `SHARPIT_STATE_DIR` | Critical | Absent on every surface | Integration |
| 10 | D6 | GET report, MCP report and CLI report on a host that sets cookies | Critical | No host call, no socket, no file; unchanged from A10 | Integration |
| 11 | D2 | Scan on a read-only or disabled panel, MCP off, cross-site | Critical | Refused before any host call; no cookie evidence collected | Integration |
| 12 | D4 | HttpOnly missing on a session or authentication name | High | PT-A02-001 at the registered severity (MEDIUM) | Unit |
| 13 | D4 | HttpOnly missing on `XSRF-TOKEN` or `CSRF-TOKEN` (with or without prefix) | High | PT-A02-001 INFO with the "commonly intentional" text | Unit |
| 14 | D4 | HttpOnly missing on a non-session name | High | PT-A02-001 INFO | Unit |
| 15 | D4 | Attribute parsing: presence flags, `Secure=false` counts as present, last `SameSite` wins, whole-name attribute matching (`Securely`, `HttpOnlyFlag`, `SameSitePolicy` do not match) | High | Same results as BootUI | Unit |
| 16 | D4 | Deletion cookies (`Max-Age` zero or negative, blank value with 1970 `Expires`) | High | Ignored by every observed-cookie check except PT-A02-007, which reads the unfiltered header list (`PentestingChecks.java:2589`); quoted `Max-Age="-1"` and positive `Max-Age` override are not deletions | Unit |
| 17 | D4 | `SameSite=None` without `Secure` | High | PT-A02-003; PT-A05-064 stays silent for a non-Secure cookie | Unit |
| 18 | D4 | `__Secure-`/`__Host-` prefix violations; compliant prefixed cookies; lowercase `__host-` is not a prefix | High | PT-A02-007 exactly as BootUI, evidence names the violations only | Unit |
| 19 | D4 | Secure session-like cookie without a recognised prefix; analytics cookie; already prefixed cookie | High | PT-A05-064 only for a Secure session or authentication name without `__Host-` or `__Secure-` | Unit |
| 20 | D4 | Cache-Control with `public`, `s-maxage`, positive `max-age`, `private`, `no-store`, quoted `private="Set-Cookie"` and `no-cache="Set-Cookie"`, escaped quotes, a numeric overflow | High | PT-A02-008 HIGH, MEDIUM for session names with a positive `max-age`, silent for the safe forms | Unit |
| 21 | D9 | `Set-Cookie` value over 4096 characters, more than 128 values, over 64 names, over 16 KiB | High | Over-limit value discarded; `set-cookie` marked incomplete; other retained cookies still evaluated; the scan is PARTIAL with a limitation; the dropped cookie is never named | Unit |
| 22 | D9 | `Cache-Control` incomplete while a cookie is present | High | PT-A02-008 not produced; limitation recorded | Unit |
| 23 | D4 | GET failed, timed out, Host rejected or probe result unavailable | High | No cookie finding and no pass claim; A10's incomplete finding and limitation stand | Unit |
| 24 | D5 | Several `Set-Cookie` header tuples from one response | High | Each is an observation in arrival order; the report order inside one rule follows arrival order | Unit, Integration |
| 25 | D5 | `SessionMiddleware(https_only=False)` passed as a keyword | High | PT-A02-004 LOW | Unit |
| 26 | D5 | `SessionMiddleware` with no `https_only` keyword (Starlette default is also false) | High | PT-A02-004 silent: the option is not explicit; the Security panel's SEC-SESSION-002 covers the default | Unit |
| 27 | D5 | `SessionMiddleware(same_site="none", https_only=False)` | High | PT-A02-006 MEDIUM; PT-A02-004 also fires | Unit |
| 28 | D5 | `same_site="none"` with `https_only=True`; `same_site="lax"` with `https_only=False` | High | PT-A02-006 silent | Unit |
| 29 | D5 | Options passed positionally, facts unavailable, or a non-FastAPI app | High | The two metadata checks are indeterminate with a limitation; never a clean result | Unit |
| 30 | D8 | A mounted sub-app with its own `SessionMiddleware(https_only=False)` | Medium | The finding names the mount path; the root app's configuration is evaluated separately | Unit |
| 31 | D4 | Registry order, DTO keys, nulls, camelCase, IDs, titles, severities, confidence, category, recommendation, learn-more URL | High | Equal to the BootUI-derived rule contract | Golden |
| 32 | D4 | A10 "pending" text for cookie checks | High | Replaced by the real result; coverage text for A02 and A04 states the cookie scope BootUI states; the CORS wording is untouched | Unit |
| 33 | D8 | `TrustedHostMiddleware` rejects the synthetic Host | Medium | A10 incomplete evidence; no cookie finding | Integration |
| 34 | D8 | Host default `SessionMiddleware` emits no cookie on the probe path | Medium | No cookie finding; the A04 coverage text states that no observed `Set-Cookie` does not establish that the application has no sessions | Unit |

## Must-cover before merge (Critical + High): one pytest name per row

Observation boundary (`tests/engine/collectors/pentesting/test_cookie_observation.py`):

- `test_cookie_value_never_enters_an_observation` (rows 1, 8)
- `test_segment_without_equals_is_unnamed_and_discarded` (row 2)
- `test_empty_name_is_unnamed_and_discarded` (row 3)
- `test_extension_and_domain_attribute_values_are_not_retained` (row 4)
- `test_non_token_and_oversized_names_are_labelled_safely` (row 5)
- `test_secret_shaped_name_is_redacted` (row 6)
- `test_parser_is_total_on_malformed_input` (row 7)
- `test_attribute_parsing_uses_presence_whole_names_and_last_samesite` (row 15)
- `test_deletion_cookies_are_marked_and_non_deletions_are_not` (row 16)

Probe boundary (`tests/fastapi/test_pentesting_cookie_probe.py`):

- `test_set_cookie_values_never_reach_the_synthetic_response` (rows 1, 8)
- `test_synthetic_response_repr_holds_no_header_text` (row 8)
- `test_duplicate_set_cookie_headers_become_ordered_observations` (row 24)
- `test_overlong_cookie_value_marks_set_cookie_incomplete_only` (row 21)
- `test_header_budgets_count_raw_cookie_text_before_parsing` (row 21)

Observed-cookie checks (`tests/engine/collectors/pentesting/test_cookie_checks.py`):

- `test_missing_httponly_is_medium_for_session_names_and_info_for_csrf_and_other` (rows 12-14)
- `test_samesite_missing_or_unrecognised_is_flagged` (row 15)
- `test_samesite_none_without_secure_is_flagged` (row 17)
- `test_prefix_requirements_are_checked_for_host_and_secure_cookies` (row 18)
- `test_session_cookie_prefix_check_needs_secure_session_name_without_prefix` (row 19)
- `test_cacheable_set_cookie_distinguishes_public_shared_and_session_max_age` (row 20)
- `test_cache_control_incomplete_does_not_manufacture_a_finding` (row 22)
- `test_failed_or_rejected_get_leaves_cookie_checks_indeterminate` (row 23)
- `test_incomplete_set_cookie_inventory_keeps_cookie_result_partial` (row 21)

Session configuration (`tests/engine/collectors/pentesting/test_session_cookie_config.py`, plus the existing
introspection test for the new flag):

- `test_explicit_https_only_false_is_flagged_and_default_is_not` (rows 25, 26)
- `test_same_site_none_with_secure_disabled_is_flagged` (rows 27, 28)
- `test_unreadable_session_options_leave_metadata_checks_indeterminate` (row 29)
- `test_https_only_false_flag_is_read_from_keyword_only` (`tests/fastapi/test_introspector_security.py`)

Report, surfaces and gates:

- `test_cookie_rules_follow_registry_order_and_bootui_contract` (row 31)
- `test_cookie_pending_text_is_replaced_and_cors_pending_text_remains` (row 32)
- `test_planted_cookie_value_is_absent_from_every_output_surface` (rows 9, 10, 11), one parametrised case per
  surface: POST scan, cached GET report, MCP `pentest_scan`, MCP `get_pentest_report`, CLI `pentest scan`, CLI
  `pentest report`, error body, log records, `SHARPIT_STATE_DIR`
- `test_cookie_checks_are_scan_action_only_and_read_only_denied` (rows 10, 11)

## Deferred (Medium + Low): file as issues

- Rows 30 and 34 beyond the unit assertion: a live run against a sample application with a real session cookie.
- Python session cookie names common outside BootUI's list (`sessionid`, `connect.sid`, `access_token`) are not
  classified as session names; BootUI's list is ported unchanged. Extending it is a separate decision.
- Cookie name label for names the host controls but that are not secrets stays visible by design.

## Known-issues cross-reference

- Masking: no change to `engine/masking.py` rules; the lane reuses `is_secret_value` only to decide a label.
- Introspection drift (known-issue family for `SessionMiddleware` option reading): the new flag is read from keyword
  options with the same defensive reader as `https_only` (`introspection_security.py:58-68`); positional options keep
  the existing limitation text.
- Lane A11 edits the neighbouring CORS "pending" wording in `report.py` and the A10 matrix: the A12 edits touch only
  the cookie words, to keep the merge mechanical.
