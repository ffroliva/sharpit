# A12 Cookie and Session-Cookie Checks Implementation Plan

> Run `/sharpit:status --feature a12-cookie-and-session-checks` for the next unchecked step. Complete one task at a
> time and run `/sharpit:check` before each commit. Companion: `2026-11-21-a12-cookie-and-session-checks-scenario.md`.

**Goal:** Replace the pending cookie and session entries of the A10 pentesting scan with the nine BootUI v2.5.0 cookie
checks, reporting cookie names and flags only and never cookie values.

**Architecture:** A10's bounded GET response is the only cookie source; no request is added. Lane A11 (merged first)
supplies the bounded-header function, per-name completeness, the assessment helpers, and, inside `cors.py`, the
masked-evidence callable and the evidence sanitiser. Task 0 of this lane moves those two into the shared module
`pentesting/echo.py` (this lane merges before A13, so it is the first lane to need them outside CORS); every finding of
this lane passes through that sanitiser, and no copy is made. The probe passes the bounded headers through one framework-free split
that turns each raw `Set-Cookie` text into a value-free `CookieObservation` and removes `set-cookie` from the header map,
so `SyntheticResponse` never holds a cookie value. Seven checks evaluate those observations (and `Cache-Control` for
PT-A02-008). Two metadata checks evaluate `SessionMiddleware` facts that the scan action reads statically through one
shared reader, which lane A13 also uses. Report order, DTOs, dismissals and the action gates are A10's and do not change.

**Predict verdict:** GO WITH CONDITIONS, 7/10. Conditions folded in: values stripped at collection time, per-surface
planted-value tests in every exposure, observed evidence kept distinct from configuration evidence, failure and
truncation kept indeterminate, no new request, no cookie decoder.

## Review disposition

Plan review on 2026-11-21: approved with eight changes, all folded into this revision.

| Change | Where |
|---|---|
| Merge order A10, A11, A12; reuse A11's completeness and header helpers instead of adding copies | Merge order; Tasks 3-4 |
| PT-A02-007 and PT-A02-008 are active, HTTP-derived checks; the nine-check scope stands | Scenario, Scope |
| `CookieObservation` keeps no attribute value (closed `SameSite` enum, `path_is_root`) | Interfaces; Task 1 |
| Secret check on the full name before the 80-character shortening; padded-base64 residual pinned | Task 1-2 |
| PT-A02-008 evidence rebuilt from parsed directives, never the raw `Cache-Control` text | Task 9-10 |
| BootUI's gap wording, no new limitation text | Tasks 9-10, 12 |
| Capture-middleware surface and an assertion that A12's limitation strings survive the 20-entry cut | Task 13 |
| Per-group check tasks, split surface tasks; Flask recorded as a deviation note | Task list; deviation rows |

Second plan review on 2026-11-21: approved with changes, all folded into this revision.

| Change | Where |
|---|---|
| Every finding passes through the shared evidence sanitiser (CR, LF and TAB runs, trim, 240-character cut); the shared module is created by this lane's Task 0 and A13 drops its own Task 0 | Architecture; Task 0; Tasks 6-8 |
| The Task 3 and Task 4 stubs no longer clash: the Task 4 stub names the finding with the echoed cookie name | Task 4 |
| `read_security_facts` has its own red-first unit tests (raising reader with a canary message, absent attribute, wrong type) | Tasks 11-12 |
| Host-level `Cache-Control` canary tests in all three exposures, covering a complete header and an over-long one, with both BootUI gap strings | Task 3; Tasks 9-10 |
| "Every exposure" is reconciled with the capture exclusion under `FULL`: the exception is stated as decision, rationale and consequence | Global Constraints; Task 13; deviation rows |
| `boundedLabel` uses an explicit ASCII class, with a non-breaking-space test | Tasks 1-2 |

Verified before writing (BootUI at tag `v2.5.0`, `bootui-engine/.../engine/pentesting/`; `Checks` is
`PentestingChecks.java`, `Support` is `PentestingCheckSupport.java`, `Assessment` is `PentestingAssessment.java`,
`Registry` is `PentestingCheckRegistry.java`):

- `Registry.java:61-62` registers `CookiePrefixRequirementsCheck` and `CacheableSetCookieCheck` as active; both are
  `HTTP_SYNTHETIC` (`Checks.java:2568-2582`, `2634-2645`). Only PT-A02-004 and PT-A02-006 are `SPRING_METADATA`
  (`Checks.java:1671-1727`).
- `Support.cookieName` (`:90-98`) keeps the whole first segment as the name when `=` is at index 0 or absent, so a
  literal port puts a value in a target and evidence (`Checks.java:416, 498, 1018, 1051`).
- `Support.boundedLabel` (`:327-333`) maps control and whitespace runs to `_` and shortens past 80 characters to 77
  plus `...`. `sharpit.engine.masking.is_secret_value` fullmatches the stripped text (`masking.py:92`): a 152-character
  JWT-shaped name is secret, its 77-character cut with `...` is not (run with `uv run python -c`).
- `Checks.java:2668, 2678, 2693` put the joined raw `Cache-Control` text into PT-A02-008 evidence; A10's module
  invariant (`checks.py:3-4`) is that header values are never echoed.
- `Assessment.java:59-65` is `retainedHeaders` with the gap `<METHOD> required response headers were incomplete.`;
  `Assessment.java:85-91` is `cookies`, which drops deletion cookies; `Assessment.java:41-44` is the configuration gap
  `Framework configuration evidence was incomplete.`
- Starlette 1.10.0 `middleware/sessions.py`: `https_only: bool = False` (`:25`) adds `secure` only when truthy
  (`:34-36`); the value is `b64encode(json)` of signed session data (`:70`); a clear writes the value `null` with a 1970
  `expires` (`:82-87`), which `Support.isDeletionCookie` (`:162-184`) does not treat as a deletion.
- Flask 3.1.3 `flask/app.py:194,196`: `SESSION_COOKIE_SECURE` defaults to `False` and `SESSION_COOKIE_SAMESITE` to
  `None`, so an explicit false cannot be told from the default. `src/sharpit/flask/` has no pentesting code.
- Capture records pass through `masker.mask_header` (`engine/capture/exchanges.py:55-59`, `traces.py:110-116`); the
  capture middleware is added to the host app (`fastapi/capture.py:483`), which the probe calls. `report.py:413-414`
  keeps at most 20 limitations of 240 characters.
- `introspector.py:878-882` writes the mount path into a limitation, so `SecurityFacts.limitations` text is never copied.

## Merge order

