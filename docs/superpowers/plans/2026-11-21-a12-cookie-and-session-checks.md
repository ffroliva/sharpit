# A12 Cookie and Session-Cookie Checks Implementation Plan

> Run `/sharpit:status --feature a12-cookie-and-session-checks` for the next unchecked step. Complete one task at a
> time and run `/sharpit:check` before each commit. Companion: `2026-11-21-a12-cookie-and-session-checks-scenario.md`.

**Goal:** Replace the pending cookie and session entries of the A10 pentesting scan with the nine BootUI v2.5.0 cookie
checks, reporting cookie names and flags only and never cookie values.

**Architecture:** A10's bounded GET response is the only cookie source; no request is added. The probe adapter hands
each raw `Set-Cookie` text to a framework-free parser in the pentesting engine package at capture time. The parser
returns a value-free `CookieObservation`, and the raw text is dropped, so `SyntheticResponse` never holds a cookie
value. Seven checks evaluate those observations (and `Cache-Control` for PT-A02-008). Two metadata checks evaluate
`SessionMiddleware` facts that the scan action reads statically from the existing security facts. Report order,
DTOs, dismissals and the action gates are A10's and do not change.

**Predict verdict:** GO WITH CONDITIONS, 7/10. Conditions folded in: values stripped at collection time, per-surface
planted-value tests, observed evidence kept distinct from configuration evidence, failure and truncation kept
indeterminate, no new request, no cookie decoder.

**Review gate:** Complete the required high-tier review of this plan and record its disposition before Task 1. The
gate covers the value boundary, the name-label policy, per-name header incompleteness, and the metadata-check
adaptation to `SessionMiddleware`.

## Review disposition

- Pending: to be recorded before implementation begins.

## Global Constraints

- Reads have no side effects; no GET route and no read MCP or CLI tool opens a socket, writes a file, changes a logger
  level, changes `os.environ`, invokes the host application, or reads middleware facts to build a result.
- Actions follow BootUI: the checks run only inside the existing scan action, behind its gates (enabled console,
  guard chain, enabled panel, panel not read-only, MCP or CLI enabled, single-flight).
- Secrets are masked before output; a cookie value, a raw `Set-Cookie` line, an attribute value and secret-key
  material never appear in an observation, report, error, log, MCP result, CLI output or persisted file.
- Python `>=3.12`; runtime dependencies exactly `starlette` and `packaging`; the engine imports no Starlette or
  FastAPI; no new module under `src/` exceeds 1000 lines; ratchets only go down.
- Every ported test cites its BootUI source with `# ported: <Class>.<method>`.
- Every test command is targeted: `uv run pytest -q -n 4 <files>`. The full suite is not run locally.
- Before every `test:` commit: `uv run python scripts/dev/red_check.py <node ids>`; the red is an assertion, never an
  import or collection error.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A cookie value reaches output through a name label (`<value>; Secure`, `=<value>`) | Names are RFC 6265 tokens only; anything else is `(unnamed)`; tests 2-3 of the scenario. |
| Critical | Raw values stay on `SyntheticResponse` or in its `repr` | The probe routes `Set-Cookie` through the parser; `headers` never holds `set-cookie`; repr test. |
| Critical | Parser failure text contains input | Parser is total and raises nothing; the probe's generic failure text is unchanged. |
| High | A dropped over-long cookie reads as "no cookie" | Per-name incompleteness on the response; cookie result PARTIAL with a limitation; the dropped cookie is not named. |
| High | Configuration evidence is mistaken for observed cookies | Separate evidence objects, targets name the middleware option, coverage text distinguishes them. |
| High | Starlette default `https_only=False` flagged as "explicitly false" | Only a keyword passed as `False` sets the new fact; default and absent options stay silent. |
| Medium | Merge conflicts with the CORS lane in `report.py` and the matrix | Edit only the cookie words of shared sentences; own matrix file. |

