# A13 Framework-Exposure Pentesting Checks Implementation Plan

> Run `/sharpit:status --feature a13-framework-exposure-checks` for the next unchecked step. Complete one task at a time and run `/sharpit:check` before each commit.

**Goal:** Add the BootUI v2.5.0 framework-exposure checks that have a FastAPI/Starlette equivalent (PT-A05-041 documentation or developer console exposed, PT-A05-044 forwarded headers trusted) to the explicitly invoked pentesting scan, and record every other framework-metadata check as not applicable, adapted elsewhere or owned by another lane, by explicit id and with its reason.

**Scope:** FastAPI/Starlette only. The pentesting scan as a whole (route, MCP tool, CLI command, probe) is wired to the FastAPI adapter; the Flask adapter has none of it, so Flask rows are `pending`.

**Architecture:** The framework-free pentesting engine gains one value object (`FrameworkEvidence`) and the two rules that evaluate it. The FastAPI adapter builds that evidence from the application's own route table and middleware facts by attribute reads, as the Security and Routes panels already do; nothing is called and no request is sent. The scan action (the same function that serves the route, MCP and CLI) reads `routes()` once and `security_facts()` once, shares the facts read with A12, and builds the evidence; GET report reads never do. Unreadable, unrecognised or truncated evidence is reported as a gap and makes the scan partial, never a clean result. Masking follows A11's fragment rule: `PentestingService.scan` receives the required keyword-only `masker`, builds `echo = make_echo(masker)`, and the rules pass only the host-chosen fragments (documentation route paths and mount paths) through `echo`, before the evidence is sanitised and cut at 240 characters. Fixed BootUI text, gaps and limitations are never masked. `echo`, `make_echo` and the evidence sanitiser live in one shared module, `engine/collectors/pentesting/echo.py`, created by A12's first task (a move out of `cors.py`) and imported by the CORS rules, the cookie rules and this lane.

**Tech Stack:** Python 3.12+, existing `RouteInfo` and `SecurityFacts` introspection, pytest, BootUI-derived fixtures.

**Review gate:** Complete the required high-tier review of this plan and record its disposition before implementation begins.

## Review dispositions

The high-tier review approved the plan with changes in two rounds. Every change is applied and listed below; implementation may begin once the plan is merged.

### Round 2

Each condition was checked against BootUI v2.5.0 and the code before it was applied.

| Condition | Verified against | Applied as |
|---|---|---|
| Masking follows A11's fragment rule, not a result-level pass | A11 plan (`76be6723`): `cors.evaluate(get, options, echo)`, `make_echo(masker)`, fixed text never masked. `Masker.mask_text` returns `None` under `METADATA_ONLY` (`masking.py:460-466`). A whole-string pass would also rewrite BootUI's fixed text | `evaluate(evidence, echo)` with `echo` required; Decision 8; Task 3 |
| `echo` and the sanitiser in one shared module | A11 builds both in `cors.py`; a private import from `cors.py` would couple two lanes | `echo.py`, created by A12's Task 0 as a move out of `cors.py` (A12 merges first and needs the sanitiser for every cookie finding); A13 has no move of its own and only imports it |
| Evidence is sanitised and bounded | BootUI `PentestingCheckSupport.evidence`: CR, LF and TAB runs to one space, trim, 240 characters with `...` (`:51-63`); `checks.finding` does neither (`checks.py:73-86`) | The sanitiser runs after `echo`, on the whole evidence string; the shared module is A12's Task 0, this lane applies it in Task 3 |
| Order before `echo` | BootUI sorts the raw markers (`PentestingChecks.java:2286-2288`) | Raw paths are sorted and de-duplicated, then echoed one by one, so `[masked]` placeholders keep the count and the order |
| Masking tests in all three exposures, including PT-A05-044's mount | `Masker` redacts a JWT-shaped or `key=` segment under `MASKED`, returns `None` under `METADATA_ONLY`, leaves `FULL` unchanged | Task 2 Step 4 and a per-rule recording-echo test in Task 3 |
| One A07 deviation row | BootUI's hand-off branch precedes the indeterminate branch (`PentestingCheckRegistry.java:279-288`); its A07 definition carries the hand-off text (`:164-175`) and its truncation test has Spring metadata present (`PentestingScannerTests.java:754-779`) | Row `pentesting:exposure-coverage-a07`: sharpit labels the branch NOT_APPLICABLE where BootUI says HANDOFF; the behaviour is ported and the ported assertion changes |
| Where gaps land, what `usable` does, the limitation cap | BootUI puts gaps in `scan.message` and, with assessment gaps, in `evidence.limitations` (`PentestingScanner.java:132-148, 241-292`); `usable` ORs per-check usability (`:124-129`). Sharpit's message is fixed text and `usable` is the GET probe (`report.py:272`); `_unique_limitations` keeps 20 entries of 240 characters (`report.py:413-414`) | Decision 9, row `pentesting:exposure-gap-placement`, worst-case cap test in Task 5 |
| Opaque mounts | The facts walk descends only into Starlette sub-applications (`introspector.py:878-884`); anything else is not inspected | A standing limitation in `standing_limitations`, always emitted, with a test; Decision 10 |
| Neither lane copies `SecurityFacts.limitations` | That text carries mount labels and route paths (`introspector.py:410, 878-884`) and limitations are unmasked. A12's revised plan already uses BootUI's fixed gap sentence and reads only whether the facts carry a limitation (a boolean), never the text | Decision 6 widened; Task 4 and Task 5 pin it with a planted path against A12's merged code |
| `adapted-elsewhere` against the matrix statuses | The matrix uses `adapted`, `n-a`, `pending` and others; there is no `adapted-elsewhere` status | Task 1 states the mapping as a constant and tests it |
| Stubs for the `echo` parameter | Every `test:` task must be red on the assertion that names the defect | Stub rules in Global Constraints, Task 2 and Task 3 |

### Round 1