A10, then A11, then A12 (this branch is stacked on A10 and is rebased onto A11 before Task 1 while it is unpushed,
merged in otherwise), then A13. A11 adds `SyntheticResponse.incomplete_header_names`, `header_inventory_incomplete`,
`headers_complete(*names)`; `headers.bound_headers` and `headers.joined`; `assessment.retained_headers` and
`required_headers`; the evidence sanitiser and `make_echo(masker)` (in `cors.py`); the required keyword-only `masker` of
`PentestingService.scan`. This lane reuses all of them and defines no equivalent; its Task 0 only moves the sanitiser
and `make_echo` into `pentesting/echo.py` (behaviour unchanged), and lane A13, which merges after this one, uses that
module without a move of its own. The shared edits (the pending
sentence in `report.py`, the A02 description, the pending-text test, `0.8.0-a10.tsv`, `PARITY.md`, spec section 14)
are resolved by the lane that merges second, which edits only its own words.

## Global Constraints

- Reads have no side effects; no GET route and no read MCP or CLI tool opens a socket, writes a file, changes a logger
  level, changes `os.environ`, invokes the host application, or reads security facts.
- Actions follow BootUI: the checks run only inside the existing scan action, behind its gates (enabled console, guard
  chain, enabled panel, panel not read-only, MCP or CLI enabled, single-flight).
- A cookie value, a raw `Set-Cookie` line, an attribute value, a raw `Cache-Control` text and a `SecurityFacts.limitations`
  text never appear in an observation, report, error, log, MCP result, CLI output or persisted file of the scan, in every
  exposure. A cookie name and a mount path are the only host-chosen text reaching evidence, and each passes through the
  shared `echo` and then the whole evidence string through `echo.sanitize_evidence` (CR, LF and TAB runs to one space,
  Java trim, 240 characters with `...`, BootUI `PentestingCheckSupport.evidence`); fixed BootUI text is never masked.
- **FULL exception for capture records.** Decision: the probe exchange recorded by the host's capture middleware is not
  excluded or rewritten; under `FULL` its `Set-Cookie` value is shown, as for every captured exchange. Rationale:
  `FULL` is the explicit opt-in to unmasked text, `Masker.mask_header` shows header values there by design for all
  captured traffic, the probe is an ordinary in-process request, and changing header masking or suppressing probe
  exchanges is a masking change that needs `/sharpit:predict` and `/sharpit:llm-council --tier high`. Consequence: the
  value guarantee holds for everything the scan itself produces in all three exposures, and for capture records in
  `MASKED` and `METADATA_ONLY`; under `FULL` the capture panel shows the probe's cookie as it shows any host response.
  Recorded as deviation row `pentesting:cookie-capture-full`; Task 13 pins both sides.
- Python `>=3.12`; runtime dependencies exactly `starlette` and `packaging`; the engine imports no Starlette or FastAPI;
  no module under `src/` exceeds 1000 lines; ruff C901 counts only go down.
- Every ported test cites its BootUI source with `# ported: <Class>.<method>`.
- Every test command is targeted: `uv run pytest -q -n 4 <files>`; `export UV_LINK_MODE=copy`. The full suite is not run
  locally.
- **Red first, wrong-value stubs.** Before every `test:` commit run `uv run python scripts/dev/red_check.py <node ids>`;
  the red is an assertion, never an import, collection or `TypeError`. A stub returns the wrong state in both
  directions: it fires where the test expects silence and is wrong where the test expects a finding, so a `[]` stub is
  not allowed. Every absence assertion is paired with the presence assertion of the finding or label it would appear in.
- Value-boundary and exposure tests use the real `Masker` in `MASKED`, `METADATA_ONLY` and `FULL`, with run-time
  canaries (`uuid4`).

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A cookie value reaches output through a name (`<value>; Secure`, `=<value>`, a JWT-shaped long name) | `(unnamed)` for a first segment without `=` at index above 0; secret check on the full name before shortening; echo on output; surface tests in three exposures. |
| Critical | Raw values stay on `SyntheticResponse` or in its `repr` | `split_cookies` removes `set-cookie`; observation holds no text beyond the label; repr test. |
| Critical | PT-A02-008 evidence echoes `Cache-Control` text | Evidence rebuilt from a closed directive vocabulary; `x-token=<canary>` test. |
| Critical | `SameSite=`, `Path=` or extension values retained | Closed `SameSite` enum and `path_is_root`; canary test over `repr`. |
| Critical | A mount path or facts limitation text reaches the report | Mount path through `echo`; limitation text never copied; fixed BootUI gap. |
| High | A dropped over-long cookie reads as "no cookie" | A11's per-name incompleteness; BootUI gap string; the dropped cookie is never named. |
| High | Configuration evidence is mistaken for observed cookies | Separate evidence, targets name the middleware option, coverage text distinguishes them. |
| High | Starlette's default `https_only=False` flagged as explicit | Only a keyword passed as `False` sets the new fact. |
| High | A12's limitation strings are cut by the 20-entry limit | Worst-case set test that asserts each A12 string survives. |
| High | A finding's evidence exceeds BootUI's 240-character cut (PT-A02-007 with three violations is 233 characters plus the name) | Every finding passes `echo.sanitize_evidence`; an all-violations `__Host-` cookie pins the cut. |
| High | A raising `security_facts()` leaks its message or crashes the scan | `read_security_facts` catches `Exception`, logs nothing, returns `None`; red-first unit tests with a canary message. |
| Medium | A cookie value reaches a capture record under `FULL` | Stated exception (Global Constraints); `MASKED` and `METADATA_ONLY` pinned; deviation row. |
| Medium | Python `\s` is Unicode and relabels a name BootUI keeps | Explicit ASCII class in `boundedLabel`; non-breaking-space test. |
| Medium | Facts read twice per scan (A12 and A13) | One shared reader; call-count test. |

## File map

- `src/sharpit/engine/collectors/pentesting/echo.py` (new, the one shared home, Task 0): `make_echo(masker)` and
  `sanitize_evidence(text)`, moved unchanged out of A11's `cors.py`; `cors.py` only imports them.
- `src/sharpit/engine/collectors/pentesting/cookie_observation.py` (new): `SameSite`, `CookieObservation`,
  `parse_set_cookie`, `split_cookies`.
- `src/sharpit/engine/collectors/pentesting/cookie_checks.py` (new): the seven observed checks, `observed`.
- `src/sharpit/engine/collectors/pentesting/cache_control.py` (new): `parse_cache_control`, `directive_summary`; reuses
  `checks._split_outside_quotes` (already the port of `splitOutsideQuotes`).
- `src/sharpit/engine/collectors/pentesting/session_cookie.py` (new): `SessionCookieConfig`, `SessionEvidence`,
  `session_evidence`, `configured`.
- `src/sharpit/engine/collectors/pentesting/evidence.py`: one new field, `SyntheticResponse.cookies`.
- `src/sharpit/engine/collectors/pentesting/report.py`, `service.py`: cookie findings and gaps in the report, the
  `session` keyword, text and coverage updates.
