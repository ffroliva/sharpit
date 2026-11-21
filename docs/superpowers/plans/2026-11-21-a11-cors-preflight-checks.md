# A11 CORS Preflight Checks Implementation Plan

> Run `/sharpit:status --feature a11-cors-preflight-checks` for the next unchecked step. Complete one task at a time and run `/sharpit:check` before each commit.

**Goal:** Replace the "pending" CORS entry of the pentesting scan with BootUI v2.5.0's CORS findings, evaluated on the OPTIONS and GET evidence that the scan already retains.

**Architecture:** The pentesting engine package gains one module for the CORS rules and a per-header-name completeness record on `SyntheticResponse`; the report builder calls the module and aligns PT-A05-069 with BootUI. The FastAPI probe changes only in how it records incompleteness. No request, route, tool or action is added: the scan keeps sending exactly one GET and one OPTIONS (fixed synthetic origin and request method, fixed path), and the existing gated scan action is the only way to reach the checks.

**Predict verdict:** Go with conditions (confidence 7/10). The conditions are folded into the tasks below.

**Review gate:** The plan inherits A10's reviewed in-process transport decision. Record the disposition of a high-tier review of this plan before Task 2 starts; the review covers evidence echo (host-controlled values), indeterminate handling, and the per-name completeness change to a safety-adjacent evidence record.

## Review disposition

- Pending until the review runs; implementation does not begin before it is recorded here.

## Global Constraints

- Reads have no side effects; no GET route or read MCP/CLI tool opens a socket, writes a file, changes a logger level, or changes `os.environ`.
- Actions follow BootUI: the scan keeps its enablement, guard, enabled-panel, non-read-only and single-flight gates; A11 adds no action.
- Secrets are masked before output; response bodies, exception text and host-controlled header values are not returned. CORS evidence names only `*`, `null`, the fixed probe origin, or a fixed sensitive header name.
- Python `>=3.12`; runtime dependencies exactly `starlette` and `packaging`; `engine/` imports no `fastapi` or `starlette`, and the FastAPI adapter imports the shared probe constants from the engine, never the reverse.
- Every ported test cites its BootUI source with `# ported: <Class>.<method>`.
- No module under `src/` exceeds 1000 lines; ratchets only go down (`checks.py` is 524 lines; the CORS rules go in their own module).
- A failure, timeout, truncation or unobserved header is indeterminate, never a clean result.
- Evidence describes a synthetic preflight against the in-process ASGI app; it never claims browser or deployed-edge behaviour.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A host-controlled header value (an origin, an exposed-header token) leaks into a finding | Echo only values equal to `*`, `null` or the fixed probe origin; name only fixed sensitive headers; secret-bearing inputs in tests. |
| Critical | A CORS check reads as clean when the preflight failed or a header was not retained | PT-A05-069 with a fixed reason, five dependent IDs named, per-name completeness, scan `PARTIAL`, A02 coverage `INDETERMINATE`. |
| High | Per-name completeness change alters A10's behaviour | Keep `headers_truncated` as a derived value; the existing A10 probe and report tests stay green unchanged. |
| High | Constants drift between the probe and the rules | One `PROBE_ORIGIN` and one `PROBE_REQUEST_METHOD` in the engine, imported by the probe; a test pins the request. |
| High | Comparison semantics drift from BootUI (case, trailing slash, `True` versus `true`) | Exact comparisons ported with BootUI's cases. |
| Medium | Report wording overstates CORS verification | Keep BootUI's "actual resource sharing was not tested" wording and add the A02 limitation; a text test pins both. |

## File map

- `src/sharpit/engine/collectors/pentesting/evidence.py`: `PROBE_ORIGIN`, `PROBE_REQUEST_METHOD`, per-name completeness on `SyntheticResponse`.
- `src/sharpit/fastapi/pentesting_probe.py`: record incomplete header names and inventory incompleteness; import the constants.
- `src/sharpit/engine/collectors/pentesting/cors.py` (new): the five CORS rules and their shared response policies.
- `src/sharpit/engine/collectors/pentesting/report.py`: call the CORS rules, align PT-A05-069, remove the pending wording, add the A02 limitation text.
- `tests/engine/collectors/pentesting/test_pentesting_cors.py` (new), `tests/engine/collectors/pentesting/test_pentesting_report.py`, `tests/fastapi/test_pentesting_probe.py`, `tests/fastapi/test_pentesting_api.py`.
- `tests/fixtures/bootui/2.5.0/pentesting/`: extend the hand-derived ASGI golden with CORS findings; the BootUI contract projection already lists the IDs and order.
- `docs/reference/matrix-updates/0.8.0-a11.tsv` (new) and `0.8.0-a10.tsv` (retire the CORS pending row), `docs/reference/PARITY.md` if it names the pending state, `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` §14.