## File map

- `src/sharpit/engine/collectors/pentesting/cookie_observation.py` (new): `CookieObservation`, `parse_set_cookie`.
- `src/sharpit/engine/collectors/pentesting/cookie_checks.py` (new): the seven observed checks, the two metadata
  checks, `SessionEvidence`, `session_evidence(facts)`.
- `src/sharpit/engine/collectors/pentesting/evidence.py`: `cookies`, `incomplete_headers`, `inventory_incomplete`,
  `headers_complete(*names)` on `SyntheticResponse` (defaults keep A10 constructors valid).
- `src/sharpit/fastapi/pentesting_probe.py`: capture-time routing of `Set-Cookie` and per-name incompleteness.
- `src/sharpit/fastapi/introspection_security.py`: one new fact name in `_session_flags`.
- `src/sharpit/fastapi/routes/pentesting.py`, `engine/collectors/pentesting/service.py`, `report.py`: session evidence
  into the scan, cookie findings into the report, text and coverage updates.
- Tests: `tests/engine/collectors/pentesting/test_cookie_observation.py`, `test_cookie_checks.py`,
  `test_session_cookie_config.py`; `tests/fastapi/test_pentesting_cookie_probe.py`,
  `test_pentesting_cookie_surfaces.py`; additions to `tests/fastapi/test_introspector_security.py` and
  `tests/engine/collectors/pentesting/test_pentesting_report.py`.
- `tests/fixtures/bootui/2.5.0/pentesting/`: extend the BootUI rule-contract projection and the hand-derived ASGI
  golden with cookie cases; fixtures use fake non-secret values.
- `docs/reference/matrix-updates/0.8.0-a12.tsv`, `docs/reference/PARITY.md`, design spec §14, user docs.

## Interfaces

```python
@dataclass(frozen=True)
class CookieObservation:
    name: str                    # safe label: RFC 6265 token <= 80 chars, "(redacted)" or "(unnamed)"
    attributes: frozenset[str]   # lowercase names present, closed set: secure, httponly, domain, samesite, path, max-age, expires
    same_site: str | None        # last SameSite value, lowercased; "" for a bare attribute; None when absent
    path: str | None             # last Path value; None when absent
    deletion: bool               # BootUI isDeletionCookie, decided before the value is dropped

def parse_set_cookie(raw: str) -> CookieObservation: ...   # total; never raises; never retains raw
```

`SyntheticResponse` gains `cookies: tuple[CookieObservation, ...] = ()`, `incomplete_headers: frozenset[str] =
frozenset()`, `inventory_incomplete: bool = False`, and `headers_complete(*names) -> bool` (BootUI
`headersComplete`). `scanned_report(get, options, scanned_at=None, session=None)` and `PentestingService.scan(...,
session=None)` accept `SessionEvidence | None`; `None` means no configuration evidence was supplied (no finding, no
limitation), which keeps A10 callers unchanged. The scan route always supplies a value.

## Deviation rows (written to `0.8.0-a12.tsv` in Task 10)