- `src/sharpit/fastapi/pentesting_probe.py`: call `split_cookies` after `bound_headers`.
- `src/sharpit/fastapi/pentesting_exposure.py` (new here; A13 extends it and does not recreate it):
  `read_security_facts(introspector) -> SecurityFacts | None`, the single per-scan read, `except Exception`, no logging,
  `None` on failure, absence or a result that is not `SecurityFacts`.
- `src/sharpit/fastapi/introspection_security.py`: one new flag name in `_session_flags`.
- `src/sharpit/fastapi/routes/pentesting.py`: read the facts once, build `SessionEvidence`, pass `session` to `scan`.
- Tests: `tests/engine/collectors/pentesting/test_evidence_echo.py`, `tests/fastapi/test_pentesting_exposure_adapter.py`
  (A13 adds its own cases to this file), `tests/engine/collectors/pentesting/test_cookie_observation.py`, `test_cookie_checks.py`,
  `test_cache_control.py`, `test_session_cookie_config.py`; `tests/fastapi/test_pentesting_cookie_probe.py`,
  `test_pentesting_cookie_surfaces.py`, `test_pentesting_cookie_hidden_surfaces.py`; additions to
  `tests/fastapi/test_introspector_security.py` and `tests/engine/collectors/pentesting/test_pentesting_report.py`.
- `tests/fixtures/bootui/2.5.0/pentesting/`: extend the rule-contract projection and the hand-derived ASGI golden with
  cookie cases (fake non-secret values; the two fixtures stay separate as in A10).
- `docs/reference/matrix-updates/0.8.0-a12.tsv`, `0.8.0-a10.tsv` (remove the `pentesting:cookie-pending` row only),
  `docs/reference/PARITY.md`, design spec section 14, user documentation.

## Interfaces

```python
class SameSite(StrEnum):
    LAX = "lax"; STRICT = "strict"; NONE = "none"; OTHER = "other"   # OTHER: any other value, including bare or empty

@dataclass(frozen=True)
class CookieObservation:
    name: str                     # BootUI label, "(unnamed)" or "(redacted)"; the only text kept from the header
    attributes: frozenset[str]    # presence, closed set: secure, httponly, domain, samesite, path
    same_site: SameSite | None    # last SameSite value, classified; None when absent
    path_is_root: bool            # last Path value, trimmed, equals "/" (BootUI cookieAttributeValue)
    deletion: bool                # Support.isDeletionCookie, decided before the text is dropped

def parse_set_cookie(raw: str) -> CookieObservation: ...      # total; never raises; retains no raw text
def split_cookies(headers: Mapping[str, tuple[str, ...]]) -> tuple[dict[str, tuple[str, ...]], tuple[CookieObservation, ...]]
def observed(get: SyntheticResponse, gaps: list[str], echo: Callable[[str], str]) -> list[Finding]
# every finding is built as checks.finding(rule, target, echo.sanitize_evidence(evidence)); the echo is applied to the
# name first, so the sanitiser sees the whole sentence
```

`SyntheticResponse.cookies: tuple[CookieObservation, ...] = ()`. Completeness is A11's: `headers_complete("set-cookie")`
reads the names `bound_headers` recorded as dropped. `scanned_report(..., session=None)` and
`PentestingService.scan(..., *, masker, session=None)` take `SessionEvidence | None`; `None` means no configuration
evidence was supplied (no finding, no gap), which keeps A10 and A11 callers valid. The scan route always supplies one.

## Deviation rows (written to `0.8.0-a12.tsv` in Task 14)

| Key | Status | Deviation | Reason |
|---|---|---|---|
| `pentesting:cookie-values` | adapted | `Set-Cookie` values and raw header text are discarded at the probe boundary; only the observation is kept and `SyntheticResponse.headers` has no `set-cookie` key | Safety model 3 (forced) |
| `pentesting:cookie-attributes` | adapted | `SameSite` is a closed enum and `Path` a boolean; no attribute value is retained. BootUI's checks read only those classifications (`Checks.java:458-467`, `2603-2608`) | Safety model 3 (forced) |
| `pentesting:cookie-name-unnamed` | adapted | A first segment with no `=` at index above 0 is `(unnamed)`; BootUI shows the whole segment, which can be a value | Safety model 3 (forced) |
| `pentesting:cookie-name-redacted` | default taken, owner to confirm | A name that `is_secret_value` matches, tested on the full name before the 80-character shortening, is `(redacted)`; the engine otherwise treats names as non-secret, so this is stricter than it. Severity logic sees an INFO label | Fail closed |
| `pentesting:cookie-name-echo` | adapted | Names and mount paths pass through A11's `echo`; under `METADATA_ONLY` they read `[masked]`; classification runs on the unmasked label | A11 rule, safety model 3 (forced) |
| `pentesting:cookie-name-residual` | default taken, owner to confirm | A nameless padded base64 value (`dGVzdA==; Secure`) keeps the unpadded part as its label, as RFC 6265bis reads a name; pinned by a test | Not distinguishable from a name |
| `pentesting:cache-control-evidence` | default taken, owner to confirm | PT-A02-008 evidence lists the recognised directive names (numeric arguments for `max-age`, `s-maxage`, `stale-*` only) and a count of other directives, not the raw header text | A10 invariant; masking cannot keep the text readable |
| `pentesting:cookie-capture-full` | default taken, owner to confirm | Under `FULL` the capture middleware records the probe exchange with its `Set-Cookie` value, as for any captured exchange; `MASKED` and `METADATA_ONLY` records hold no value | `FULL` is the opt-in to unmasked text; changing header masking is a separate predict and council decision |
| `pentesting:session-config` | adapted | PT-A02-004 and PT-A02-006 read `SessionMiddleware(https_only=..., same_site=...)` keyword options from the static security facts instead of `server.servlet.session.cookie.*`; "explicitly false" means the keyword was passed as `False`; target, evidence and recommendation name the middleware option; IDs, titles, severities, confidence and categories are BootUI's | Spring properties do not exist (forced) |
| `pentesting:session-config-gap` | default taken, owner to confirm | Facts that are absent or carry any limitation record BootUI's gap `Framework configuration evidence was incomplete.` and no limitation text; counting every limitation, not only session-related ones, is the conservative default | Text may carry a mount path (text forced; count is the default) |
| `pentesting:session-clear-cookie` | parity note | Starlette's clear writes the value `null` with a 1970 `expires`; BootUI's rule does not treat it as a deletion, so it is evaluated like any cookie | Ported faithfully |
| `pentesting:flask-session-config` | deviation note | Not ported for Flask: `app.config` always holds `SESSION_COOKIE_SECURE` and `SESSION_COOKIE_SAMESITE` with defaults, so an explicit false is undetectable, and the Flask adapter has no pentesting scan | Python/Flask forces |
| `pentesting:cookie-overlap` | adapted | The Security panel rules SEC-SESSION-002 and SEC-SESSION-004 stay; the pentesting checks report separate evidence under their own IDs, as BootUI's two panels do | No duplicate claims |
| `pentesting:cookie-pending` | resolved | The A10 row is removed; the cookie words leave the pending text | The checks are evaluated |