BootUI sources ported (tag `v2.5.0`, `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/pentesting/`): `PentestingChecks.java` (`OptionsProbeFailedCheck`, `CredentialedCorsCheck`, `BroadCorsCheck`, `CorsNullOriginAllowedCheck`, `BroadCorsMethodsHeadersCheck`, `CorsExposeHeadersCheck`), `PentestingResponsePolicies.java` (`successfulPreflight`, `credentials`, `allowedOrigin`, `matchesOrigin`, `permissiveOrigin`), `PentestingAssessment.java` (`headers`, `retainedHeaders`, `gap`), `PentestingLocalHttpResponse.java` (`headersComplete`, bounded header retention), `PentestingCheckRegistry.java` (registry order, A02 coverage text), `PentestingScanner.java` (the fixed probe headers). Tests ported from `PentestingScannerTests.java` and `PentestingLocalHttpResponseTests.java` in the sibling test tree.

### Task 1: Freeze the CORS probe and completeness contract

**Commit:** `test: define the CORS preflight evidence contract`

**Files:** `tests/fastapi/test_pentesting_probe.py`, `tests/engine/collectors/pentesting/test_pentesting_cors.py`.

**Interfaces:** Defines `PROBE_ORIGIN`, `PROBE_REQUEST_METHOD` and the per-name completeness fields consumed by Tasks 2 to 4.

