# A11 CORS Preflight Checks Implementation Plan

> Run `/sharpit:status --feature a11-cors-preflight-checks` for the next unchecked step. Complete one task at a time and run `/sharpit:check` before each commit.

**Goal:** Replace the "pending" CORS entry of the pentesting scan with BootUI v2.5.0's CORS findings, evaluated on the OPTIONS and GET evidence that the scan already retains.

**Architecture:** The pentesting engine package gains a pure header-bounding function (BootUI's `boundedHeaders`), per-header-name completeness on `SyntheticResponse`, a small assessment module for "required header" gaps, and one module for the CORS rules and the PT-A05-069 diagnostic. The report builder calls them. The FastAPI probe only groups raw headers and calls the bounding function. No request, route, tool or action is added: the scan keeps sending exactly one GET and one OPTIONS (fixed synthetic origin and request method, fixed path), and the existing gated scan action is the only way to reach the checks.

**Predict verdict:** Go with conditions (confidence 7/10). The conditions are folded into the tasks below.

## Design decisions

| Decision | Rationale | Consequence |
|---|---|---|
| OPTIONS incompleteness is a failed request or truncated headers; a truncated OPTIONS body is not incomplete evidence. | BootUI raises PT-A05-069, marks the scan partial and makes A02 indeterminate only on `failed()` or `headersTruncated()` (`PentestingChecks.java` 214 to 221, `PentestingScanner.java` 255 to 259, `PentestingCheckRegistry.java` 415 to 423); no CORS rule reads the OPTIONS body. Adapt only where Python forces it. | A10's behaviour changes: an OPTIONS body over the limit no longer raises PT-A05-069 or `PARTIAL`; the body-limit limitation line stays. No A10 test pins the old behaviour; the new test does. The `pentesting:options-body-truncation` deviation is not needed. |
| `SyntheticResponse` keeps `headers_truncated` and gains `incomplete_header_names` and `header_inventory_incomplete`; a bare `headers_truncated=True` (including the probe's trailers path) means the inventory is incomplete. | BootUI's legacy constructor sets the inventory flag from the truncated flag (`PentestingLocalHttpResponse.java` line 38) and derives the truncated flag from names and inventory (line 55). Treating the bare flag as "complete" would let a rule read an unknown header as absent. | `headers_complete(*names)` is false for any listed incomplete name, and for every name when the inventory is incomplete. A10 constructors stay valid. |
| BootUI's `boundedHeaders` is ported as one pure engine function, `bound_headers`, that returns the retained headers, the incomplete names and the inventory flag; the probe calls it. | `_retain` is at McCabe 10 and the ratchet forbids a new function over 10; the retention rules are independently testable without an ASGI app. | `_retain` and its counters leave the probe. The probe tests that import `HEADER_MAX_*` from the probe module keep working through re-exports. |
| A rule that requires a header name is withheld, with a gap, when that name is incomplete; it is never downgraded to a weaker finding. | BootUI's `headers()` returns early on a missing required name (`PentestingChecks.java` 566, 606, 647, 1395, 2842 to 2852). | A table test covers each rule and each required name. |
| PT-A05-069 follows BootUI's two evidence forms, with the fixed incomplete reason in place of the transport error text. | BootUI's text carries the error text; exception text can carry host data (existing deviation `pentesting:body-evidence`). | A failed request says `Request failed before CORS preflight headers could be inspected: <fixed reason>`; truncated headers say `Response headers exceeded bounded retention limits`. Both name PT-A05-007, -008, -023, -024 and -065. |
| A fixed limitation names PT-A05-073 as indeterminate when either of its halves is withheld. | BootUI's 069 list omits PT-A05-073 although its preflight half skips silently on a failed preflight. | Fail closed at no parity cost; the 069 finding text itself stays verbatim. |
| CORS evidence echoes constants only: `*`, `null`, the probe origin, and one fixed spelling per sensitive header name. | BootUI echoes the untrimmed origin in -008 and -023 and the host's spelling of a sensitive token in -073. | The report never contains the host's whitespace or spelling. The comparisons themselves are BootUI's. |
| BootUI's comparison asymmetries are ported: PT-A05-007 and the credentials token compare untrimmed; -008, -023, -065 and -073 trim; the -073 GET half treats only `*` and the probe origin constant as permissive. | `PentestingChecks.java` 570 to 576, 617 to 618, 1406 to 1408, 2860 to 2863; `PentestingResponsePolicies.java` 35 to 38. | Each asymmetry has a test. |
| Repeated header values are joined with `, `, as in `PentestingCheckSupport.header`. | A repeated `Access-Control-Allow-Origin` is then a comma list that matches nothing. | The CORS rules use a joined accessor; A10's TRACE check keeps its first-value accessor. |
| A02 coverage stays `INDETERMINATE` whenever the scan is partial, even when A02 findings exist. | BootUI keeps the finding status and appends a limitation (`PentestingCheckRegistry.java` 269 to 290); porting that would change A10 coverage for existing findings. | Stricter than BootUI; logged as a deviation and pinned by a test. |
| The 069 text, the gap strings and the CORS rules do not grow `_evidence_limitations` or `scanned_report`. | The limitation list is capped at 20 and the standing statements are appended last. | The new logic lives in `cors.py`; gaps are deduplicated; a test proves the standing statements survive. |

## Global Constraints

- Reads have no side effects; no GET route or read MCP/CLI tool opens a socket, writes a file, changes a logger level, or changes `os.environ`.
- Actions follow BootUI: the scan keeps its enablement, guard, enabled-panel, non-read-only and single-flight gates; A11 adds no action.
- Secrets are masked before output; response bodies, exception text and host-controlled header values are not returned. CORS evidence names only `*`, `null`, the fixed probe origin, or a fixed sensitive header spelling.
- Python `>=3.12`; runtime dependencies exactly `starlette` and `packaging`; `engine/` imports no `fastapi` or `starlette`, and the FastAPI adapter imports the shared probe constants and the bounding function from the engine, never the reverse.
- Every ported test cites its BootUI source with `# ported: <Class>.<method>`.
- No module under `src/` exceeds 1000 lines; ratchets only go down (`checks.py` is 524 lines; the CORS rules go in their own module); no function over McCabe 10 is added, and `_retain` leaves the probe.
- A failure, timeout, truncation or unobserved header is indeterminate, never a clean result.
- Evidence describes a synthetic preflight against the in-process ASGI app; it never claims browser or deployed-edge behaviour.
- Every `test:` commit carries wrong-value stubs in `src` (returning the wrong state, never raising) so that each red is an assertion; a stub is replaced in the `feat:` commit that follows.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A host-controlled header value, whitespace or spelling leaks into a finding | Echo constants only; secret-bearing and padded inputs in tests. |
| Critical | A CORS check reads as clean when the preflight failed or a header was not retained | PT-A05-069 with a fixed reason, per-name completeness, the required-name table test, a bare truncated flag meaning an incomplete inventory, scan `PARTIAL`, A02 coverage `INDETERMINATE`. |
| Critical | A rule downgrades to a weaker finding when a name it depends on is incomplete (credentials reads as absent) | The rule is withheld with a gap; the table test asserts no finding for each rule and name. |
| High | Per-name completeness changes A10's behaviour | `headers_truncated` stays and is derived from names and inventory; the A10 probe and report tests stay green. The one intended change (OPTIONS body) is stated and tested. |
| High | Constants drift between the probe and the rules | One `PROBE_ORIGIN` and one `PROBE_REQUEST_METHOD` in the engine, imported by the probe; a test pins the request. |
| High | Comparison semantics drift from BootUI (case, trailing slash, `True` versus `true`, trimmed versus untrimmed) | Exact comparisons ported with BootUI's cases and the asymmetry tests. |
| High | Standing limitations pushed out of the 20-entry cap by new gaps | Gaps are deduplicated and built in a helper; a worst-case test. |
| Medium | Report wording overstates CORS verification | Keep BootUI's "actual resource sharing was not tested" wording and add the A02 limitation; a text test pins both. |

## File map

- `src/sharpit/engine/collectors/pentesting/headers.py` (new): `HEADER_MAX_NAMES`, `HEADER_MAX_VALUES`, `HEADER_MAX_NAME_CHARS`, `HEADER_MAX_VALUE_CHARS`, `HEADER_MAX_CHARS`, `BoundedHeaders`, `bound_headers(source)`, `joined(headers, name)`.
- `src/sharpit/engine/collectors/pentesting/evidence.py`: `PROBE_ORIGIN`, `PROBE_REQUEST_METHOD`, `SyntheticResponse.incomplete_header_names`, `header_inventory_incomplete`, `failed`, `headers_complete(*names)`.
- `src/sharpit/engine/collectors/pentesting/assessment.py` (new): `retained_headers(method, response, required, gaps)` and `required_headers(method, response, required, gaps)`, BootUI's `PentestingAssessment.retainedHeaders` and `headers`, with its gap strings.
- `src/sharpit/engine/collectors/pentesting/cors.py` (new): `evaluate(get, options) -> tuple[list[Finding], list[str]]` and `options_diagnostic(options) -> list[Finding]`.
- `src/sharpit/engine/collectors/pentesting/report.py`: call the CORS module, restrict OPTIONS incompleteness to failed or header-truncated, remove the pending wording, add the A02 limitation text.
- `src/sharpit/fastapi/pentesting_probe.py`: group raw headers and call `bound_headers`; record trailers; import the constants.
- `tests/engine/collectors/pentesting/test_pentesting_headers.py` (new), `test_pentesting_cors.py` (new), `test_pentesting_report.py`, `tests/fastapi/test_pentesting_probe.py`, `tests/fastapi/test_pentesting_api.py`.
- `tests/fixtures/bootui/2.5.0/pentesting/`: extend the hand-derived ASGI golden with CORS findings; the BootUI contract projection already lists the IDs and order.
- `docs/reference/matrix-updates/0.8.0-a11.tsv` (new) and `0.8.0-a10.tsv` (delete the CORS pending row, amend the framework-evidence row), `docs/reference/PARITY.md` if it names the pending state, `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` §14.

BootUI sources ported (tag `v2.5.0`, `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/pentesting/`): `PentestingChecks.java` (`OptionsProbeFailedCheck`, `CredentialedCorsCheck`, `BroadCorsCheck`, `CorsNullOriginAllowedCheck`, `BroadCorsMethodsHeadersCheck`, `CorsExposeHeadersCheck`), `PentestingResponsePolicies.java` (`successfulPreflight`, `credentials`, `allowedOrigin`, `matchesOrigin`, `permissiveOrigin`), `PentestingAssessment.java` (`response`, `retainedHeaders`, `headers`, `gap`), `PentestingLocalHttpResponse.java` (`headersComplete`, `boundedHeaders`), `PentestingCheckSupport.java` (`header`, `headers`), `PentestingCheckRegistry.java` (registry order, A02 coverage text), `PentestingScanner.java` (the fixed probe headers). Tests ported from `PentestingScannerTests.java` and `PentestingLocalHttpResponseTests.java` in the sibling test tree.

### Task 1: Define the completeness and probe-constant contract (red first)

**Commit:** `test: define the CORS preflight evidence contract`

**Files:** `tests/engine/collectors/pentesting/test_pentesting_headers.py` (new), `tests/engine/collectors/pentesting/test_pentesting_report.py` (completeness cases only), `tests/fastapi/test_pentesting_probe.py`; wrong-value stubs in `headers.py` (new), `evidence.py`.

**Interfaces:** Produces the stubs the later tasks fill in. Stubs: `PROBE_ORIGIN = ""`, `PROBE_REQUEST_METHOD = ""`; `SyntheticResponse.incomplete_header_names = frozenset()`, `header_inventory_incomplete = False`, `failed` (real), `headers_complete(*names)` returning `True`; `headers.bound_headers` returning no headers, no incomplete names and a complete inventory; `headers.joined` returning `None`. Each stub carries a one-line comment naming the task that replaces it.

- [ ] **Step 1 (characterization, green today, not in the red check):** Keep `test_options_uses_only_the_fixed_synthetic_origin_and_request_method` (the OPTIONS request carries exactly `Origin: https://evil.example` and `Access-Control-Request-Method: GET`; no parameter of `probe()`, `install()` or the scan route changes them) and `test_scan_still_sends_exactly_one_get_and_one_options_request` (a CORS-bearing host receives two requests in order and nothing else). They pin existing A10 behaviour. # ported: `PentestingScannerTests.scanUsesOnlySyntheticLoopbackRequestsAndDoesNotExposeResponseBody`.
- [ ] **Step 2:** Add `test_probe_request_uses_the_engine_probe_constants`: the request values equal `PROBE_ORIGIN` and `PROBE_REQUEST_METHOD`, and those constants are `https://evil.example` and `GET`. Red: the stub constants are empty strings.
- [ ] **Step 3:** Add the bounding tests in `test_pentesting_headers.py`: `test_bound_headers_reports_incomplete_names_and_inventory_at_each_boundary` (parametrized: an oversized value or a value past the 128-value budget marks that name incomplete; more than 64 names, a blank or over-256-character name, or the 16 KiB budget marks the inventory incomplete; names are lower-cased) and `test_an_incomplete_header_name_is_not_reported_as_absent`. Read the case names in `PentestingLocalHttpResponseTests` at execution time and cite each. Red: the stub reports nothing incomplete.
- [ ] **Step 4:** Add the record tests: `test_synthetic_response_headers_complete_is_false_for_an_incomplete_name_or_inventory` (case-insensitive names; other names stay complete), `test_a_bare_headers_truncated_flag_implies_inventory_incomplete` (a hand-built `SyntheticResponse(..., headers_truncated=True)` has `header_inventory_incomplete` true and `headers_complete("access-control-allow-origin")` false), and `test_trailers_response_marks_the_header_inventory_incomplete` (probe level: a trailers message leaves `header_inventory_incomplete` true). Red: the stub fields stay false and `headers_complete` returns true.
- [ ] **Step 5:** Add the probe tests `test_probe_records_incomplete_header_names_per_name` and `test_probe_marks_header_inventory_incomplete`: an oversized `Access-Control-Allow-Credentials` value is absent from the retained headers and its name is incomplete; 65 names mark the inventory incomplete. Red: the probe does not fill the new fields.
- [ ] **Step 6:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_probe.py tests/engine/collectors/pentesting` and `uv run python scripts/dev/red_check.py <node ids of steps 2 to 5>`; every verdict must be RED (an assertion), none CRASH. Confirm the characterization tests of step 1 are green. Commit tests and stubs with explicit `git add` and `git commit -s`.

### Task 2: Per-name completeness, bounding function and probe constants

**Commit:** `feat: record per-header completeness for pentesting evidence`

**Files:** `headers.py`, `evidence.py`, `fastapi/pentesting_probe.py`.

**Interfaces:** `headers.bound_headers(source: Mapping[str, Sequence[str]]) -> BoundedHeaders` where `BoundedHeaders` holds `headers`, `incomplete_names` and `inventory_incomplete`; `headers.joined(headers, name) -> str | None` (values joined with `, `, names case-insensitive); `SyntheticResponse.incomplete_header_names: frozenset[str]`, `header_inventory_incomplete: bool`, `failed: bool`, `headers_complete(*names) -> bool`. Consumed by `assessment.py` and `cors.py`, and by lane A12.

- [ ] **Step 1:** Confirm the Task 1 failures are the named behaviour assertions.
- [ ] **Step 2:** Port `boundedHeaders` into `headers.py` with BootUI's order of checks and the five limits; add `joined`. The function is pure and stays at or under complexity 10.
- [ ] **Step 3:** Fill `evidence.py`: the two constants; a `__post_init__` that lower-cases the incomplete names, sets the inventory flag when only `headers_truncated` is given, and derives `headers_truncated` from the names and the inventory; `failed` is `status is None or incomplete_reason is not None`; `headers_complete(*names)` is false for an incomplete inventory or any listed incomplete name. A10 constructors stay valid (frozen dataclass defaults).
- [ ] **Step 4:** In the probe, group the raw headers by lower-cased name, call `bound_headers`, record the trailers flag, pass the three completeness values to `SyntheticResponse`, and import the constants from the engine. Delete `_retain` and its counters; re-export `HEADER_MAX_*` and `BODY_MAX_*` where the existing probe tests read them.
- [ ] **Step 5:** Run the A10 probe and report tests unchanged plus the new ones: `uv run pytest -q -n 4 tests/fastapi/test_pentesting_probe.py tests/engine/collectors/pentesting`. Run `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, and `uv run ruff check --select C901 --config 'lint.mccabe.max-complexity=9'` on the touched files (no function at 10 in the probe). Commit with explicit paths and `git commit -s`.

### Task 3: Port the CORS rule tests and report expectations (red first)

**Commit:** `test: port BootUI CORS preflight checks`

**Files:** `tests/engine/collectors/pentesting/test_pentesting_cors.py` (new), `test_pentesting_report.py`, `tests/fastapi/test_pentesting_api.py`, golden fixture; wrong-value stubs in `assessment.py` (new) and `cors.py` (new).

**Interfaces:** Stubs: `assessment.retained_headers` and `assessment.required_headers` return `True` and record no gap; `cors.evaluate` returns `([], [])`; `cors.options_diagnostic` returns `[]`. Each carries a comment naming Task 4. The tests define `cors.py`, `assessment.py` and the PT-A05-069 and A02 wording consumed by Task 4.

- [ ] **Step 1:** Rule tests, each with its citation and BootUI thresholds: `test_credentialed_wildcard_origin_is_low_and_browser_blocked` and `test_credentialed_reflected_origin_is_high` (# ported: `credentialedCorsDistinguishesBrowserBlockedWildcardFromReflectedOrigin`); `test_non_2xx_preflight_suppresses_origin_dependent_cors_rules` and `test_origin_and_credentials_comparisons_are_exact` (# ported: `successfulPreflightRequiresExactOriginAndCredentialTokens`); `test_null_origin_is_reported_without_credential_escalation` and its silent counterpart (# ported: `corsNullOriginCheckReportsUnmatchedOriginWithoutCredentialEscalation`, `corsNullOriginCheckStaysSilentWhenOriginIsNotLiteralNull`); `test_wildcard_methods_and_headers_need_a_permissive_origin` (# ported: `httpProbeChecksFlagWildcardCorsAndTraceAndMissingIsolationHeaders`, `wildcardCorsMethodsCheckStaysSilentWhenOriginIsTrusted`); `test_expose_headers_flags_sensitive_names_and_effective_wildcard_only` and `test_expose_headers_is_evaluated_per_probe_with_its_own_target` (# ported: `corsExposeHeadersCheckFlagsSensitiveAuthHeadersAndNonCredentialedWildcardWhileIgnoringSetCookie`); `test_duplicate_cors_header_values_are_joined_like_bootui`. Assert ID, title, severity, confidence, evidence text, recommendation and learn-more URL against the BootUI strings.
- [ ] **Step 2:** Asymmetry and echo tests: `test_origin_is_untrimmed_for_credentialed_cors_and_trimmed_elsewhere` (padded `*` and a padded credentials token), `test_expose_headers_get_half_uses_the_fixed_probe_origin` (the GET half is permissive for `*` and the probe origin constant only), `test_cors_evidence_echoes_only_constants_and_fixed_spellings` (padded origins show the constant; `X-API-KEY` and `x-xsrf-token` show their fixed spelling), `test_cors_evidence_never_echoes_non_matching_or_secret_origin_values`, `test_expose_headers_evidence_names_only_fixed_sensitive_headers`.
- [ ] **Step 3:** Completeness tests: `test_unrelated_incomplete_header_name_keeps_supported_cors_signals` (# ported: `unrelatedIncompleteOptionsFieldsDoNotSuppressSupportedPolicySignals`), `test_incomplete_header_inventory_suppresses_cors_rules_with_a_gap`, `test_bare_truncated_flag_suppresses_every_cors_rule`, and `test_incomplete_required_name_withholds_rule_and_records_gap`, parametrized by rule and required name: -007 and -008 with `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` incomplete; -065 and -023 with `Access-Control-Allow-Origin`; -073 with origin and `Access-Control-Expose-Headers`, and the wildcard case with credentials. Each case asserts no finding for that rule, exactly one fixed gap string, and, for -073 with only credentials incomplete, that a sensitive exposed name is still reported. Use an input that a rule reading only the retained dictionary would downgrade (an incomplete credentials value on a reflected origin).
- [ ] **Step 4:** Diagnostic and report tests: `test_truncated_options_body_alone_is_complete_evidence_for_cors` (no PT-A05-069, status `SCANNED`, A02 not `INDETERMINATE`, CORS rules evaluate, the body-limit limitation line stays; red against the current report), `test_options_failure_and_header_truncation_mark_derived_rules_indeterminate` and `test_options_failure_text_is_a_fixed_reason_not_exception_text` (# ported: `scanReportsOptionsProbeFailureSeparatelyFromGetProbeFailure`, `scanDoesNotReportOptionsProbeFailureWhenPreflightSucceeds`, `failedOptionsOrIncompleteJacksonMetadataMarksDependentCategoriesIndeterminate`; the text begins `Request failed before CORS preflight headers could be inspected` or `Response headers exceeded bounded retention limits`, names exactly PT-A05-007, -008, -023, -024, -065, and contains no exception text), `test_expose_headers_withheld_states_a_limitation_naming_the_rule`, a gap-string test for `OPTIONS response headers were incomplete.`, `OPTIONS probe was unavailable.` and `OPTIONS required response headers were incomplete.`, `test_standing_limitations_survive_when_every_cors_gap_is_present`, and `test_partial_scan_keeps_a02_indeterminate_when_a02_findings_exist`.
- [ ] **Step 5:** Safety and golden tests: `test_report_reads_after_cors_scan_do_not_invoke_host` (use `no_side_effects`), `test_cors_scan_respects_existing_gates_and_sends_no_probe_when_refused`, `test_cors_findings_keep_bootui_registry_order_and_golden` against an extended hand-derived ASGI golden (a hand-built preflight responder; Starlette's `CORSMiddleware` covers `test_cors_checks_follow_observed_starlette_cors_middleware_behaviour` instead), `test_preflight_without_cors_headers_is_clean_but_states_the_limit`, and a text test that "pending" no longer describes CORS while cookie and session checks remain pending (replace `test_cors_and_cookie_checks_are_reported_as_pending_not_unavailable` with a cookie-only assertion).
- [ ] **Step 6:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting tests/fastapi/test_pentesting_api.py tests/fastapi/test_pentesting_probe.py` and `uv run python scripts/dev/red_check.py <node ids>`; every new test must be RED by an assertion against a stub or the current report, none CRASH or PASS. Commit tests, stubs and fixtures with explicit `git add` and `git commit -s`.

### Task 4: Implement the CORS rules and report wiring

**Commit:** `feat: add BootUI CORS preflight checks`

**Files:** `assessment.py`, `cors.py`, `report.py`.

**Interfaces:** `assessment.retained_headers` and `assessment.required_headers` as in the file map; `cors.evaluate(get, options) -> tuple[list[Finding], list[str]]` returns findings (OPTIONS half before GET half for PT-A05-073) and deduplicated gaps; `cors.options_diagnostic(options) -> list[Finding]` is PT-A05-069. Consumed by `scanned_report`.

- [ ] **Step 1:** Confirm the Task 3 failures are named behaviour assertions.
- [ ] **Step 2:** Port BootUI's assessment helpers into `assessment.py` with its gap strings, then `PentestingResponsePolicies` (`successful_preflight`, `credentials`, `allowed_origin`, `matches_origin`, `permissive_origin`) and the five rules into `cors.py` with BootUI's order of checks and strings. Read values with `headers.joined`. Apply the echo and asymmetry decisions above. Keep every function at or under complexity 10.
- [ ] **Step 3:** Implement the two availability modes: rules that require headers (007, 008, 065, 023, 073) skip with a gap when the response failed or a required name is incomplete; PT-A05-024 keeps A10's behaviour. Add the fixed limitation that names PT-A05-073 when either of its halves is withheld.
- [ ] **Step 4:** In `report.py`, call `cors.evaluate` and `cors.options_diagnostic` and add the gaps to the limitations; make OPTIONS incompleteness `options.failed or options.headers_truncated` for PT-A05-069, the scan status and the A02 coverage (the GET rule is unchanged); remove the CORS "pending" limitation and the A02 scanned-description wording; add BootUI's A02 limitation that actual CORS resource responses were not tested. Keep the logic out of `scanned_report` so its complexity does not grow.
- [ ] **Step 5:** Run `uv run pytest -q -n 4` on the Task 3 files and `tests/test_code_shape.py`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`; confirm the Task 3 delete-the-control check (remove one rule and observe the named test fail). Commit with explicit paths and `git commit -s`.

### Task 5: Parity, matrix and documentation

**Commit:** `docs: document the CORS preflight checks`

**Files:** `docs/reference/matrix-updates/0.8.0-a11.tsv`, `0.8.0-a10.tsv`, `docs/reference/PARITY.md` (if it states the pending state), spec §14, user documentation that lists scan coverage.

- [ ] **Step 1:** Delete the `pentesting:cors-pending` row from `0.8.0-a10.tsv`, amend its `pentesting:framework-evidence` row to name the CORS checks on the OPTIONS probe and PT-A05-073 on both probes, and add the deviation rows below to `0.8.0-a11.tsv`.
- [ ] **Step 2:** Update the spec §14 and any user-facing text that describes CORS checks as pending; keep the cookie and session checks stated as pending.
- [ ] **Step 3:** Map every scenario row to a passing test by name; confirm registry order and golden match BootUI v2.5.0.
- [ ] **Step 4:** Run the lane tests (targeted, `-n 4`), `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`; report counts. Commit with explicit paths and `git commit -s`.

## Deviation rows (matrix fragment `0.8.0-a11.tsv`)

| Key | Status | Deviation | Reason |
|---|---|---|---|
| `pentesting:cors-transport` | adapted | The CORS checks evaluate the response of the in-process ASGI app to BootUI's fixed preflight (origin `https://evil.example`, request method `GET`), not a loopback HTTP response; the report labels it heuristic synthetic evidence and does not claim browser, proxy or deployed-edge behaviour. | Safety model 4 and 6 (no socket); consistent with `pentesting:transport`. |
| `pentesting:cors-evidence-spelling` | adapted | CORS evidence shows `*`, `null` or the fixed probe origin and the fixed spelling of each sensitive exposed header; the host's whitespace and header spelling are not repeated. BootUI's evidence text and comparisons are otherwise unchanged. | Masking boundary; consistent with `pentesting:body-evidence`. |
| `pentesting:options-failure-text` | adapted | PT-A05-069 states the probe's fixed incomplete reason instead of the transport error text. | Exception text can carry host data. |
| `pentesting:cors-expose-limitation` | adapted | A fixed limitation names PT-A05-073 as indeterminate when either of its probe halves is withheld; BootUI's PT-A05-069 text omits it. | Fail closed; the 069 text itself is BootUI's. |
| `pentesting:a02-partial-status` | adapted | A02 coverage is `INDETERMINATE` whenever the scan is partial, even when A02 findings exist; BootUI keeps the finding status and appends a limitation. | A10 behaviour kept; stricter. |
| `pentesting:cors-starlette-methods` | adapted | Starlette `CORSMiddleware` never sends `Access-Control-Allow-Methods: *`; PT-A05-023 reports only hosts that send the literal wildcard. | Framework behaviour; the check is ported as is. |

## Definition of done

- [ ] All Critical and High scenarios have named passing tests; gate, read-purity and request-count tests hold.
- [ ] Every `test:` commit was seen red by an assertion (`red_check` verdict RED, no CRASH) before its `feat:` commit.
- [ ] Registry order, titles, severities, confidence, evidence text and thresholds match BootUI v2.5.0 for PT-A05-007, -008, -065, -023, -073 and -069; PT-A05-024 is unchanged.
- [ ] No host-controlled value, spelling, exception text or raw response data appears in a finding, limitation or log.
- [ ] A failed, timed-out or header-truncated preflight never reads as clean; a truncated OPTIONS body alone does not make the scan partial; scan status and A02 coverage reflect it.
- [ ] The A10 tests pass unchanged except the CORS-pending assertion.
- [ ] No function over complexity 10 is added; `tests/test_code_shape.py` passes with the baseline unchanged or lower.
- [ ] Matrix fragments and spec §14 reflect the implementation (`pentesting:cors-pending` deleted); the lane gates pass with targeted test runs.