## Task 0: Share the evidence echo and sanitiser

**Commit:** `refactor: move the pentesting evidence echo and sanitiser to a shared module`

**Precondition:** A11 has merged into this branch. If A11 already put `make_echo` and the sanitiser in a shared module,
use that module's name throughout this plan and skip this task; this plan assumes they sit in `cors.py`. Lane A13's
plan names `echo.py` and drops its own Task 0 because this task creates the module first.

**Files:** `engine/collectors/pentesting/echo.py`, `engine/collectors/pentesting/cors.py`,
`tests/engine/collectors/pentesting/test_evidence_echo.py`.

**Interfaces:** `make_echo(masker) -> Callable[[str], str]` (the masked fragment, or `[masked]` when `masker.mask_text`
returns `None`) and `sanitize_evidence(text) -> str`. Behaviour is A11's, unchanged; only the home changes. The module
imports no `Masker` class and no HTTP code (`tests/engine/test_import_boundary.py`).

**Stub for the red run:** `echo.py` with `make_echo` returning the identity function and `sanitize_evidence` returning
its input, so the tests fail on their assertions and not on an import.

- [ ] **Step 1:** Write `test_evidence_echo.py` with the behaviour A11's tests already pin, against the shared module:
  `test_sanitizer_collapses_cr_lf_and_tab_runs_to_one_space`, `test_sanitizer_trims_java_whitespace`,
  `test_sanitizer_cuts_at_240_characters_with_an_ellipsis` (237 characters plus `...`), and one echo test per exposure
  (`MASKED` shows the fragment, `METADATA_ONLY` gives `[masked]`, `FULL` shows it) with the real `Masker`.
  `# ported: PentestingCheckSupport.evidence` (`PentestingCheckSupport.java:51-63`).
- [ ] **Step 2:** Run the file against the stub, confirm assertion reds, `red_check.py`. Then move the code from
  `cors.py` into `echo.py`, import it in `cors.py`, keep A11's tests green unchanged
  (`uv run pytest -q -n 4 tests/engine/collectors/pentesting tests/engine/test_import_boundary.py`), and make one commit
  with explicit paths and `git commit -s`.

## Task 1: Freeze the value-free observation contract

**Commit:** `test: define the value-free cookie observation contract`

**Files:** `tests/engine/collectors/pentesting/test_cookie_observation.py`; wrong-value stub `cookie_observation.py`; the
`cookies` field of `SyntheticResponse`.

**Stub:** `parse_set_cookie` is BootUI's literal `cookieName` (the whole first segment as the name, attribute presence
by substring, no deletion), the wrong-value shape the tests rule out.

- [ ] **Step 1:** Observation tests: `test_cookie_value_never_enters_an_observation` (canary absent from every field and
  `repr`; the label `NAME` is present), `test_segment_without_equals_is_unnamed` (`<canary>; Secure`),
  `test_empty_name_is_unnamed` (`=<canary>; Secure`), `test_attribute_values_are_never_retained` (`SameSite=<canary>`,
  `Path=/<canary>`, `Domain=`, `Foo=<canary>`: canary absent from `repr`; `same_site` is `SameSite.OTHER`;
  `path_is_root` false), `test_label_follows_bootui_bound_and_replaces_whitespace` (runs of U+0000-U+0020 and U+007F, which is Java's
  `[\p{Cntrl}\s]` at `Support.java:328`, to `_`; 81 characters to 77 plus `...`),
  `test_label_keeps_unicode_whitespace_that_java_does_not_match` (U+00A0, U+0085, U+2003 and U+3000 stay in the label
  and U+007F becomes `_`; the presence assertion is the finding named with that label), `test_secret_shaped_name_is_redacted_before_shortening` (a 152-character JWT-shaped
  name gives `(redacted)`, not a 77-character prefix; vendor-token shapes; the shortened text of a non-secret name is
  unchanged), `test_padded_base64_without_a_name_keeps_the_unpadded_label` (pins the residual of the deviation row),
  `test_parser_is_total_on_malformed_input` (empty, only `;`, control characters, 1 MiB text, lone surrogates: each
  returns the observation with name `(unnamed)`, no attributes and no deletion).
- [ ] **Step 2:** Port the parsing cases as `test_attribute_parsing_uses_presence_whole_names_and_last_samesite` and
  `test_deletion_cookies_are_marked_and_non_deletions_are_not` (attribute names also compare as Java
  `equalsIgnoreCase`). `# ported: PentestingScannerTests.cookiesUsePresenceFlagsAndLastSameSiteAttribute`
  (`Secure=false` and `HttpOnly=false` count as present; last `SameSite` wins; a bare attribute is the empty value),
  `# ported: PentestingScannerTests.cookieAttributeParsingRequiresWholeAttributeNames` (`Securely`, `HttpOnlyFlag`,
  `SameSitePolicy=Lax`), and the deletion cases of
  `# ported: PentestingScannerTests.deletionCookiesAreIgnoredWhilePrefixedAndAdditionalSessionCookieNamesAreRecognized`
  (`Max-Age=0`, `Max-Age=-1`, blank, `""` or `deleted` value with a 1970 `Expires`; quoted `Max-Age="-1"` and a
  20-digit `Max-Age` fall through to the `Expires` rule; `Max-Age=3600` over a 1970 `Expires` is not a deletion).
  Add `test_starlette_session_clear_is_not_a_deletion_cookie` (`session=null; expires=Thu, 01 Jan 1970 ...`).
  Cite `Support.java:90-98, 162-184, 257-290` beside the cases.