- [ ] **Step 1:** Add `test_options_uses_only_the_fixed_synthetic_origin_and_request_method`: the OPTIONS request carries exactly `Origin: https://evil.example` and `Access-Control-Request-Method: GET`, and those values equal the engine constants. No parameter of `probe()`, `install()` or the scan route can change them. # ported: `PentestingScannerTests.scanUsesOnlySyntheticLoopbackRequestsAndDoesNotExposeResponseBody`.
- [ ] **Step 2:** Add `test_scan_still_sends_exactly_one_get_and_one_options_request`: a CORS-bearing host receives two requests in order and nothing else. The existing sequence test stays unchanged.
- [ ] **Step 3:** Port the retention cases of `PentestingLocalHttpResponseTests` as `test_probe_records_incomplete_header_names_per_name` and `test_probe_marks_header_inventory_incomplete`: an oversized value or a value past the 128-value budget marks that name incomplete; more than 64 names, a blank or over-256-character name, or exhausting the 16 KiB budget marks the inventory incomplete; an incomplete name is not reported as absent. Read the case names in the BootUI test file at execution time and cite each.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_probe.py tests/engine/collectors/pentesting/test_pentesting_cors.py` and `uv run python scripts/dev/red_check.py <node ids>`; each failure must be an assertion naming the missing constant or field, not an import crash. Commit with explicit `git add` and `git commit -s`.

### Task 2: Per-name completeness and shared probe constants

**Commit:** `feat: record per-header completeness for pentesting evidence`

**Files:** `evidence.py`, `fastapi/pentesting_probe.py`.

**Interfaces:** `SyntheticResponse.incomplete_header_names: frozenset[str]`, `header_inventory_incomplete: bool`, `headers_complete(*names) -> bool`; `headers_truncated` becomes true whenever either is set. Consumed by `cors.py`.

- [ ] **Step 1:** Confirm Task 1 failures are the named behaviour assertions.
- [ ] **Step 2:** Add the constants and fields (frozen dataclass defaults keep every A10 constructor call valid). Port BootUI's rule: a name is incomplete when one of its values is oversized, past the value budget, or past the character budget; the inventory is incomplete for a name overflow, an invalid name, or the character budget before a name is read.
- [ ] **Step 3:** Update the probe to fill the new fields from the same decisions that currently set `headers_truncated`; import the constants from the engine.
- [ ] **Step 4:** Run the A10 probe and report tests unchanged plus the new ones: `uv run pytest -q -n 4 tests/fastapi/test_pentesting_probe.py tests/engine/collectors/pentesting`. Run `uv run ruff check`, `uv run ruff format --check` and `uv run pyright` on the touched files. Commit with explicit paths and `git commit -s`.

### Task 3: Port the CORS rule tests and report expectations

**Commit:** `test: port BootUI CORS preflight checks`

**Files:** `tests/engine/collectors/pentesting/test_pentesting_cors.py`, `test_pentesting_report.py`, `tests/fastapi/test_pentesting_api.py`, golden fixture.

**Interfaces:** Defines `cors.py` behaviour and the PT-A05-069 and A02 wording consumed by Task 4.

- [ ] **Step 1:** Rule tests, each with its citation and BootUI thresholds: `test_credentialed_wildcard_origin_is_low_and_browser_blocked` and `test_credentialed_reflected_origin_is_high` (# ported: `credentialedCorsDistinguishesBrowserBlockedWildcardFromReflectedOrigin`); `test_non_2xx_preflight_suppresses_origin_dependent_cors_rules` and `test_origin_and_credentials_comparisons_are_exact` (# ported: `successfulPreflightRequiresExactOriginAndCredentialTokens`); `test_null_origin_is_reported_without_credential_escalation` and its silent counterpart (# ported: `corsNullOriginCheckReportsUnmatchedOriginWithoutCredentialEscalation`, `corsNullOriginCheckStaysSilentWhenOriginIsNotLiteralNull`); `test_wildcard_methods_and_headers_need_a_permissive_origin` (# ported: `httpProbeChecksFlagWildcardCorsAndTraceAndMissingIsolationHeaders`, `wildcardCorsMethodsCheckStaysSilentWhenOriginIsTrusted`); `test_expose_headers_flags_sensitive_names_and_effective_wildcard_only` and `test_expose_headers_is_evaluated_per_probe_with_its_own_target` (# ported: `corsExposeHeadersCheckFlagsSensitiveAuthHeadersAndNonCredentialedWildcardWhileIgnoringSetCookie`). Assert ID, title, severity, confidence, evidence text, recommendation and learn-more URL against the BootUI strings.
- [ ] **Step 2:** Completeness tests: `test_unrelated_incomplete_header_name_keeps_supported_cors_signals` (# ported: `unrelatedIncompleteOptionsFieldsDoNotSuppressSupportedPolicySignals`) and `test_incomplete_header_inventory_suppresses_cors_rules_with_a_gap`.
- [ ] **Step 3:** Diagnostic tests: `test_options_failure_and_header_truncation_mark_derived_rules_indeterminate` and `test_options_failure_text_is_a_fixed_reason_not_exception_text` (# ported: `scanReportsOptionsProbeFailureSeparatelyFromGetProbeFailure`, `scanDoesNotReportOptionsProbeFailureWhenPreflightSucceeds`, `failedOptionsOrIncompleteJacksonMetadataMarksDependentCategoriesIndeterminate`); the text begins `Request failed before CORS preflight headers could be inspected` or `Response headers exceeded bounded retention limits`, names exactly PT-A05-007, -008, -023, -024, -065, and contains no exception text.
- [ ] **Step 4:** Safety tests: `test_cors_evidence_never_echoes_non_matching_or_secret_origin_values`, `test_expose_headers_evidence_names_only_fixed_sensitive_headers`, and `test_report_reads_after_cors_scan_do_not_invoke_host` (use `no_side_effects`).
- [ ] **Step 5:** Report tests: `test_cors_findings_keep_bootui_registry_order_and_golden` against an extended hand-derived ASGI golden (a hand-built preflight responder; Starlette's `CORSMiddleware` covers `test_cors_checks_follow_observed_starlette_cors_middleware_behaviour` instead), `test_preflight_without_cors_headers_is_clean_but_states_the_limit`, `test_cors_scan_respects_existing_gates_and_sends_no_probe_when_refused`, and a text test that "pending" no longer describes CORS while cookie and session checks remain pending (replace `test_cors_and_cookie_checks_are_reported_as_pending_not_unavailable` with a cookie-only assertion).
- [ ] **Step 6:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting tests/fastapi/test_pentesting_api.py tests/fastapi/test_pentesting_probe.py` and `uv run python scripts/dev/red_check.py <node ids>`; commit tests and fixtures with explicit `git add` and `git commit -s`.

### Task 4: Implement the CORS rules and report wiring

**Commit:** `feat: add BootUI CORS preflight checks`

**Files:** `cors.py`, `report.py`.

**Interfaces:** `cors.evaluate(get, options) -> tuple[list[Finding], list[str]]` returns findings and per-rule gaps; consumed by `scanned_report`.