| Change | Applied as |
|---|---|
| Decision 1 rationale | Decision 1 states the real grounds (id contract, disjoint advisors, differing triggers, no pytest gate) |
| 38-id ledger | Explicit ids everywhere, no ranges; retired PT-A05-030 and PT-A05-031 are asserted absent; PT-A05-029 has its own row |
| PT-A07-006 and PT-A07-007 | PT-A07-006 is adapted elsewhere (security advisor OAuth rules); PT-A07-007 is n-a because the flow type is not captured |
| Coverage rule | Port BootUI's precedence exactly: A02 INDETERMINATE on truncation, A07 stays NOT_APPLICABLE (hand-off branch first), A04 and A10 unchanged |
| Completeness | Failure is a gap; a non-FastAPI host is the absent-provider case; `security_facts().limitations` is neither copied nor counted |
| ReDoc | ReDoc is reported from the route table; no configured-ReDoc claim, no port change |
| Masking | Planted-secret tests cover docs and mount paths on every surface (the wiring itself is revised in round 2: fragment-level `echo`) |
| Host cost | One `security_facts()` read and one `routes()` read per scan, shared with A12, wrapped in `except Exception`; scale test above 4096 routes |
| Proxy matching | Simple name plus module, with lookalike tests |
| PT-A05-051 and PT-A05-040 | Reasons restated; PT-A05-040 is n-a with nothing deferred |
| Flask | Pending row; the scan as a whole is FastAPI-only |
| Contract text | Tool descriptions and `cli/tools.json` are not edited |

## Decisions