- [ ] **Step 3:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_cookie_observation.py`; confirm
  assertion reds, then `red_check.py <node ids>`; commit with explicit `git add` and `git commit -s`.

## Task 2: Implement the parser

**Commit:** `feat: parse Set-Cookie into value-free observations`

**Files:** `src/sharpit/engine/collectors/pentesting/cookie_observation.py`.

- [ ] **Step 1:** Implement `parse_set_cookie` with A11's `java_trim` and `java_is_blank`. A blank text gives
  `(unnamed)`. The first segment is `raw.split(";", 1)[0]`; the name text is the part before the first `=` only when
  that `=` is at index above 0, otherwise `(unnamed)`; a blank name is `(unnamed)`. Trim the name, return `(redacted)`
  when `masking.is_secret_value` is true on the full trimmed name, then apply `boundedLabel`: `re.sub(r"[\x00-\x20\x7f]+", "_", label)`, an explicit ASCII class (Java's `\p{Cntrl}` and
  `\s` are ASCII only; Python's `\s` is Unicode and is never used here), then over 80 characters to 77 plus `...`. Attribute segments are `raw.split(";")[1:]`, trimmed; names compare as
  Java `equalsIgnoreCase`; presence needs the whole name; the value is the last occurrence per `cookieAttributeValue`.
  `same_site` classifies the last value case-insensitively; `path_is_root` is the last `Path` value equal to `/`.
- [ ] **Step 2:** Compute `deletion` as `isDeletionCookie`: a `Max-Age` that parses as Java `Long.parseLong` (optional
  sign, decimal digits, 64-bit range) decides at or below zero; anything else falls through to the blank-value-and-1970
  rule. Keep none of that text. Wrap the body so the function never raises and never puts input in a message.
- [ ] **Step 3:** Run the Task 1 file and `tests/engine/collectors/pentesting`; commit.

## Task 3: Freeze the probe boundary and the cookie surfaces of the report

**Commit:** `test: pin the cookie value boundary of the probe and the report surfaces`

**Files:** `tests/fastapi/test_pentesting_cookie_probe.py`, `tests/fastapi/test_pentesting_cookie_surfaces.py`; stubs
`cookie_observation.split_cookies` and `cookie_checks.observed`, and the call of `observed` in `scanned_report`.

**Stubs:** `split_cookies` returns the headers unchanged and no observations (raw `set-cookie` stays on the response).
`observed` is the literal port: for each raw `set-cookie` value in `get.headers` it emits PT-A02-001 with target
`Set-Cookie <whole first segment>` and evidence naming it, and ignores `echo`. Both are the wrong-value shapes.

- [ ] **Step 1:** Probe boundary, with a test ASGI app that emits raw header tuples:
  `test_set_cookie_values_never_reach_the_synthetic_response` (canary absent from `headers`, `cookies`, `repr`, `str`;
  the cookie name is present as an observation), `test_synthetic_response_repr_holds_no_header_text`,
  `test_duplicate_set_cookie_headers_become_ordered_observations` (arrival order; deletion cookies kept with `deletion`
  true), `test_overlong_cookie_value_marks_set_cookie_incomplete_only` (a 4097-character value is not an observation,
  `headers_complete("set-cookie")` is false, `headers_complete("cache-control")` stays true, other cookies retained;
  `# ported: PentestingScannerTests.incompleteFieldsDoNotInventMissingCookieFlagsOrEffectivePolicies`),
  `test_header_budgets_apply_to_raw_cookie_text_before_parsing` (128 values, 64 names, 16 KiB still count raw text).
- [ ] **Step 2:** Surfaces, real `Masker`, one parametrised case per surface and exposure (`MASKED`, `METADATA_ONLY`,
  `FULL`): POST scan body, cached GET report body, MCP `pentest_scan` summary, MCP `get_pentest_report`, CLI
  `pentest scan` and `pentest report` (tool endpoint and command output). The host sets a well-formed
  `session=<canary>; Path=/` (no `HttpOnly`, so its PT-A02-001 finding must be present, with the name `session` in `MASKED` and
  `FULL` and `[masked]` in `METADATA_ONLY`), a name-less `<canary>; Secure`, an empty-name `=<canary>; Secure`,
  `Foo=<canary>`, `SameSite=<canary>`, `Path=/<canary>`, a JWT-shaped 152-character name, an over-long value, and
  `Cache-Control: public, x-token=<canary>` (PT-A02-008 must be present and the canary absent on every surface).
  `FULL` is the discriminating exposure: values are dropped by the parser, not masked. Reuse the client factory of
  `tests/fastapi/test_pentesting_api.py:23-68`.