- [ ] **Step 1:** Confirm Task 3 failures are named behaviour assertions.
- [ ] **Step 2:** Port `PentestingResponsePolicies` helpers and the five rules in `cors.py` with BootUI's order of checks and strings. Use the existing `first()` header accessor (first value, case-insensitive names). Apply the evidence-echo rule from the Global Constraints.
- [ ] **Step 3:** Implement BootUI's two availability modes: rules that require headers (007, 008, 065, 023, 073) skip with a gap when the response failed or a required name is incomplete; PT-A05-024 keeps A10's `retained headers` behaviour (evaluated when not failed, gap when incomplete).
- [ ] **Step 4:** In `report.py`, call `cors.evaluate` for OPTIONS and GET, add the gaps to `limitations` with BootUI's gap wording (`OPTIONS required response headers were incomplete.`), and align PT-A05-069: it fires when the OPTIONS request failed or its headers were incomplete, with BootUI's two evidence forms and the fixed reason; keep A10's existing trigger and its existing evidence text for body-only truncation (deviation row). Remove the CORS "pending" limitation and the A02 scanned-description wording; add BootUI's A02 limitation that actual CORS resource responses were not tested.
- [ ] **Step 5:** Run `uv run pytest -q -n 4` on the Task 3 files, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`; confirm the Task 3 delete-the-control check (remove one rule and observe the named test fail). Commit with explicit paths and `git commit -s`.

### Task 5: Parity, matrix and documentation

**Commit:** `docs: document the CORS preflight checks`

**Files:** `docs/reference/matrix-updates/0.8.0-a11.tsv`, `0.8.0-a10.tsv`, `docs/reference/PARITY.md` (if it states the pending state), spec §14, user documentation that lists scan coverage.

- [ ] **Step 1:** Remove the `pentesting:cors-pending` row from `0.8.0-a10.tsv` and add the deviation rows below to `0.8.0-a11.tsv`.
- [ ] **Step 2:** Update the spec §14 and any user-facing text that describes CORS checks as pending; keep the cookie and session checks stated as pending.
- [ ] **Step 3:** Map every scenario row to a passing test by name; confirm registry order and golden match BootUI v2.5.0.
- [ ] **Step 4:** Run the lane tests (targeted, `-n 4`), `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`; report counts. Commit with explicit paths and `git commit -s`.

## Deviation rows (matrix fragment `0.8.0-a11.tsv`)

| Key | Status | Deviation | Reason |
|---|---|---|---|
| `pentesting:cors-transport` | adapted | The CORS checks evaluate the response of the in-process ASGI app to BootUI's fixed preflight (origin `https://evil.example`, request method `GET`), not a loopback HTTP response; the report labels it heuristic synthetic evidence and does not claim browser, proxy or deployed-edge behaviour. | Safety model 4 and 6 (no socket); consistent with `pentesting:transport`. |
| `pentesting:cors-evidence-echo` | adapted | CORS evidence repeats an origin only when it is `*`, `null` or the fixed probe origin, and names only the fixed sensitive exposed headers; other host-controlled values are never echoed. BootUI's evidence text is otherwise unchanged. | Masking boundary; consistent with `pentesting:body-evidence`. |
| `pentesting:options-failure-text` | adapted | PT-A05-069 states a fixed reason from the probe instead of the transport error text. | Exception text can carry host data. |
| `pentesting:options-body-truncation` | adapted | A truncated OPTIONS body keeps A10's incomplete handling (PT-A05-069 and `PARTIAL`); BootUI treats only a failed OPTIONS request or truncated OPTIONS headers that way. | A10's stricter rule is retained; the body is not used by any CORS check. |
| `pentesting:cors-starlette-methods` | adapted | Starlette `CORSMiddleware` never sends `Access-Control-Allow-Methods: *`; PT-A05-023 reports only hosts that send the literal wildcard. | Framework behaviour; the check is ported as is. |
| `pentesting:cors-pending` | retired | Removed from the A10 fragment; the checks are implemented. | Lane A11. |

## Definition of done

- [ ] Review disposition recorded before Task 2.
- [ ] All Critical and High scenarios have named passing tests; gate, read-purity and request-count tests hold.
- [ ] Registry order, titles, severities, confidence, evidence text and thresholds match BootUI v2.5.0 for PT-A05-007, -008, -065, -023, -073 and -069; PT-A05-024 is unchanged.
- [ ] No host-controlled value, exception text or raw response data appears in a finding, limitation or log.
- [ ] A failed, timed-out or truncated preflight never reads as clean; scan status and A02 coverage reflect it.
- [ ] The A10 tests pass unchanged except the CORS-pending assertion.
- [ ] Matrix fragments and spec §14 reflect the implementation; the lane gates pass with targeted test runs.