1. PT-A05-041 and PT-A05-044 are emitted as pentesting findings with BootUI's ids, because the ids are BootUI's report, ordering (`PentestingCheckRegistry.java:35-105`) and dismissal contract. BootUI's Spring advisor has no equivalent rule (`SecurityRules.java` mentions forwarded headers only in TLS text), so there is no BootUI pairing to copy; the pair exists only in its Quarkus advisor. `SEC-FAPI-002` and `SEC-FAPI-003` are sharpit rules with different triggers (secured routes; `trusted_hosts="*"`), the two advisors are disjoint (`registry.py:76-82`) so no panel shows both, and pentesting has no pytest gate (`assess=None`). The security rules are not changed and a test pins their ownership. This overrules the earlier recommendation to reuse the advisor rules instead of adding pentesting findings.
2. The documentation routes are identified by the registered handler (module and qualified name), not by path and not by the configured URL attributes (see the scenario's worst-case trace). The path is only what the finding reports. ReDoc is found the same way, as a registered route; no configured ReDoc URL is read.
3. Evidence exists only in the scan action. A report read returns the cached or initial report and calls none of `routes()`, `app_info()` or `security_facts()`.
4. Coverage follows BootUI's precedence (finding, hand-off or not-applicable, then indeterminate; `PentestingCheckRegistry.java:270-286`). Endpoint truncation or unreadable evidence sets `partial`, which makes A02 INDETERMINATE through the rule A11 ports. A07 is not made indeterminate: BootUI's A07 hand-off branch (`PentestingCheckRegistry.java:164-175, 279-281`) precedes its indeterminate branch (`:285-288`) on an adapter without Spring metadata, and sharpit's A07 is that branch. The behaviour is ported; two things differ and are one deviation row, `pentesting:exposure-coverage-a07`: sharpit's label is NOT_APPLICABLE where BootUI's is HANDOFF, and the ported truncation assertion (`PentestingScannerTests.java:754-779`, which runs with Spring metadata present and so asserts INDETERMINATE) becomes NOT_APPLICABLE. A test pins A07, A04 and A10 unchanged.
5. A non-FastAPI host is BootUI's absent-provider case: documentation is evaluated from the route table, PT-A05-044 is not evaluated, a standing limitation says so, and there is no gap. A missing method or an exception is BootUI's failure case: gap, PARTIAL, A02 INDETERMINATE.
6. `security_facts()` is read once per scan, by `read_security_facts` in `fastapi/pentesting_exposure.py`, which A12 creates (its own red-first tests cover the raising, absent and wrong-type cases) and this lane extends; the helper wraps the call in `except Exception` and degrades to "unavailable". A12 and A13 consume that one read. `SecurityFacts.limitations` text is never copied by any lane: it can carry route paths and mount labels (`introspector.py:410, 878-884`) and limitations are not masked. A12 uses only whether the list is empty (a boolean behind BootUI's fixed configuration gap), and this lane neither copies nor counts them. A13 never puts that text in the report; a planted-path test pins it against A12's merged code.
7. The middleware match requires the simple name `ProxyHeadersMiddleware` (the advisor's `simple()` helper) and the module `uvicorn.middleware.proxy_headers`; Starlette ships no such class.
8. Masking is A11's fragment rule. `evaluate(evidence, echo)` takes `echo` as a required argument (no identity default, so a caller cannot forget it). Each rule sorts and de-duplicates the raw documentation or mount paths first, then passes each one through `echo`, joins them into BootUI's evidence text, and sanitises the whole string (CR, LF and TAB runs to one space, trim, 240 characters with `...`). Under `METADATA_ONLY`, `echo` returns `[masked]` per path, so the count and order survive. The middleware class name is matched exactly (simple name plus module) and is fixed text, never echoed. Gaps and limitations are fixed strings and are not masked. Deviation row `pentesting:exposure-masking` records that BootUI masks nothing here.
9. Gaps land in `evidence.limitations`, with BootUI's gap wording (`PentestingScanner.java:260-262`), placed before the generic trailing sentences; the scan `message` stays the fixed text of A10 (BootUI appends the gaps to its message, `:288-291`; row `pentesting:exposure-gap-placement`). `usable` is unchanged: it stays the GET probe's usability (`report.py:272`), so unavailable route evidence neither raises nor lowers it. `coverageComplete` stays False as A10 sets it. The limitation list keeps 20 entries of 240 characters (`report.py:413-414`); A13 adds at most three gap entries and three standing sentences, each at most 240 characters, and a worst-case test proves they survive the cap with every lane's maximal limitations present.
10. Mounted applications that are not Starlette applications (a WSGI app, a metrics ASGI app) are not inspected. This is a standing limitation, emitted on every scan that supplies route evidence, because the evidence cannot tell that such a mount exists. It is a limitation, not a gap: it does not make the scan partial.

## Global Constraints

- Reads have no side effects: no GET route and no read MCP or CLI tool builds the evidence, opens a socket, writes a file, changes a logger level or changes `os.environ`. The evidence is built by attribute reads inside the action; no host endpoint is called.
- Actions keep A10's gates: enablement, guard, enabled panel, non-read-only, single-flight.
- Route and mount paths reach output only through `echo`, built by `make_echo(masker)` from the required `masker` of `PentestingService.scan` (A11's wiring); no raw host value other than a masked path or the fixed middleware class name is returned, and `SecurityFacts.limitations` text is never copied into the report. This lane adds no second masker, defines no echo or sanitiser of its own (a test pins that), and does not import `Masker` through `collectors/security`. Tests prove it in `MASKED`, `METADATA_ONLY` and `FULL` with the real `Masker`.
- No claim of authorization or reachability: the evidence says the route is registered, nothing more.
- A failure, an unrecognised shape, or a truncated inventory is indeterminate and stated, never a clean result.
- `engine/` imports no `fastapi` or `starlette`; the adapter owns the handler names and the middleware module name.
- Every ported test cites its BootUI source with `# ported: <Class>.<method>`.
- Tool descriptions and `cli/tools.json` are contract text and are not edited.
- No module under `src/` exceeds 1000 lines; ratchets only go down.
- Every `test:` task is red against a wrong-value stub: the stub returns plausible wrong values so each test fails on the assertion that names the defect, never on an import error. Every stub of a function that gains the `echo` parameter has the final signature (`evaluate(evidence, echo)`), so a test never fails with a `TypeError` on the call. The masking stub returns BootUI's text with the raw sorted paths, calls `echo` never and sanitises nothing, so the planted-secret, `METADATA_ONLY`, recording-echo and sanitiser tests fail on their own assertions. Each task lists its stub and the red reason per test.
- Every pytest command in this plan is targeted and parallel: `uv run pytest -q -n 4 <files>`. The full suite is not run locally.

## Merge order and conflicts

This lane builds on the A10 probe and report. It lands after A11 (CORS) and A12 (cookies and session), which also edit `report.py`, `service.py`, `routes/pentesting.py` and the shared limitation sentences. A11 adds the required keyword-only `masker` argument to `PentestingService.scan` and builds `echo = make_echo(masker)` for the host-echoed fragments of its own evidence (it does not mask whole strings, limitations or gaps), with `make_echo` and the sanitiser in `cors.py`; A12's Task 0 moves them to `echo.py` (this lane has no such task and imports the module). A12 adds a `session` keyword to `scanned_report` and `PentestingService.scan`, creates `fastapi/pentesting_exposure.py` with `read_security_facts` and reads `security_facts()` once in the scan function through it; this lane extends that module with `framework_evidence`, reuses the one read, and adds an `exposure` keyword beside `session`. A12's plan does not copy `SecurityFacts.limitations` text: it records BootUI's fixed configuration gap when the facts are absent or carry any limitation. This lane's pin test (Task 5) proves that against A12's merged code. Each lane keeps its own matrix fragment. Resolve overlaps by merging the earlier lane in, and edit only the words of the shared limitation sentence that concern route and middleware checks.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A host-chosen documentation or mount path carries a secret into evidence, MCP or CLI output | `echo` from A11's `make_echo`, applied to every path before the sanitiser; planted-secret tests on route, MCP, CLI and cached GET in `MASKED`, `METADATA_ONLY` and `FULL`, with a non-secret control; a per-rule recording-echo test. |
| Critical | `SecurityFacts.limitations` text (mount labels, route paths) is copied into the unmasked limitations | Never copied by A13; A12 records a fixed gap sentence and no limitation text; planted-path pin. |
| High | A13's gaps and standing sentences are dropped by the 20-entry limitation cap | Placed before the trailing sentences, at most six entries of at most 240 characters; worst-case cap test. |
| Critical | A report read builds evidence or touches the host | Evidence only in the scan action; call-count and `no_side_effects` tests on GET, MCP and CLI reads covering `routes()`, `app_info()` and `security_facts()`. |
| High | Configured URL attributes flag an app that serves no documentation | Match registered handlers; worst-case trace test. |
| High | FastAPI renames its documentation handlers and the check goes silent | Declared-but-unrecognised becomes a stated gap; a test pins the installed handler names, and the lowest-direct CI leg runs it. |
| High | Introspection failure reads as "no exposure" | `available` and `truncated` map to gaps, PARTIAL and A02 INDETERMINATE; an exception degrades the same way. |
| High | The facts walk runs twice on the host loop (A12 and A13) | One `security_facts()` read per scan; call-count test and a more-than-4096-route scale test. |
| High | A lookalike class name triggers PT-A05-044 | Simple name plus module match; lookalike tests. |
| Medium | Duplicate or contradictory findings with the security advisor | Distinct ids, no shared code, advisor rules unchanged and pinned. |
| Medium | Merge conflicts with A11 and A12 in `report.py` | Section above; own module and matrix file. |

## File map

- `src/sharpit/engine/collectors/pentesting/echo.py` (created by A12's Task 0, one shared home; not edited here): `make_echo(masker)` (mask one host fragment; `[masked]` when `mask_text` returns `None`) and `sanitize_evidence(text)` (CR, LF and TAB runs to one space, Java trim, 240 characters with `...`). Created by A12's Task 0 (a move out of `cors.py`, A12 merging first); this lane only imports it.
- `src/sharpit/engine/collectors/pentesting/framework_exposure.py` (new): `FrameworkEvidence`, the two rules (`evaluate(evidence, echo)`), the gap messages, the standing limitations, the inspection bound. Imports `echo.sanitize_evidence` and defines neither.
- `src/sharpit/engine/collectors/pentesting/report.py`: accept `exposure`, add its findings, gaps and standing limitations before the trailing sentences, set `partial` on an incomplete inventory, update the limitation sentence.
- `src/sharpit/engine/collectors/pentesting/service.py`: pass `exposure` through `scan` and the `echo` it already builds from A11's required `masker`.
- `src/sharpit/fastapi/pentesting_exposure.py` (created by A12, extended here): adds `framework_evidence`, and owns the handler names and the middleware module name. `read_security_facts`, the one-read helper, is A12's and is not redefined.
- `src/sharpit/fastapi/routes/pentesting.py`: the scan function reads the facts once, builds the evidence and passes both on.
- `tests/engine/collectors/pentesting/test_framework_exposure_ledger.py`, `test_framework_exposure.py` (new); `test_evidence_echo.py` is A12's.
- `tests/fastapi/test_pentesting_exposure_api.py` (new); `tests/fastapi/test_pentesting_exposure_adapter.py` (created by A12 with the `read_security_facts` cases, extended here with the `framework_evidence` cases).
- `tests/fixtures/bootui/2.5.0/pentesting/framework-exposure.json` (new): the ledger and the BootUI projection of the two implemented rules. Separate from the hand-derived ASGI transport golden.
- `docs/reference/matrix-updates/0.8.0-a13.tsv` (new), `docs/reference/PARITY.md`, `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` section 14.

## The 38 framework-evidence ids (ledger)

Implemented: PT-A05-041, PT-A05-044. Other lane (A12): PT-A02-004, PT-A02-006. Adapted elsewhere: PT-A07-006. n-a, Actuator (19): PT-A05-016, PT-A05-019, PT-A05-027, PT-A05-028, PT-A05-032, PT-A05-033, PT-A05-034, PT-A05-035, PT-A05-036, PT-A05-037, PT-A05-038, PT-A05-039, PT-A05-040, PT-A05-049, PT-A05-052, PT-A05-053, PT-A05-054, PT-A05-055, PT-A05-056. n-a, others: PT-A05-029, PT-A05-017, PT-A05-051, PT-A05-062, PT-A05-042, PT-A05-043, PT-A07-001, PT-A07-002, PT-A07-003, PT-A07-004, PT-A07-005, PT-A01-001, PT-A07-007, PT-A08-001. Retired and absent from the ledger: PT-A05-030, PT-A05-031. Total 38.

Ledger dispositions map to matrix statuses, because the matrix has no `adapted-elsewhere` status (its statuses include `adapted`, `n-a` and `pending`): `n-a` maps to `n-a`; `adapted-elsewhere` (PT-A07-006) maps to an `adapted` row; `implemented` (PT-A05-041, PT-A05-044) maps to the `adapted` rows `exposure-docs-source`, `exposure-docs-text` and `exposure-proxy`; `other-lane` (PT-A02-004, PT-A02-006) has no row in this fragment and is owned by A12's fragment. Task 1 holds the mapping as a constant, `LEDGER_TO_MATRIX_STATUS`, and tests it.

## Deviation rows (recorded in `0.8.0-a13.tsv`)

| Key | Status | Deviation | Reason |
|---|---|---|---|
| `pentesting:exposure-docs-source` | adapted | PT-A05-041 matches the registered OpenAPI, Swagger UI and ReDoc handlers, and reports their route paths, instead of BootUI's fixed prefix list `/v3/api-docs`, `/v2/api-docs`, `/swagger-ui`, `/graphiql` | The Java prefixes name Spring libraries; paths are configurable in FastAPI, so the handler is the stable fact |
| `pentesting:exposure-graphiql` | n-a | GraphiQL marker dropped | A GraphQL library serves its IDE and its API on one route; the route table cannot distinguish them |
| `pentesting:exposure-docs-text` | adapted | PT-A05-041 recommendation and learn-more link name FastAPI's conditional OpenAPI guidance and omit the H2 sentence; id, title, category, severity and confidence are BootUI's | The H2 console has no Python equivalent |
| `pentesting:exposure-proxy` | adapted | PT-A05-044 evaluates `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware` on the application stack instead of `server.forward-headers-strategy`; title, target, evidence, recommendation and link are Python-specific; id, category, severity and confidence are BootUI's | The Spring property does not exist; uvicorn's server flags are not observable and are stated as a limitation |
| `pentesting:exposure-unavailable` | adapted | An exception or a missing introspector method is a gap, a partial scan and A02 INDETERMINATE; a non-FastAPI host is evaluated for documentation only, with PT-A05-044 reported as not evaluated in a standing limitation and no gap | BootUI's failed provider is truncated and its absent provider is silent; FastAPI internals vary by version, so a failure must not read as a clean result |
| `pentesting:exposure-masking` | adapted | Documentation route paths and mount paths in PT-A05-041 and PT-A05-044 evidence pass through the context masker one by one before the 240-character cut and become `[masked]` under `METADATA_ONLY`; BootUI masks nothing here. Fixed text is never masked. Same rule as `pentesting:cors-evidence-masking` | Safety model item 3: secrets are masked before any output |
| `pentesting:exposure-coverage-a07` | adapted | Sharpit labels A07 coverage NOT_APPLICABLE where BootUI labels the same branch HANDOFF; the behaviour is ported (the hand-off branch precedes the indeterminate branch), so endpoint truncation leaves A07 unchanged and the ported assertion of `PentestingScannerTests.java:754-779` changes from INDETERMINATE to NOT_APPLICABLE | The BootUI test runs with Spring metadata present; sharpit has none, so its A07 is the hand-off branch |
| `pentesting:exposure-gap-placement` | adapted | Gaps are entries of `evidence.limitations` with BootUI's wording; the scan message stays fixed text and `usable` stays the GET probe's usability | BootUI appends gaps to its scan message and ORs per-check usability; sharpit's message and `usable` are A10's |
| `pentesting:exposure-bound` | adapted | The 4096-pattern inspection bound and its gap text are BootUI's; the 64-handler-mapping bound has no analogue | Starlette has one route tree, not a list of handler mappings |
| `pentesting:exposure-html-mappings` | n-a | `htmlMappingsPresent` is not ported | It only gates BootUI's Spring whitelabel 404 exclusion, which A10 does not apply (`pentesting:browser-document`) |
| `pentesting:exposure-actuator` | n-a | PT-A05-016, PT-A05-019, PT-A05-027, PT-A05-028, PT-A05-032, PT-A05-033, PT-A05-034, PT-A05-035, PT-A05-036, PT-A05-037, PT-A05-038, PT-A05-039, PT-A05-049, PT-A05-052, PT-A05-053, PT-A05-054, PT-A05-055, PT-A05-056 | No management-endpoint model in FastAPI/Starlette |
| `pentesting:exposure-prometheus` | n-a | PT-A05-040 | BootUI binds it to the Actuator base path; a `prometheus_client` ASGI app is an opaque mount at a host-chosen path, not a framework convention |
| `pentesting:exposure-h2` | n-a | PT-A05-017 | No embedded database console |
| `pentesting:exposure-actuator-cors` | n-a | PT-A05-029 | Spring property; generic CORS is A11 |
| `pentesting:exposure-request-logging` | n-a | PT-A05-051 | No application-level request-detail logging toggle; server logging verbosity is outside the app object and a logger level is process-global state a read must not change |
| `pentesting:exposure-devtools` | n-a | PT-A05-062 | No remote-restart secret; the Werkzeug debugger is not visible on the app object |
| `pentesting:exposure-firewall` | n-a | PT-A05-042 | Starlette has no request firewall |
| `pentesting:exposure-management-port` | n-a | PT-A05-043 | No separate management port |
| `pentesting:exposure-spring-security` | n-a | PT-A07-001, PT-A07-002, PT-A07-003, PT-A07-004, PT-A07-005, PT-A01-001 | Spring Security is not ported |
| `pentesting:exposure-oauth2-issuer` | adapted | PT-A07-006 is covered by the security advisor's `SEC-OAUTH-004` and `SEC-OAUTH-006`, which exempt loopback hosts and are production-only; BootUI flags any `http://` issuer | The scheme-URL facts already exist in the security advisor; no pentesting finding is added |
| `pentesting:exposure-oauth2-grant` | n-a | PT-A07-007 | The OAuth2 flow type is not captured by the introspector |
| `pentesting:exposure-jvm` | n-a | PT-A08-001 | JVM serialization |
| `pentesting:exposure-flask` | pending | Flask documentation routes and the Werkzeug debugger | The pentesting scan as a whole is wired to the FastAPI adapter only |

### Task 0: removed

The shared module `echo.py` (`make_echo`, `sanitize_evidence`) is created by A12's Task 0, a move out of `cors.py`, because A12 merges first and needs the sanitiser for its cookie findings. This lane has no move and imports the module. The no-second-home pin that Task 0 carried is Task 3 Step 1 below.

### Task 1: Freeze the ledger and the report statements

**Commit:** `test: freeze the framework-exposure ledger and report statements`

**Files:** `tests/fixtures/bootui/2.5.0/pentesting/framework-exposure.json`, `tests/engine/collectors/pentesting/test_framework_exposure_ledger.py`.

**Interfaces:** The fixture is the ledger consumed by Tasks 3 and 6. The ledger checker is a pure function inside the test module, `partition_problems(entries, registry_ids, retired_ids) -> list[str]`.

**Stub for the red run:** none is needed in `src/`; the reds are an absent matrix fragment and an absent limitation. The ledger checker is proved by planted controls instead of by a stub.

- [ ] **Step 1:** Create the fixture from `PentestingChecks.java`: the 38 `SPRING_METADATA` ids listed above, each with its disposition (`implemented`, `other-lane`, `adapted-elsewhere` or `n-a`), its BootUI source range and, for the last two, the reason; for PT-A05-041 and PT-A05-044 the BootUI id, title, OWASP category, severity, confidence and the registry position from `PentestingCheckRegistry.java:35-105`.
- [ ] **Step 2:** Add `test_framework_exposure_ledger_partitions_the_bootui_metadata_checks` (every one of the 38 ids appears exactly once, all exist in `rule-ids.json`, none is retired). Cite `# ported: PentestingScannerTests.registryDefinesUniquePentestingIds` (`PentestingScannerTests.java:817`). Add its controls, each of which must fail the checker: `test_ledger_checker_reports_a_planted_duplicate`, `test_ledger_checker_reports_a_planted_missing_id`, `test_ledger_checker_reports_a_retired_id` (PT-A05-030 and PT-A05-031 planted). The ledger test is a data guard and is green on arrival; the controls are what prove the guard can fail.
- [ ] **Step 3:** Add `test_matrix_fragment_accounts_for_every_not_applicable_id`: `assert path.is_file()` for `docs/reference/matrix-updates/0.8.0-a13.tsv`, then, with `LEDGER_TO_MATRIX_STATUS = {"n-a": "n-a", "adapted-elsewhere": "adapted", "implemented": "adapted"}`, every ledger id whose disposition is a key appears in a row of the mapped status; `other-lane` ids are not asserted here. Add `test_matrix_fragment_records_the_round_two_deviation_rows`: the rows `pentesting:exposure-masking`, `pentesting:exposure-coverage-a07` and `pentesting:exposure-gap-placement` exist with status `adapted`, each once.
- [ ] **Step 4:** Add `test_scan_without_route_evidence_states_the_route_checks_were_not_evaluated`: `scanned_report(get, options)` (no evidence) contains no PT-A05-041 or PT-A05-044 finding and a limitation naming both ids and saying no route evidence was supplied.
- [ ] **Step 5:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_framework_exposure_ledger.py` and `uv run python scripts/dev/red_check.py <node ids of steps 3 and 4>` (Step 3 adds two reds: the missing fragment and the missing rows). The red must be the assertions (missing fragment, missing limitation), not an import error. Commit with explicit `git add` and `git commit -s`.

### Task 2: Port the BootUI cases through the scan action

**Commit:** `test: port BootUI developer-tooling and forwarded-header cases`

**Files:** `tests/fastapi/test_pentesting_exposure_api.py`, the stubs below.

**Interfaces and stubs:** Stubs carry a comment naming Task 3 or Task 4. `framework_exposure.evaluate(evidence, echo)` has its final signature and returns a plausible wrong value: both findings always present, with BootUI's text built from the raw sorted paths, `echo` never called and nothing sanitised (the masking stub of Global Constraints); `gaps` returns `[]` and `standing_limitations` returns `[]`; `pentesting_exposure.framework_evidence` returns available evidence with no routes and no proxy and ignores the app; `read_security_facts` returns `None` without calling the introspector; the scan function passes `exposure` through but not through any wrong path. These make the tests drive the existing `POST` scan route on real FastAPI apps and fail on assertions.

| Test | Red against the stub because |
|---|---|
| default app reports developer tooling | the stub ignores the evidence's routes (it lists none), so the path list in the BootUI text is wrong |
| openapi-disabled app, user route named docs, custom docs url without redirect | the stub emits PT-A05-041 where none is expected, or lists the wrong paths |
| mounted sub-app documentation | `/v1/...` paths absent |
| proxy middleware reported or silent | the stub emits PT-A05-044 for an app without it, and its evidence names no middleware |
| lookalike proxy middleware | the stub emits PT-A05-044 |
| masking tests, `MASKED` | the stub puts the raw canary path into the evidence, so "canary absent" fails |
| masking tests, `METADATA_ONLY` | the stub shows raw paths where `[masked]` is expected |
| masking tests, `FULL` | the verbatim-path assertion is a control and is green against the stub by design; the same test's 240-character assertion on a long path list is the red, because the stub cuts nothing |
| docs path and mount path with a secret, PT-A05-044 mount evidence | the stub's mount evidence carries the raw mount path |
| dismissal | the stub's wrong evidence fails the ported dismissal assertion on content |
| unavailable, exception, unrecognised and bound tests | no gap, scan not PARTIAL, A02 not INDETERMINATE |
| gap placement, `usable`, cap, standing limitations | the stub returns no gaps and no standing sentences: the gap entry, the opaque-mount and server-flag sentences are absent, and the `usable` test's PARTIAL assertion on unavailable evidence fails (its `usable` assertion is a pin, green by design) |
| facts limitations pin | the stub ignores the facts, so the pin is green against it; it turns red only if a later step copies the text, and Task 5's control (below) plants that defect once to prove it bites |
| read purity | the stub does not count calls; the double's counters expose that the action path does not call `routes()` once |
| single read | the stub never calls the introspector, so the call count is 0, not 1 |

- [ ] **Step 1:** `test_default_fastapi_app_reports_developer_tooling` with `# ported: SpringPentestingObservationCollectorTests.apiDocsCheckFiresForDeveloperConsoles` (`:1088`): one PT-A05-041, severity INFO, confidence Medium, evidence `Detected developer-tooling mapping(s): /docs, /openapi.json, /redoc. Anonymous reachability was not tested.`, and no mention of an ordinary API route.
- [ ] **Step 2:** `test_openapi_disabled_app_has_no_documentation_finding` (worst case), `test_custom_docs_url_is_reported_without_the_oauth2_redirect`, `test_user_route_named_docs_is_not_documentation`, `test_mounted_subapp_documentation_is_reported`.
- [ ] **Step 3:** `test_proxy_headers_middleware_is_reported` with `# ported: SpringPentestingObservationCollectorTests.forwardHeadersStrategyFiresForFrameworkAndNative` (`:1185`): fires with `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware` on the root stack, silent without it (the `none` case), and a mounted-only case; `trust_any_proxy` leaves the finding unchanged. `test_lookalike_proxy_middleware_is_not_matched`: a class named `FakeProxyHeadersMiddleware` and a `ProxyHeadersMiddleware` defined in another module do not fire.
- [ ] **Step 4:** Masking, on every surface (scan response, MCP `pentest_scan` output, CLI `pentest scan` output and the cached `GET`), parametrised over `MASKED`, `METADATA_ONLY` and `FULL` with the real `Masker`: `test_docs_route_path_with_a_secret_is_masked_in_evidence`, `test_mount_path_with_a_secret_is_masked_in_evidence` and `test_forwarded_header_mount_evidence_masks_the_mount_path` (PT-A05-044's evidence for a sub-application with `ProxyHeadersMiddleware` mounted at a secret path). Canaries are measured against `Masker.mask_text`: a JWT-shaped segment (`/docs/<jwt>`) and a `key=` segment (`/api/key=abc123SECRETvalue/docs`) are redacted under `MASKED`. Expected per exposure: `MASKED` has the canary absent and BootUI's fixed text intact; `METADATA_ONLY` shows `[masked]` for every path with the count preserved and no path text; `FULL` shows the paths verbatim (a deliberate control). In every exposure the finding is present and a non-secret path yields the finding with that path (positive control). `test_long_path_list_evidence_is_sanitised_and_cut`: many long paths, one containing a newline, give one evidence string of at most 240 characters ending in `...` with no CR, LF or TAB, on every surface. The wiring is A11's `masker` argument; this lane adds no masker. `test_framework_exposure_findings_can_be_dismissed` for an initial, cached and scanned report (`# ported: PentestingDismissalTests`, `PentestingDismissalTests.java:40-43`).
- [ ] **Step 5:** `test_report_reads_do_not_build_route_evidence` using `no_side_effects` and an introspector double that counts `routes()`, `app_info()` and `security_facts()` calls on GET, MCP read and CLI read (all zero). `test_one_scan_reads_security_facts_and_routes_once` (one scan, both counters equal 1, with a session-evidence consumer active). `test_mcp_and_cli_scan_include_framework_evidence`. `test_scan_with_partial_exposure_evidence_is_evaluated_by_fail_on` pins the existing PARTIAL note (`fail_on.py:113, 256`).
- [ ] **Step 6:** `test_unavailable_route_metadata_is_incomplete_not_clean` (a double without `routes`), `test_introspector_exception_degrades_to_unavailable_evidence` (`routes()` and, separately, `security_facts()` raise `RuntimeError`; the scan completes, is PARTIAL, has the gap, no finding and A02 INDETERMINATE), `test_unrecognised_documentation_handlers_are_incomplete_not_clean`, `test_pure_starlette_host_skips_proxy_evaluation_without_a_gap`, `test_route_inspection_bound_makes_the_scan_partial` with `# ported: PentestingScannerTests.truncatedEndpointMetadataMakesA07IndeterminateButNotA04` (`:754`), adapted: PARTIAL, the BootUI gap wording, A02 INDETERMINATE, A04 and A10 unchanged. `test_a07_coverage_is_unchanged_by_endpoint_truncation`: A07 stays NOT_APPLICABLE (REVIEW only with PT-A07-008), with the adaptation reason in a comment (the hand-off branch precedes the indeterminate branch, `PentestingCheckRegistry.java:279-286`).
- [ ] **Step 7:** Gaps, `usable`, the cap and the standing limitations, all through the scan action: `test_exposure_gaps_land_in_evidence_limitations_with_bootui_wording` (the bound gap text is an entry of `evidence.limitations`; `scan.message` is still the fixed A10 text), `test_usable_is_the_get_probe_whatever_the_route_evidence` (unavailable route evidence with a usable GET keeps `usable` true; a failed GET keeps it false with complete route evidence), `test_exposure_limitations_survive_the_twenty_entry_cap` (the worst case: GET and OPTIONS incomplete with every limitation flag, A11's and A12's maximal gaps and A13's three gaps all present; each A13 gap and standing sentence is present in the final list and is at most 240 characters, so none is cut), `test_standing_limitations_state_the_opaque_mount_and_server_flag_limits` (a scan with route evidence always carries the sentence that mounted applications which are not Starlette applications are not inspected, and the sentence that server-level forwarded-header flags are not observable; neither makes the scan PARTIAL), and `test_security_facts_limitations_text_never_reaches_the_report` (a facts double whose `limitations` carry a planted path such as `/canary-mount`: the planted text is absent from every surface and the scan is not PARTIAL because of it).
- [ ] **Step 8:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_exposure_api.py` and `uv run python scripts/dev/red_check.py <node ids>`. Each red names a missing finding, a wrong value or a missing gap. The Task 2 tests stay unpushed-red until Task 5 turns them green. Commit.

### Task 3: Engine value object and rules

**Commit:** `feat: evaluate framework-exposure evidence in the pentesting engine`

**Files:** `engine/collectors/pentesting/framework_exposure.py`, `tests/engine/collectors/pentesting/test_framework_exposure.py`.

**Interfaces:** `FrameworkEvidence(documentation_routes: tuple[str, ...], proxy_headers: tuple[str, ...], available: bool, truncated: bool, declared_documentation: bool, proxy_evaluated: bool)`; `evaluate(evidence, echo) -> list[Finding]` with `echo: Callable[[str], str]` required and no default; `gaps(evidence) -> list[str]`; `standing_limitations(evidence) -> list[str]` (at most three entries, each at most 240 characters); `MAX_ROUTE_PATTERNS = 4096`. Consumed by Tasks 4 and 5. Imports no framework and no masker class; it imports `sanitize_evidence` from `echo.py` and defines no echo or sanitiser. Masking is the `echo` argument: the rules pass only documentation route paths and mount paths through it. The engine tests use a recording echo and the real `Masker` through `make_echo`; the end-to-end proof on every surface is Task 2.

**Stub for the red run:** the Task 2 stubs, replaced one function at a time; the stub of `evaluate` has the final `(evidence, echo)` signature.

- [ ] **Step 1:** Unit tests first, ported from the same BootUI cases as Task 2: evidence text, sorted and de-duplicated routes (the collector's `LinkedHashSet`, `SpringPentestingObservationCollector.java:890`, then `sorted()`, `PentestingChecks.java:2286-2288`), empty routes give no finding, the mounted-name evidence of PT-A05-044, BootUI's DTO fields from the fixture. Echo tests: `test_evaluate_requires_an_echo` (a call without `echo` raises `TypeError`), `test_documentation_rule_echoes_each_unique_raw_path_once_in_sorted_order` (a recording echo sees `/a`, `/z` for the input `/z`, `/a`, `/a`, and sees no fixed BootUI text), `test_forwarded_header_rule_echoes_each_mount_path_and_never_the_class_name`, `test_metadata_only_placeholders_keep_the_count_and_the_order` (a placeholder echo over `/b`, `/a`, `/a` gives two placeholders, not one and not three), `test_evidence_is_sanitised_after_the_echo` (an echo that returns a CR/LF/TAB-bearing, over-long fragment gives one line of at most 240 characters ending in `...`), and a real-`Masker` case per exposure through `make_echo`. Add `test_no_other_pentesting_module_defines_an_echo_or_a_sanitizer` (an `ast` walk of every module under `engine/collectors/pentesting/` other than A12's `echo.py` finds no function named `make_echo` or `sanitize_evidence`, so `cors.py`, `cookie_checks.py` and `framework_exposure.py` import the one home; it is green on arrival, so its red evidence is a planted second definition in a temporary module). Run against the stub and confirm each red is a wrong value.
- [ ] **Step 2:** Implement with `checks.finding(...)` and `echo.sanitize_evidence`. Order inside each rule: raw values, sort, de-duplicate, echo each, join into BootUI's text, sanitise.
- [ ] **Step 3:** `gaps`: unavailable metadata, truncation (BootUI text `endpoint metadata was incomplete or exceeded the 4096-pattern inspection limit`, `PentestingScanner.java:260-262`), and declared documentation with no recognised handler. `standing_limitations`: (1) the route and middleware evidence is static declaration evidence and not authorization or reachability, and server-level forwarded-header flags are not observable; (2) mounted applications that are not FastAPI or Starlette applications are not inspected; (3) when `proxy_evaluated` is false, PT-A05-044 was not evaluated. A test asserts each sentence is at most 240 characters.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_framework_exposure.py tests/engine/test_import_boundary.py`; commit.

### Task 4: FastAPI adapter

**Commit:** `feat: read framework-exposure evidence from the FastAPI introspector`

**Files:** `fastapi/pentesting_exposure.py` (created by A12; this task adds a function to it), `tests/fastapi/test_pentesting_exposure_adapter.py` (created by A12 with the `read_security_facts` cases; this task adds cases).

**Interfaces:** `framework_evidence(introspector, facts) -> FrameworkEvidence`, added beside A12's `read_security_facts(introspector) -> SecurityFacts | None`, which this task uses and does not redefine, stub or re-test (one call, wrapped in `except Exception`, `None` on failure, on an absent method or on a result that is not `SecurityFacts`). `framework_evidence` reads `routes()` once and the supplied facts; never calls an endpoint. The facts are the shared read also consumed by A12's session evidence.

**Stub for the red run:** `framework_evidence` returns the available, empty evidence of Task 2.

- [ ] **Step 1:** Tests: the installed handler names equal the expected set (`fastapi.applications:FastAPI.setup.<locals>.openapi`, `swagger_ui_html`, `redoc_html`; `swagger_ui_redirect` is not a marker); a lookalike handler elsewhere does not match; the 4096 bound; `declared_documentation` is true only when the root app's `SecurityFacts.openapi_url` is set and no recognised handler appears (no ReDoc URL is read); an introspector without `routes`, one whose `routes()` raises, and facts that are `None` (what A12's `read_security_facts` returns for a raising, absent or wrong-type reader) give `available=False` without a crash; `FakeProxyHeadersMiddleware` and a same-named class in another module do not set `proxy_headers`, while `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware` does (root and mounted, with the mount path); a non-FastAPI host (`NOT_FASTAPI` facts) evaluates documentation and sets `proxy_evaluated=False`; `SecurityFacts.limitations` never changes completeness and its text, with a planted route path and mount label, never appears in the evidence or in any value the adapter returns.
- [ ] **Step 2:** Implement. The handler names and the middleware module and class name live only here; match on the simple name via the advisor's `simple()` helper plus the module prefix of `MiddlewareFacts.name`.
- [ ] **Step 3:** Run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_exposure_adapter.py tests/fastapi/test_introspector_security.py tests/engine/test_import_boundary.py`; commit.

### Task 5: Wire the scan action and the report

**Commit:** `feat: add BootUI framework-exposure checks to the pentesting scan`

**Files:** `report.py`, `service.py`, `fastapi/routes/pentesting.py`, the Task 2 and Task 1 tests.

**Interfaces:** `scanned_report(get, options, scanned_at=None, ..., exposure=None)` and `PentestingService.scan(..., masker, exposure=None)` (`masker` is A11's required keyword-only argument; the service builds `make_echo(masker)` once and passes it to `framework_exposure.evaluate`); `None` means no evidence supplied (no finding, the Task 1 limitation), which keeps older callers valid. The scan function in `routes/pentesting.py` always supplies it, from the one facts read that it also hands to A12.

- [ ] **Step 1:** Confirm the Task 1 and Task 2 failures are the named assertions.
- [ ] **Step 2:** Add the findings to `scanned_report`, and the gaps and standing limitations to `limitations` immediately before the generic trailing sentences (so the 20-entry cap keeps them); the scan message and `usable` are unchanged. An incomplete inventory sets `partial`, which makes A02 INDETERMINATE through A11's rule and leaves A07, A04 and A10 as BootUI's precedence gives them (`PentestingCheckRegistry.java:270-286, 415-435`); update the limitation sentence so route and middleware evidence is described as static declaration evidence (`PentestingChecks.java:2287-2291` wording) and Spring, Actuator and JVM checks are n-a; do not touch the CORS and cookie wording owned by A11 and A12.
- [ ] **Step 3:** Pass `exposure` through the service; in the scan function call `read_security_facts` once and `framework_evidence` once and share the facts with A12's session evidence, so the route, MCP and CLI share it. Masking is the `echo` the service builds from A11's `masker`. The single-flight acquisition is unchanged. Delete-the-control check: temporarily append the facts' `limitations` text to the report in the scan function, confirm `test_security_facts_limitations_text_never_reaches_the_report` fails on the planted path, and revert; likewise make `evaluate` skip `echo` and confirm the `MASKED` and `METADATA_ONLY` masking tests fail.
- [ ] **Step 4:** Add the regression pins `test_security_advisor_documentation_and_proxy_rules_are_unchanged` (existing `SEC-FAPI-002` and the proxy rule on the same apps) in `tests/engine/collectors/security/test_rules_auth.py` and `test_rules_transport.py` beside their current cases, and `test_pentesting_checks_are_not_owned_by_the_advisors` in the registry tests (`advisor_for` resolves no `PT-` id, the `SEC-FAPI-002` and `SEC-FAPI-003` ids resolve to the security advisor).
- [ ] **Step 5:** Add a scale test with more than 4096 routes proving one scan completes within the existing overhead budget (the budget is not raised), and run `uv run pytest -q -n 4 tests/fastapi/test_pentesting_exposure_api.py tests/engine/collectors/pentesting tests/fastapi/test_pentesting_api.py tests/engine/collectors/security/test_rules_auth.py tests/engine/collectors/security/test_rules_transport.py tests/cli/test_fail_on.py` and `red_check.py` for any `test:` commit; commit the implementation with explicit paths and DCO sign-off.

### Task 6: Matrix, parity and documentation

**Commit:** `docs: document the framework-exposure checks of the pentesting scan`

**Files:** `docs/reference/matrix-updates/0.8.0-a13.tsv`, `docs/reference/PARITY.md`, spec section 14, user documentation of the pentesting scan.

- [ ] **Step 1:** Write the matrix rows from the deviation table above (three tab-separated columns: key, status, reason). Task 1's matrix test turns green.
- [ ] **Step 2:** Update `PARITY.md` and spec section 14 for the two implemented checks, the adapted-elsewhere check and the n-a families; state in the user documentation that the findings report registered routes and middleware, not authorization or reachability, that mounted applications that are not FastAPI or Starlette apps are not inspected, and name the unobservable server flags.
- [ ] **Step 3:** Regenerate the deviation table with `scripts/dev/generate_parity_deviations.py` if the repository gate requires it; run `uv run pytest -q -n 4 tests/parity tests/engine/collectors/pentesting tests/fastapi/test_pentesting_exposure_api.py tests/fastapi/test_pentesting_exposure_adapter.py`, `uv run ruff check`, `uv run ruff format --check` and `uv run pyright`.
- [ ] **Step 4:** Live check with `/sharpit:live-verify` on a sample app: default docs reported, `openapi_url=None` silent, scan partial with a deliberately broken introspector; describe the evidence as route-table evidence only. Commit docs with explicit paths and `git commit -s`.

## Definition of done

- [ ] High-tier review disposition recorded before implementation.
- [ ] Every Critical and High scenario has a named passing test; GET reads provably build no evidence; every `test:` commit was seen red on its assertions against a wrong-value stub.
- [ ] PT-A05-041 and PT-A05-044 match the BootUI contract projection in id, category, severity, confidence and order; text deviations are matrix rows.
- [ ] All 38 framework-evidence ids are implemented, owned by another lane, adapted elsewhere or n-a with a reason, exactly once; the ledger checker is proved by planted controls.
- [ ] Unreadable, unrecognised and truncated evidence is stated and never clean; an exception never escapes the scan.
- [ ] Route and mount paths are absent from every output surface when they carry a secret, in `MASKED` and `METADATA_ONLY` (and shown verbatim only in `FULL`), through the shared `echo` and no second masker; PT-A05-044's mount evidence is covered; evidence is sanitised and cut at 240 characters; a per-rule recording-echo test passes.
- [ ] Gaps land in `evidence.limitations`, `usable` is the GET probe's, the 20-entry cap keeps A13's entries, the opaque-mount sentence is a standing limitation, and `SecurityFacts.limitations` text never reaches the report.
- [ ] The matrix fragment holds the `exposure-masking`, `exposure-coverage-a07` and `exposure-gap-placement` rows, and the ledger-to-matrix status mapping is tested.
- [ ] One `security_facts()` read and one `routes()` read per scan, shared with A12.
- [ ] Security advisor rules are unchanged and pinned; tool descriptions and `cli/tools.json` are unchanged.
- [ ] Lane tests, ruff and pyright pass; parity and spec section 14 reflect the lane.