| Key | Status | Deviation | Reason |
|---|---|---|---|
| `pentesting:cookie-values` | adapted | `Set-Cookie` values and raw header text are discarded at capture; only a name label and the closed attribute facts are retained; `SyntheticResponse.headers` has no `set-cookie` key | Safety model 3 |
| `pentesting:cookie-names` | adapted | A name is shown only when it is an RFC 6265 token (at most 80 characters, BootUI's label bound) and not secret-shaped; a first segment without `=`, an empty name or a non-token is `(unnamed)`, a secret-shaped token is `(redacted)`. BootUI shows the whole first segment, which can be a value | Safety model 3 |
| `pentesting:session-config` | adapted | PT-A02-004 and PT-A02-006 read `SessionMiddleware(https_only=..., same_site=...)` keyword options from the static security facts instead of `server.servlet.session.cookie.*`; "explicitly false" means the keyword was passed as `False` (Starlette's default is also false); IDs, titles, severities and confidence are BootUI's; target, evidence and recommendation name the middleware option instead of a Spring property; positional or unreadable options are indeterminate | Spring properties do not exist |
| `pentesting:cookie-overlap` | adapted | The Security panel rules SEC-SESSION-002 and SEC-SESSION-004 stay as they are; the pentesting checks report separate evidence under their own IDs, as BootUI does for its Security and Pentesting panels | No duplicate claims |
| `pentesting:cookie-pending` | resolved | The A10 row is removed in this lane's docs commit; the CORS row stays | The seven GET-derived checks are evaluated |

## Task 1: Freeze the cookie observation contract and the value boundary

**Commit:** `test: define the value-free cookie observation contract`

**Files:** `tests/engine/collectors/pentesting/test_cookie_observation.py`; stubs `cookie_observation.py` and the
`SyntheticResponse` fields, so failures are assertions.

**Interfaces:** Produces `CookieObservation` and `parse_set_cookie` signatures consumed by Tasks 2-6.

- [ ] **Step 1:** Add `CookieObservation` and a `parse_set_cookie` stub that returns an observation named
  `"(stub)"`; add the three new `SyntheticResponse` fields with defaults and `headers_complete` returning `True`.
- [ ] **Step 2:** Write the observation tests of the scenario: `test_cookie_value_never_enters_an_observation` (value
  canary built with `uuid4` at run time; asserts the canary is in no field and not in `repr`),
  `test_segment_without_equals_is_unnamed_and_discarded`, `test_empty_name_is_unnamed_and_discarded`,
  `test_extension_and_domain_attribute_values_are_not_retained`, `test_non_token_and_oversized_names_are_labelled_safely`,
  `test_secret_shaped_name_is_redacted` (JWT and vendor-token shapes through `engine.masking.is_secret_value`),
  `test_parser_is_total_on_malformed_input` (empty, only `;`, control characters, 1 MiB text, lone surrogates).
- [ ] **Step 3:** Port the parsing cases. `# ported: PentestingScannerTests.cookiesUsePresenceFlagsAndLastSameSiteAttribute`
  (`Secure=false` and `HttpOnly=false` count as present, last `SameSite` wins),
  `# ported: PentestingScannerTests.cookieAttributeParsingRequiresWholeAttributeNames` (`Securely`, `HttpOnlyFlag`,
  `SameSitePolicy=Lax`), and `# ported: PentestingScannerTests.deletionCookiesAreIgnoredWhilePrefixedAndAdditionalSessionCookieNamesAreRecognized`
  for the deletion cases (`Max-Age=0`, `Max-Age=-1`, blank value with 1970 `Expires`; quoted `Max-Age="-1"` and
  `Max-Age=3600` over a 1970 `Expires` are not deletions). Cite `PentestingCheckSupport.java:90-98,162-184,257-290`
  beside the cases.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_cookie_observation.py`; confirm
  assertion reds, then `uv run python scripts/dev/red_check.py <node ids>`; commit with explicit `git add` and
  `git commit -s`.

## Task 2: Implement the parser

**Commit:** `feat: parse Set-Cookie into value-free observations`

**Files:** `src/sharpit/engine/collectors/pentesting/cookie_observation.py`, `evidence.py`.

- [ ] **Step 1:** Implement `parse_set_cookie`: split on `;`, take the first segment's text before the first `=` as
  the candidate name (token characters per RFC 6265 `token`, trimmed); no `=` or empty candidate gives `(unnamed)`;
  more than 80 characters is shortened as BootUI's bounded label (77 characters and `...`); a secret-shaped token
  gives `(redacted)`. Collect only the closed attribute set from the remaining segments with BootUI's rules (presence
  by whole attribute name, case-insensitive; value after `=`; last occurrence wins). Compute `deletion` from the
  `Max-Age` and `Expires` text and the blank-or-`""`-or-`deleted` value before returning; keep none of that text.
- [ ] **Step 2:** Implement `SyntheticResponse.headers_complete(*names)` as BootUI `headersComplete`: false when the
  inventory is incomplete or a requested lowercase name is in `incomplete_headers`.
- [ ] **Step 3:** Run the Task 1 file and the A10 evidence and report tests
  (`tests/engine/collectors/pentesting`); commit.

## Task 3: Freeze the probe cookie boundary

**Commit:** `test: pin the cookie boundary of the synthetic probe`

**Files:** `tests/fastapi/test_pentesting_cookie_probe.py`.

- [ ] **Step 1:** Using a test ASGI app that emits raw header tuples, assert
  `test_set_cookie_values_never_reach_the_synthetic_response` (canary absent from `headers`, `cookies`, `repr`,
  `str`), `test_synthetic_response_repr_holds_no_header_text`, and
  `test_duplicate_set_cookie_headers_become_ordered_observations` (arrival order, deletion cookies kept as
  observations with `deletion` true).
- [ ] **Step 2:** Assert `test_overlong_cookie_value_marks_set_cookie_incomplete_only` (a 4097-character value is not
  an observation, `headers_complete("set-cookie")` is false, `headers_complete("cache-control")` stays true, the
  other cookies are retained; `# ported: PentestingScannerTests.incompleteFieldsDoNotInventMissingCookieFlagsOrEffectivePolicies`)
  and `test_header_budgets_count_raw_cookie_text_before_parsing` (128-value, 64-name and 16 KiB limits still count
  the raw text; `# ported: PentestingLocalHttpResponse` limits, `PentestingLocalHttpResponse.java:20-135`).
- [ ] **Step 3:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_cookie_probe.py tests/fastapi/test_pentesting_probe.py`;
  confirm assertion reds; `red_check.py`; commit.

## Task 4: Route `Set-Cookie` through the parser at capture time

**Commit:** `feat: discard cookie values at the probe boundary`

**Files:** `src/sharpit/fastapi/pentesting_probe.py`.

- [ ] **Step 1:** In `_Capture._retain`, keep the existing budget accounting on the raw text, then for the name
  `set-cookie` call `parse_set_cookie(value)` and store only the observation; the raw value is never stored in
  `capture.headers`. Record the header name in an `incomplete_headers` set wherever a value or the name is dropped
  (over-limit value, null-equivalent, value count, character budget) and set `inventory_incomplete` where BootUI sets
  `headerInventoryIncomplete` (name count, name length, blank name, header-character budget). `headers_truncated`
  keeps its current meaning.
- [ ] **Step 2:** Build the frozen `SyntheticResponse` with the new fields; the Host-rejection and failure paths keep
  their current generic texts.
- [ ] **Step 3:** Run the Task 3 file plus `tests/fastapi/test_pentesting_probe.py` and
  `tests/fastapi/test_pentesting_api.py`; commit.

## Task 5: Freeze the seven observed-cookie checks

**Commit:** `test: port the BootUI observed cookie checks`

**Files:** `tests/engine/collectors/pentesting/test_cookie_checks.py`; stub `cookie_checks.py` with `observed(get,
limitations)` returning `[]`.

**Interfaces:** `observed(get: SyntheticResponse, limitations: list[str]) -> list[Finding]`, evaluated on the GET
response only.

- [ ] **Step 1:** Port by named BootUI case, each with its `# ported:` line and the IDs, titles, severities,
  confidence, category, recommendation and learn-more text taken from the `PentestingChecks.java` lines in the scenario
  scope table:
  - PT-A02-001: `conventionalCsrfCookieWithoutHttpOnlyIsAnInformationalReviewHint` and the severity loop of
    `deletionCookiesAreIgnoredWhilePrefixedAndAdditionalSessionCookieNamesAreRecognized` (`__Host-SESSION`,
    `__Secure-JSESSIONID`, `q_session`, `q_session_admin`, `remember-me` are MEDIUM; the CSRF text and name-based
    INFO cases; `PentestingChecks.java:405-439`).
  - PT-A05-005 (`:458-472`; `none` is a recognised value), PT-A02-002 (`:491-502`), PT-A02-003
    (`cookieCheckFlagsSameSiteNoneWithoutSecure`).
  - PT-A02-007 (`cookiePrefixRequirementsCheckFlagsViolationsAndAllowsCompliantCookies`; evaluated over the unfiltered
    observation list, `:2589`; `__host-` lowercase is not a prefix).
  - PT-A05-064 (`sessionCookieMissingPrefixCheckFlagsSecureSessionCookieWithoutPrefix`,
    `sessionCookieMissingPrefixCheckStaysSilentWhenPrefixOrSecureIsMissing`,
    `sessionCookiePrefixCheckDoesNotClassifyEveryHttpOnlyCookieAsASession`).
  - PT-A02-008 (`cacheableSetCookieCheckDistinguishesPublicSharedAndSessionMaxAgeCaching`: all listed
    `Cache-Control` forms; reuse `checks._split_outside_quotes`, which already ports `splitOutsideQuotes`).
  - Evidence and target texts follow BootUI (`"Set-Cookie " + name`, quoting the label).
- [ ] **Step 2:** Add the indeterminate and edge tests of the scenario:
  `test_failed_or_rejected_get_leaves_cookie_checks_indeterminate`,
  `test_incomplete_set_cookie_inventory_keeps_cookie_result_partial` (retained cookies still evaluated, limitation
  recorded, the dropped cookie unnamed), `test_cache_control_incomplete_does_not_manufacture_a_finding`,
  `test_planted_value_is_absent_from_every_finding_field` (canary in value, nameless token, empty name, extension
  attribute).
- [ ] **Step 3:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_cookie_checks.py`; confirm
  assertion reds; `red_check.py`; commit.

## Task 6: Implement the observed checks and report wiring

**Commit:** `feat: evaluate BootUI cookie checks on the synthetic GET`

**Files:** `cookie_checks.py`, `report.py`, `tests/engine/collectors/pentesting/test_pentesting_report.py`.

- [ ] **Step 1:** Implement `observed`: a response that is unavailable (`checks.available` false) yields nothing;
  non-deletion observations feed PT-A02-001, PT-A05-005, PT-A02-002, PT-A02-003, PT-A05-064 and PT-A02-008; PT-A02-007
  reads all observations; PT-A02-008 runs only when `headers_complete("cache-control")` and an observed cookie exist.
  When `headers_complete("set-cookie")` is false, append the limitation `"Set-Cookie response headers exceeded a
  bounded retention limit; cookie results are incomplete."`. Findings keep arrival order within a rule; the report's
  stable sort by `RULE_ORDER` orders rules.
- [ ] **Step 2:** In `scanned_report`, call `observed` inside the `checks.available(get)` branch after
  `_get_findings`, so a truncated unrelated header does not suppress cookie checks and the cookie checks do not
  depend on A10's early return.
- [ ] **Step 3:** Replace the cookie pending text: remove only the words "and cookie and session checks" from the
  limitation sentence and "cookie," from the A02 description; do not edit the CORS words. Update
  `test_cors_and_cookie_checks_are_reported_as_pending_not_unavailable` to assert the cookie words are gone and the
  CORS words remain. Add coverage text from BootUI's `scopeLimitations` (`PentestingCheckRegistry.java`,
  `scopeLimitations`): A02 ends with "Cookie issuance on other routes and actual CORS resource responses were not
  tested." (CORS phrase unchanged if the CORS lane has not changed it) and A04 states the BootUI no-finding text for
  cookie and transport checks plus "No observed Set-Cookie does not establish that the application has no sessions."
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting` and
  `tests/fastapi/test_pentesting_api.py`; commit.

## Task 7: Freeze the session-configuration checks

**Commit:** `test: port the BootUI session cookie configuration checks`

**Files:** `tests/engine/collectors/pentesting/test_session_cookie_config.py`, an addition to
`tests/fastapi/test_introspector_security.py`; stub `SessionEvidence`, `session_evidence`, `configured`.

**Interfaces:** `SessionEvidence(configs: tuple[SessionCookieConfig, ...], limitation: str | None)`;
`SessionCookieConfig(mount: str | None, https_only_false: bool, same_site_none: bool)`;
`session_evidence(facts: SecurityFacts | None) -> SessionEvidence`;
`configured(session: SessionEvidence | None, limitations) -> list[Finding]`.

- [ ] **Step 1:** Port the BootUI cases to `SessionMiddleware` options. `# ported: SpringPentestingObservationCollectorTests.metadataChecksStaySilentForSafeConfiguration`
  (`SpringPentestingObservationCollectorTests.java:533-550`: no PT-A02-004 or PT-A02-006 for a safe configuration) and
  `# ported: SpringPentestingObservationCollectorTests.metadataChecksFlagAdditionalLowFalsePositiveSpringSettings`
  (`:625-655`: SameSite none with secure false gives PT-A02-006). Tests:
  `test_explicit_https_only_false_is_flagged_and_default_is_not`,
  `test_same_site_none_with_secure_disabled_is_flagged` (also the `https_only=True` and `same_site="lax"` silent
  cases), `test_unreadable_session_options_leave_metadata_checks_indeterminate` (positional options, no facts,
  non-FastAPI app: limitation, no finding, no pass), and a mounted sub-app case that names the mount path.
- [ ] **Step 2:** Add `test_https_only_false_flag_is_read_from_keyword_only` to the introspection tests: a keyword
  `https_only=False` yields the new fact, an absent keyword and `True` do not, and no option value (including
  `secret_key`) appears in the facts.
- [ ] **Step 3:** Run both files with `uv run pytest -q -n 4`; confirm assertion reds; `red_check.py`; commit.

## Task 8: Implement the metadata checks and wire the scan

**Commit:** `feat: evaluate session cookie configuration in the pentesting scan`

**Files:** `introspection_security.py`, `cookie_checks.py`, `report.py`, `service.py`, `fastapi/routes/pentesting.py`.

- [ ] **Step 1:** In `_session_flags`, add `https_only_false` when the keyword is present and `is False`; the reader
  keeps returning fact names only. Existing `https_only` and `same_site_none` behavior is unchanged, so the Security
  panel rules are unchanged.
- [ ] **Step 2:** Implement `session_evidence` and `configured`: PT-A02-004 for each `https_only_false`; PT-A02-006
  for each config with `same_site_none` and `https_only_false`. Keep BootUI titles, severities (LOW; MEDIUM),
  confidence (Medium; High) and categories (A04; A02); target, evidence and recommendation name the
  `SessionMiddleware` option and the mount path when present, never an option value.
- [ ] **Step 3:** In the scan route, read facts as the Security tools do (the duck-typed `security_facts` of the
  introspector, a static read), build `SessionEvidence`, and pass it through `service.scan` to `scanned_report`;
  facts that are absent or carry `limitations` set the evidence limitation. A non-empty limitation adds the
  limitation text and makes the scan PARTIAL without inventing a finding. The scan action and its gates are
  unchanged; no read path builds session evidence.
- [ ] **Step 4:** Run the Task 7 files, `tests/engine/collectors/pentesting`,
  `tests/fastapi/test_pentesting_api.py` and `tests/fastapi/test_introspector_security.py`; commit.

## Task 9: Prove the surfaces, the gates and the controls

**Commit:** `test: assert no cookie value on any pentesting output surface`

**Files:** `tests/fastapi/test_pentesting_cookie_surfaces.py`.

- [ ] **Step 1:** `test_planted_cookie_value_is_absent_from_every_output_surface`: a host that sets cookies with a
  run-time canary in a value, a name-less token, an empty name, an extension attribute and an over-long value; one
  parametrised case each for POST scan body, cached GET report body, MCP `pentest_scan` summary, MCP
  `get_pentest_report`, CLI `pentest scan` and `pentest report` (tool endpoint and command output), an error body
  (409 and 504 paths), captured log records (`caplog`, stderr) and every file under `SHARPIT_STATE_DIR`. Reuse the
  client factory pattern of `tests/fastapi/test_pentesting_api.py:23-68`.
- [ ] **Step 2:** `test_cookie_checks_are_scan_action_only_and_read_only_denied`: GET and read tools make no host
  call, open no socket (`no_side_effects`), and never read middleware facts; read-only panel, disabled panel, MCP off,
  inactive and cross-site scans refuse before any host call (`# ported:` none; AGENTS action gates).
- [ ] **Step 3:** Prove the controls by deletion: temporarily make the parser return the raw first segment as the
  name, then keep a raw value in `SyntheticResponse.headers`, then drop the per-name incompleteness; each change must
  fail a named test here or in Tasks 1-6. Record the failing test names in the commit body and restore the code.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_cookie_surfaces.py tests/fastapi/test_pentesting_api.py`;
  commit.

## Task 10: Contract fixtures, parity and documentation

**Commit:** `docs: document the cookie and session checks of the pentesting scan`

**Files:** `tests/fixtures/bootui/2.5.0/pentesting/*`, `tests/engine/collectors/pentesting/test_pentesting_report.py`,
`docs/reference/matrix-updates/0.8.0-a12.tsv`, `docs/reference/matrix-updates/0.8.0-a10.tsv` (remove the
`pentesting:cookie-pending` row only), `docs/reference/PARITY.md`, design spec §14, user documentation.

- [ ] **Step 1:** Extend the BootUI-derived rule-contract projection with the nine checks' fields
  (`test_cookie_rules_follow_registry_order_and_bootui_contract`) and the hand-derived ASGI golden with a
  cookie-setting response using fake non-secret values; keep the two fixtures separate as in A10.
- [ ] **Step 2:** Add `test_cookie_pending_text_is_replaced_and_cors_pending_text_remains`.
- [ ] **Step 3:** Write the five deviation rows above to `0.8.0-a12.tsv`, mirror them in spec §14, update the
  pentesting row of `PARITY.md`, and describe in the user documentation what the cookie checks observe (one GET, names
  and flags only, in-process ASGI evidence, no TLS edge) and what the configuration checks read.
- [ ] **Step 4:** Run the lane tests (`uv run pytest -q -n 4 tests/engine/collectors/pentesting tests/fastapi/test_pentesting_api.py tests/fastapi/test_pentesting_probe.py tests/fastapi/test_pentesting_cookie_probe.py tests/fastapi/test_pentesting_cookie_surfaces.py tests/fastapi/test_introspector_security.py tests/engine/collectors/security/test_rules_transport.py tests/parity`),
  `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`; report counts. Commit docs with explicit paths
  and `git commit -s`.

## Definition of done

- [ ] High-tier review disposition is recorded before Task 1.
- [ ] Every Critical and High scenario row has a named passing test; every value-bearing surface has a planted-value
  case; each control was proven by deletion.
- [ ] The seven observed checks and two metadata checks match the BootUI v2.5.0 IDs, titles, severities, confidence,
  categories and order, with observed and configuration evidence kept separate.
- [ ] Failure, rejection, truncation and unreadable configuration never read as a clean result.
- [ ] The A10 cookie "pending" text and matrix row are replaced; the CORS text is untouched.
- [ ] Lane tests, ruff and pyright pass; live verification states that evidence is ASGI-only, one GET, names and flags
  only.