- [ ] **Step 2b:** `test_cache_control_canary_is_absent_from_every_output_surface`, parametrised by surface and exposure
  as in Step 2, over host responses that each set `session=<canary>; Path=/` (no `HttpOnly`) plus one `Cache-Control` header, with a run-time
  canary: (a) `public, x-token=<canary>`: PT-A02-008 present, evidence names `public` and one other directive;
  (b) `max-age=<canary>`: no PT-A02-008 (a non-numeric `max-age` is not positive, `Checks.java:2741`) and the cookie's
  PT-A02-001 still present; (c) an over-long value (more than 4096 characters, so A11's `bound_headers` drops it) that
  starts with `public, x-token=<canary>` or `max-age=<canary>`: no PT-A02-008, the scan is PARTIAL, and both of BootUI's
  gap strings, `GET required response headers were incomplete.` and `GET required response headers were unavailable.`
  (`Assessment.java:59-71`, reached through `headers()` at `Checks.java:2653`), are present on every surface that carries
  the report limitations. The canary is absent everywhere in all three exposures.
- [ ] **Step 3:** Run both files plus `tests/fastapi/test_pentesting_probe.py`; confirm assertion reds;
  `red_check.py`; commit. The reds of Step 2b for cases (a) and (c) stay assertion reds until Task 10.

## Task 4: Route `Set-Cookie` through the split at the probe boundary

**Commit:** `feat: discard cookie values at the probe boundary`

**Files:** `cookie_observation.py`, `src/sharpit/fastapi/pentesting_probe.py`, `cookie_checks.py` (stub moves to reading
`get.cookies`), `evidence.py`.

- [ ] **Step 1:** Implement `split_cookies`: parse every `set-cookie` value in arrival order, return the header map
  without that key and the observations. Budget accounting stays in A11's `bound_headers`, which runs first on the raw
  text, so a dropped value is recorded by name and never parsed.
- [ ] **Step 2:** In the probe, call `split_cookies` on the bounded headers before building the frozen response, and set
  `SyntheticResponse.cookies`. The raw lists are never stored on the capture object past this call. The Host-rejection
  and failure paths keep their generic texts.
- [ ] **Step 3:** Change the `observed` stub to read `get.cookies` and emit one wrong-value finding per cookie:
  `PT-A02-001`, `INFO`, target `"Set-Cookie " + echo(obs.name)` and evidence `echo(obs.name)`. The finding is named with
  the cookie's echoed label (`session`, or `[masked]` in `METADATA_ONLY`), so the Task 3 Step 2 presence assertions and
  the canary-absence assertions turn green for the right reason, and the stub is wrong everywhere else (every cookie,
  every flag state and deletion cookies get the same INFO finding, no other rule, no gap), so the checks of Tasks 5, 7
  and 9 stay red until Tasks 6, 8 and 10. The Task 3 stub's literal `stub` target is not reused.
- [ ] **Step 4:** Run the Task 3 files and `tests/fastapi/test_pentesting_api.py`; commit.

## Task 5: Freeze the flag checks (PT-A02-001, PT-A05-005, PT-A02-002, PT-A02-003)

**Commit:** `test: port the BootUI HttpOnly, SameSite and Secure cookie checks`

**Files:** `tests/engine/collectors/pentesting/test_cookie_checks.py` (group 1).

- [ ] **Step 1:** Port by named BootUI case with `# ported:` lines; IDs, titles, severities, confidence, category,
  recommendation and learn-more text from `Checks.java:389-503` and `992-1023`:
  `test_missing_httponly_is_medium_for_session_names_and_info_for_csrf_and_other`
  (`conventionalCsrfCookieWithoutHttpOnlyIsAnInformationalReviewHint` and the severity loop of
  `deletionCookiesAreIgnoredWhilePrefixedAndAdditionalSessionCookieNamesAreRecognized`: `__Host-SESSION`,
  `__Secure-JSESSIONID`, `q_session`, `q_session_admin`, `remember-me` MEDIUM), `test_samesite_missing_or_unrecognised_is_flagged`
  (`none` is recognised; `Lax ` trimmed), `test_missing_secure_is_flagged`,
  `test_samesite_none_without_secure_is_flagged` (`cookieCheckFlagsSameSiteNoneWithoutSecure`),
  `test_deletion_cookies_feed_no_flag_check`, `test_flag_findings_name_the_echoed_label_and_classify_the_unmasked_one`
  (a recording `echo` shows each target and evidence name went through it before the 240-character cut; severity follows
  the unmasked label), `test_redacted_and_unnamed_labels_are_info_severity`.
- [ ] **Step 2:** Run the file; confirm assertion reds (the stub is wrong in both directions); `red_check.py`; commit.

## Task 6: Implement the flag checks

**Commit:** `feat: evaluate the BootUI cookie flag checks on the synthetic GET`

**Files:** `cookie_checks.py`, `report.py`, `service.py`.

- [ ] **Step 1:** Implement the four rules over non-deletion observations (BootUI `Assessment.cookies`), in BootUI's
  order of checks and strings; target `"Set-Cookie " + echo(name)`; evidence is BootUI's sentence with `echo(name)`, passed
  through `echo.sanitize_evidence` by the one local finding helper that every rule of `cookie_checks.py` uses (imported
  from the shared `echo.py`, never copied); findings keep arrival order within a rule and the report's stable sort by
  `RULE_ORDER` orders rules.
- [ ] **Step 2:** Gate with `assessment.retained_headers("GET", get, ("set-cookie",), gaps)` (A11): an unavailable
  response yields nothing and the gap is BootUI's `GET required response headers were incomplete.`; retained cookies are
  still evaluated when the inventory is incomplete. In `scanned_report` call `observed` after `_get_findings`, inside
  the `checks.available(get)` branch, with the `echo` that `PentestingService.scan` builds from `masker` (A11).
- [ ] **Step 3:** Run the Task 3 and Task 5 files and `tests/engine/collectors/pentesting`; commit.

## Task 7: Freeze the prefix checks (PT-A02-007, PT-A05-064)

**Commit:** `test: port the BootUI cookie prefix checks`

**Files:** `test_cookie_checks.py` (group 2).

- [ ] **Step 1:** `test_prefix_requirements_are_checked_for_host_and_secure_cookies`
  (`cookiePrefixRequirementsCheckFlagsViolationsAndAllowsCompliantCookies`; evaluated over the unfiltered observations,
  `Checks.java:2584-2591`, so a deletion cookie is checked; `__host-` lowercase is not a prefix; `Path=/` is
  `path_is_root`; evidence names the violations only),
  `test_session_cookie_prefix_check_needs_secure_session_name_without_prefix`
  (`sessionCookieMissingPrefixCheckFlagsSecureSessionCookieWithoutPrefix`,
  `sessionCookieMissingPrefixCheckStaysSilentWhenPrefixOrSecureIsMissing`,
  `sessionCookiePrefixCheckDoesNotClassifyEveryHttpOnlyCookieAsASession`; `Checks.java:1025-1064`),
  `test_cookie_finding_evidence_is_sanitised_and_cut_at_240_characters` (the all-violations cookie
  `__Host-session=<canary>; Domain=example.test; Path=/x`, no `Secure`: PT-A02-007 is present with all three violations
  named; BootUI's sentence is 233 characters plus the name (`Checks.java:2616-2619`), so the evidence is exactly 240
  characters, 237 and `...`, with no CR, LF or TAB; `# ported: PentestingCheckSupport.evidence`), and
  `test_cookie_finding_evidence_goes_through_the_shared_sanitiser` (a recording stand-in patched over the sanitiser name
  that `cookie_checks.py` uses sees the whole sentence after `echo`; one case each for PT-A02-001, -002, -003, -007, -008, PT-A05-005 and -064).
- [ ] **Step 2:** Run; confirm assertion reds; `red_check.py`; commit.

## Task 8: Implement the prefix checks

**Commit:** `feat: evaluate the BootUI cookie prefix checks`

**Files:** `cookie_checks.py`.

- [ ] **Step 1:** Implement PT-A02-007 over all observations and PT-A05-064 over non-deletion observations, through the
  same finding helper (sanitiser included).
- [ ] **Step 2:** Run the Task 7 file and `tests/engine/collectors/pentesting`; commit.

## Task 9: Freeze the Cache-Control check and the indeterminate cases (PT-A02-008)

**Commit:** `test: port the BootUI cacheable Set-Cookie check`

**Files:** `tests/engine/collectors/pentesting/test_cache_control.py`, `test_cookie_checks.py` (group 3); stubs
`cache_control.py` (`directive_summary` returns the raw joined text, `parse_cache_control` all-false) and the PT-A02-008
branch of `observed`.

- [ ] **Step 1:** `test_cacheable_set_cookie_distinguishes_public_shared_and_session_max_age`
  (`cacheableSetCookieCheckDistinguishesPublicSharedAndSessionMaxAgeCaching`: `public`, `s-maxage`, positive `max-age`,
  `private`, `no-store`, quoted `private="Set-Cookie"` and `no-cache="Set-Cookie"`, escaped quotes, numeric overflow;
  HIGH, MEDIUM for session names with a positive `max-age`, silent for the safe forms),
  `test_cache_control_evidence_is_rebuilt_from_directives` (`public, x-token=<canary>` and `private="<canary>"` keep the
  finding, name the recognised directives and count the others, and never contain the canary; each directive keeps its
  spelling case-folded; presence assertions first), `test_cache_control_incomplete_does_not_manufacture_a_finding`
  (an over-long `Cache-Control` value: no finding, and both of BootUI's gaps, `GET required response headers were
  incomplete.` and `GET required response headers were unavailable.`, because PT-A02-008 uses `Assessment.headers`,
  not `retainedHeaders`; the same two gaps appear when the response sets no cookie, because BootUI evaluates the header
  requirement before the empty-cookie check, `Checks.java:2652-2653`).
- [ ] **Step 2:** `test_failed_or_rejected_get_leaves_cookie_checks_indeterminate` (failed, timed-out and Host-rejected
  GET: no cookie finding, no pass claim, A10's incomplete finding stands),
  `test_incomplete_set_cookie_inventory_keeps_cookie_result_partial` (retained cookies still evaluated, exactly BootUI's
  gap string, the dropped cookie unnamed), `test_cookie_gaps_are_bootuis_strings_and_deduplicated`.
- [ ] **Step 3:** Run; confirm assertion reds; `red_check.py`; commit.

## Task 10: Implement PT-A02-008, the report text and the coverage

**Commit:** `feat: evaluate the cacheable Set-Cookie check and update the cookie report text`

**Files:** `cache_control.py`, `cookie_checks.py`, `checks.py` (docstring only), `report.py`,
`tests/engine/collectors/pentesting/test_pentesting_report.py`.

- [ ] **Step 1:** Implement `parse_cache_control` (BootUI `parseCacheControl` over `checks._split_outside_quotes`) and
  `directive_summary(values)`: recognised names (`public`, `private`, `no-cache`, `no-store`, `no-transform`,
  `must-revalidate`, `proxy-revalidate`, `must-understand`, `immutable`, `max-age`, `s-maxage`, `stale-while-revalidate`,
  `stale-if-error`) lowercased, a `=digits` argument kept only for the numeric ones and at most 10 digits, other
  directives counted as `N other directive(s)`. PT-A02-008 runs when `assessment.required_headers("GET", get,
  ("cache-control",), gaps)` is available and a non-deletion cookie exists, in BootUI's order: the non-deletion cookies
  are collected first (which can add the `set-cookie` gap), then the `cache-control` requirement is evaluated (both gaps
  when it is incomplete, even with no cookie), then an empty cookie list ends the check; evidence is BootUI's sentence
  with the rebuilt summary and `echo(name)`, through the shared finding helper (sanitiser included).
- [ ] **Step 2:** In `checks.py` extend only the docstring sentence: header and body values are never echoed there, and
  the cookie and CORS evidence, which echo only masked names and origins, lives in `cookie_checks.py` and `cors.py`.
- [ ] **Step 3:** Remove the cookie words from the pending limitation and the A02 description as A11 left them (leave the
  CORS words as merged), and add BootUI's scope suffixes where A11 has not: A02 ends with `Cookie issuance on other
  routes and actual CORS resource responses were not tested.`; A04 ends with `No observed Set-Cookie does not establish
  that the application has no sessions.` (`Registry.java:319-330`). Update the A11 version of
  `test_cors_and_cookie_checks_are_reported_as_pending_not_unavailable` into
  `test_cookie_pending_text_is_replaced_and_no_pending_wording_remains`.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting tests/fastapi/test_pentesting_api.py`;
  commit.

## Task 11: Freeze the session-configuration checks

**Commit:** `test: port the BootUI session cookie configuration checks`

**Files:** `tests/engine/collectors/pentesting/test_session_cookie_config.py`, an addition to
`tests/fastapi/test_introspector_security.py`, `tests/fastapi/test_pentesting_exposure_adapter.py`; stubs
`session_cookie.session_evidence` and `configured`, and `pentesting_exposure.read_security_facts`.

**Interfaces:** `SessionCookieConfig(mount: str | None, https_only_false: bool, same_site_none: bool)`;
`SessionEvidence(configs: tuple[SessionCookieConfig, ...], complete: bool)`; `session_evidence(facts: SecurityFacts |
None) -> SessionEvidence` (`complete` is false when `facts` is `None` or carries any limitation; the text is not read);
`configured(session, gaps, echo) -> list[Finding]`.

**Stubs:** `session_evidence` returns one config with `https_only_false` and `same_site_none` true and `complete` true
for any input; `configured` returns one PT-A02-004 finding with severity `INFO` and evidence `stub` for any input and
records no gap. `read_security_facts` returns an empty `SecurityFacts` for any input (wrong where the tests expect
`None`, and not the object the introspector returned where they expect it).

- [ ] **Step 0:** `test_pentesting_exposure_adapter.py`, with a fake introspector and a run-time canary:
  `test_read_security_facts_returns_the_object_the_introspector_gives` (the presence control: the very `SecurityFacts`
  instance comes back), `test_read_security_facts_returns_none_and_logs_nothing_when_the_reader_raises` (the exception
  message carries the canary; the result is `None`, `caplog.records` is empty, stderr and stdout are empty, and the
  canary is in no captured text; an `Exception` subclass and a `RuntimeError` both covered, `KeyboardInterrupt` is not
  swallowed), `test_read_security_facts_returns_none_when_the_attribute_is_absent` (an introspector without
  `security_facts`, and one where the attribute is not callable), `test_read_security_facts_returns_none_for_a_result_of_the_wrong_type`
  (a dict, a string and `None` returned by the reader). The duck-typed read matches `engine/tools04/security.py:33`.
- [ ] **Step 1:** Port to `SessionMiddleware` options. `# ported: SpringPentestingObservationCollectorTests.metadataChecksStaySilentForSafeConfiguration`
  (`:533-550`) and `# ported: SpringPentestingObservationCollectorTests.metadataChecksFlagAdditionalLowFalsePositiveSpringSettings`
  (`:625-655`). Tests: `test_explicit_https_only_false_is_flagged_and_default_is_not`,
  `test_same_site_none_with_secure_disabled_is_flagged` (also `https_only=True` and `same_site="lax"` silent),
  `test_unreadable_session_options_leave_metadata_checks_indeterminate` (facts `None`, positional options, a non-FastAPI
  app and a limitation whose text carries a mount-path canary: BootUI's gap string, no finding, no pass, canary absent),
  `test_mounted_sub_app_finding_names_the_echoed_mount_path` (the mount path goes through `echo`; under
  `METADATA_ONLY` it reads `[masked]`).
- [ ] **Step 2:** `test_https_only_false_flag_is_read_from_keyword_only` in the introspection tests: a keyword
  `https_only=False` yields the new flag, an absent keyword and `True` do not, and no option value (including
  `secret_key`) appears in the facts.
- [ ] **Step 3:** Run the three files; confirm assertion reds; `red_check.py`; commit.

## Task 12: Implement the metadata checks and wire the scan

**Commit:** `feat: evaluate session cookie configuration in the pentesting scan`

**Files:** `introspection_security.py`, `session_cookie.py`, `report.py`, `service.py`, `fastapi/pentesting_exposure.py`,
`fastapi/routes/pentesting.py`.

- [ ] **Step 1:** In `_session_flags` add `https_only_false` when the keyword is present and `is False`; existing flags
  keep their behaviour, so the Security panel rules are unchanged.
- [ ] **Step 2:** Implement `session_evidence` and `configured`: PT-A02-004 for each `https_only_false`; PT-A02-006 for
  each config with `same_site_none` and `https_only_false`; BootUI titles, severities (LOW; MEDIUM), confidence (Medium;
  High) and categories (A04; A02); target, evidence and recommendation name the `SessionMiddleware` option and the
  echoed mount path, never an option value. When `complete` is false, append `Framework configuration evidence was
  incomplete.` (`Assessment.java:41-44`), which makes the scan PARTIAL without a finding.
- [ ] **Step 3:** Add `read_security_facts(introspector)` to `pentesting_exposure.py` with A13's name, signature and
  module: one `security_facts()` read through the duck-typed attribute used by `engine/tools04/security.py:33`, wrapped
  in `except Exception` with no logging and no message copied, `None` on failure, on absence of the attribute and on a
  result that is not a `SecurityFacts` instance. The Task 11 Step 0 tests turn green. The scan function calls it once and
  passes `session_evidence(facts)` to `service.scan`. The action and its gates are unchanged; no read path calls it.
- [ ] **Step 4:** Run the Task 11 files (including `tests/fastapi/test_pentesting_exposure_adapter.py`), `tests/engine/collectors/pentesting`, `tests/fastapi/test_pentesting_api.py` and
  `tests/fastapi/test_introspector_security.py`; commit.

## Task 13: Prove the hidden surfaces, the gates and the controls

**Commit:** `test: assert no cookie value on any hidden pentesting surface`

**Files:** `tests/fastapi/test_pentesting_cookie_hidden_surfaces.py`, `tests/engine/collectors/pentesting/test_pentesting_report.py`.

These cases are absence-only, so their red evidence is a control-deletion run: apply each wrong-value mutation below in
the working tree, run `red_check.py` on the named tests in the mutated tree, restore the file with `git checkout --
<path>`, and record the test names in the commit body.

- [ ] **Step 1:** `test_planted_cookie_value_is_absent_from_every_hidden_surface`: with the Task 3 host, one case each
  for error bodies (409 and 504 paths), captured log records (`caplog`, stderr) and every file under
  `SHARPIT_STATE_DIR`, in all three exposures. `test_probe_exchange_and_trace_records_are_free_of_the_canary`: a positive
  control first (the probe exchange is recorded), then no canary in the exchange and trace records at `MASKED` and
  `METADATA_ONLY`; `FULL` is the stated exception of Global Constraints (`mask_header` shows values there by design
  for all captured traffic), pinned by `test_full_exposure_capture_records_the_probe_exchange_like_any_other` (the
  probe exchange is recorded and the capture record equals what `mask_header` gives for the same headers in `FULL`),
  so the exception is a tested fact and a change of it fails a test. The same test file asserts, in `FULL`, that every
  scan-produced surface (the report, MCP and CLI output, error bodies, logs, state files) holds no canary.
- [ ] **Step 2:** `test_cookie_checks_are_scan_action_only_and_read_only_denied`: GET and read tools make no host call,
  open no socket (`no_side_effects`) and never call `security_facts`; a read-only panel, a disabled panel, MCP off,
  an inactive console and a cross-site scan refuse before any host call; `test_one_scan_reads_security_facts_once`.
- [ ] **Step 3:** `test_limitations_added_by_this_lane_survive_the_cut`: build the worst-case scan (A10's fixed lines,
  A11's, and this lane's two gaps) and assert each of this lane's strings is present after `_unique_limitations`, not
  only that the count is at most 20.
- [ ] **Step 4:** Mutations, each failing a named test: M1 the parser returns the raw first segment as the name; M2
  `split_cookies` returns the headers unchanged; M3 the `echo` is skipped on a cookie name; M4 `directive_summary`
  returns the raw text; M5 `observed` reads the middleware facts in a read path; M6 the per-name incompleteness is
  dropped; M7 `session_evidence` copies the limitation text; M8 the finding helper skips `sanitize_evidence`; M9
  `read_security_facts` lets the reader's exception, or its message in a log record, escape; M10 `boundedLabel` uses
  Python `\s`. Record each test name; restore.
- [ ] **Step 5:** Run `uv run pytest -q -n 4` on the two files; `red_check.py` per mutation; commit.

## Task 14: Contract fixtures, parity and documentation

**Commit:** `docs: document the cookie and session checks of the pentesting scan`

**Files:** `tests/fixtures/bootui/2.5.0/pentesting/*`, `tests/engine/collectors/pentesting/test_pentesting_report.py`,
`docs/reference/matrix-updates/0.8.0-a12.tsv`, `0.8.0-a10.tsv` (remove the `pentesting:cookie-pending` row only),
`docs/reference/PARITY.md`, design spec section 14, user documentation.

- [ ] **Step 1:** Extend the rule-contract projection with the nine checks (`test_cookie_rules_follow_registry_order_and_bootui_contract`)
  and the hand-derived ASGI golden with a cookie-setting response using fake non-secret values.
- [ ] **Step 2:** Write the deviation rows above to `0.8.0-a12.tsv`, mirror them in spec section 14, update the
  pentesting row of `PARITY.md`, and describe in the user documentation what the cookie checks observe (one GET, names
  and flags only, in-process ASGI evidence, no TLS edge), what the configuration checks read, and that under `FULL` the
  capture panel shows the probe's cookie as it shows any host response.
- [ ] **Step 3:** Run the lane tests (`uv run pytest -q -n 4 tests/engine/collectors/pentesting tests/fastapi/test_pentesting_api.py tests/fastapi/test_pentesting_probe.py tests/fastapi/test_pentesting_cookie_probe.py tests/fastapi/test_pentesting_cookie_surfaces.py tests/fastapi/test_pentesting_cookie_hidden_surfaces.py tests/fastapi/test_pentesting_exposure_adapter.py tests/fastapi/test_introspector_security.py tests/engine/collectors/security/test_rules_transport.py tests/engine/test_import_boundary.py tests/parity`),
  `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`; report counts. Commit with explicit paths and
  `git commit -s`.

## Definition of done

- [ ] Every Critical and High scenario row has a named passing test; every output surface of the scan has a
  planted-value case in `MASKED`, `METADATA_ONLY` and `FULL`, capture records in `MASKED` and `METADATA_ONLY` with the
  `FULL` exception pinned; each control was proven by mutation.
- [ ] Every finding of this lane passes through the shared `echo.sanitize_evidence`; `echo.py` is created by this lane's
  Task 0 and A13 reuses it.
- [ ] The seven observed checks and two metadata checks match the BootUI v2.5.0 IDs, titles, severities, confidence,
  categories and order, with observed and configuration evidence kept separate.
- [ ] Failure, rejection, truncation and unreadable configuration never read as a clean result, and the gap strings
  are BootUI's.
- [ ] The cookie pending text and matrix row are replaced; the CORS wording is as A11 merged it.
- [ ] Lane tests, ruff and pyright pass; live verification states that evidence is ASGI-only, one GET, names and flags
  only.
