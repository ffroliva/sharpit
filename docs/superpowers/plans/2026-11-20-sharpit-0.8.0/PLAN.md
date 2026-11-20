# sharpit 0.8.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. Every lane gets its own plan file in this folder
> when its predict and scenario steps have run. Run `/sharpit:status --feature 0.8.0` for the next unchecked step;
> `/sharpit:check` before every commit.

**Goal:** sharpit 0.8.0 is measured against BootUI 2.5.0, ports the 2.5.0 changes that apply to a Python application,
and closes the open issue list: #207, #75 (Flask, gate first), #68 and #59.

**Architecture:** A pin wave (W0a, W0b) repairs the capture pipeline, captures the BootUI 2.5.0 static fixtures and
moves the static parity tests and status files to them without changing behaviour. A contribution wave (P) adds the
contributor documents and the contribution check before the first outside contribution merges. Track A ports what
2.5.0 changed; Track E closes the open issues; Track F adds the Flask gate. The safety model, the architecture rules
and `sharpit-report/1` (additive changes only) stay as they are unless a lane's predict step and council say
otherwise; a change to a safety-model rule also needs the maintainer's decision and the `AGENTS.md` change in the same
pull request.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, SQLAlchemy 2 (optional), Flask (test only, Track F), pytest + xdist,
Svelte 5 + TypeScript (`ui/`), uv.

**Reference:** BootUI tag `v2.5.0` (commit `c4458db8dd18c08074119f22a79dda3e714abbda`, tag object
`80a4ee22affd9d1544c9eaf4b3b876e16b2c7bfc`), read in a BootUI clone with `git show v2.5.0:<path>`. `v2.4.0..v2.5.0`
is 101 commits and 629 files. BootUI paths below are shortened: `E/` = `bootui-engine/src/main/java/io/github/jdubois/bootui`,
`S/` = `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure`,
`C/` = `bootui-cli/src/main/java/io/github/jdubois/bootui/cli`.

**Review:** this plan was reviewed on 2026-11-20 by a high-tier council (four independent reviewers across three
model families); its findings are incorporated below. Lanes marked *predict* run `/sharpit:predict` and
`/sharpit:scenario` before their plan file is written; lanes marked *council* also run `/sharpit:llm-council --tier high`.

## What 2.5.0 changes, in brief

- **No HTTP route, panel or tool is added or removed.** The 269 starter mappings and 78 actions are unchanged; the
  catalog adds three read sub-contracts of `GET /exceptions/{id}`. `bootui-tools.json` changes two descriptions
  (`get_mappings`, `get_request_profile`).
- **New DTO keys:** `basePath` on `mappings/flat`; `requestId`, `bindingDiagnostics`, `bindingDiagnosticsTruncated`
  on exception occurrences and request-profile exceptions; `authorizations` and `baselineComparison` on the request
  journal; `virtualThreadPinningSupported`, `pinnedEvents`, `outsidePinnedEvents`, `pinnedDurationMicros` on
  `runtime-insights/resource-profile` (`BootUiApiContractCatalog.java`).
- **Three properties are added:** `bootui.vulnerabilities.scan-timeout` (60s), `bootui.http-exchanges.expose-request-id-header`
  (**true**), `bootui.cli.instances-dir`.
- **One insight kind is added:** `route-latency-outliers` (#1670; 28 → 29 kinds), which needs only the HTTP source.
- **Forty-one rules are retired**, seven of which sharpit evaluates today (`RAPI-NAME-002`, `RAPI-DOC-001`,
  `RAPI-DOC-002`, `ARCH-CODE-004`, `ARCH-CODE-018`, `DB-POOL-004`, `DB-SERVER-002`). REST API rules stay registered and
  return `SKIPPED` with a retired definition (`E/engine/restapi/RestApiRules.java:945`); architecture and database
  rules are removed and their ids reserved (`DatabaseAdvisorRuleRegistry.java:8-19`, `ArchitectureRuleRegistry.java:16-17`).
  Sixty rules are added, most of them Spring, Hibernate, Quarkus, WebFlux, pentesting or JVM memory checks.
- **Masking:** exception and cause messages are scrubbed of user-input literals outside `FULL` exposure, and binding
  field paths redact map keys and unknown property names (`MessageExposure.scrubBindingLiterals`, `ExceptionsService`).
- **Engine changes that apply to Python:** binding diagnostics on validation failures (#1679); the request ID response
  header on by default (#1675); the mappings `basePath` and the HTTP Probe route picker (#1676); a whole-scan deadline
  and accuracy fixes in the vulnerability scan (#1691, #1703); accuracy fixes in ported rules (#1682, #1663, #1664);
  investigation navigation in the UI (#1711–#1713).
- **Depends on routes or sources sharpit does not have:** same-route baselines (#1688) live on
  `GET /activity/request/{id}/journal`, which sharpit has not built (recorded route gap); authorization evidence
  (#1677) reads the `authorization` journal source (recorded lane B4).
- **Java-only:** virtual-thread pinning (#1685), startup compatibility checks (#1697), Spring CI evidence (#1700), the
  Quarkus LTS baseline (#1729) and the Spring, Hibernate, Quarkus and JVM rules.
- **Not ported in this release:** local instance discovery and `init` (#1687). The CLI would read lease files and
  connect to URLs the user did not name, the host application would write a lease file at startup, and `init` writes
  MCP client configuration files; this conflicts with safety rule 6 and is recorded as a deviation.

## Global Constraints

From `AGENTS.md`; every lane's requirements include these.

- Python `>=3.12`; runtime dependencies are exactly `starlette` and `packaging`. `fastapi` and `pydantic-settings` are
  optional; `flask` and `flask-sqlalchemy` are test dependencies only.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  are verbatim from BootUI with `BootUI`→`sharpit`.
- **Reads have no side effects**; actions follow BootUI's gates.
- Safety model 1–6 never regresses. A lane that touches activation, the guard chain, masking or introspection runs
  `/sharpit:known-issues` first. A masking change runs a base-against-branch masking corpus diff before merge.
- Architecture rules 1–6. A change to a rule happens in `tests/engine/test_import_boundary.py` and `AGENTS.md` in the
  same pull request. No module under `src/` passes 1000 lines; new capture wiring goes in new modules, not in
  `fastapi/capture.py`.
- **Port BootUI, do not reinvent:** each lane reads BootUI's source at `v2.5.0` before writing code and cites each
  ported test with `# ported: <Class>.<case>`. Each adaptation is one deviation row in
  `docs/reference/matrix-updates/<lane>.tsv`.
- Each defect found becomes a regression test seen red first (`scripts/dev/red_check.py`); one condition per assert.
- Hot-path overhead budgets (capture middleware, SQL listener) are never raised to pass.
- An outside contribution merges only once the contribution check passes; its commits keep their author.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | Exception messages carry user-input literals today (an `int()` or validation message shows the raw value under `MASKED`) | A4b ports `scrubBindingLiterals` with Python patterns; masking corpus rows added before the diff; predict and council |
| Critical | Binding diagnostics put a rejected value or a user-supplied key into an output (pydantic errors carry `input`, `ctx` and `loc`) | A4a freezes the contract: pydantic `type` as the reason, never `msg`, `ctx` or `input`; `loc` map keys and extra-property names redacted unless `FULL`; predict, council and corpus diff |
| High | A4a captures validation errors that `fastapi/capture.py:196-205` deliberately skips today, wrapping the host's 422 handler | The reversal is stated in A4a's spec; a host-replaced 422 handler still runs (test); capture budget test unchanged |
| High | The request ID header changes host responses and trusts a rewritten peer | A8 ports all four BootUI gates (property, `http-exchanges` panel enabled, trusted source, an application header wins) and reuses the guard's trusted-source check; off whenever sharpit is inactive; predict and council |
| High | The capture script no longer reproduces the committed 2.4.0 fixtures, so a 2.4.0 → 2.5.0 diff mixes pipeline drift with BootUI changes | W0a re-captures 2.4.0 with the repaired script and records the drift separately before W0b |
| High | Retiring evaluated rules drops findings users rely on, or lets an old dismissal bind to a different check | A1 follows BootUI's mechanism per advisor; reserved ids never bind a dismissal (test); the changelog lists each id |
| Medium | Flask introspection breaks on Flask internals between versions | Track F follows safety rule 5 (degrade, never crash); tested on the lowest and latest supported Flask |
| Medium | The vulnerability scan deadline leaves the single-flight lock held, or a socket timeout outlives the deadline | A5 ports `PARTIAL` on deadline, gives each request min(request timeout, time left), and tests that the lock releases |
| Medium | An outside author does not sign, and #207 blocks the release | E0 is time-boxed (decision 3); the Flask lanes do not depend on it |

## Lanes

Status: `[ ]` not started, `[~]` in flight, `[x]` merged.

### Wave 0: pin BootUI 2.5.0 (no behaviour change)

- [ ] **W0a Capture pipeline repair.** In `scripts/capture_bootui.py`: classify the `BOOTUI-COMPAT-*` ids
      (`E/engine/compatibility/PlatformCompatibility.java`); read the Java `RETIRED_*` sets and the REST API retired
      definitions as retired; read property defaults and their line citations from source instead of the hand-filled
      table (`:688-701`); keep `bootui.cli.max-*` (`:706`); handle Windows long paths. Re-capture 2.4.0 with the
      repaired script and record every drift from the committed fixtures.
- [ ] **W0b Pin 2.5.0.** Capture `tests/fixtures/bootui/2.5.0/` (static fixtures), retarget the static parity tests and
      status files to 2.5.0, add a test that resolves every `# ported:` citation against `bootui-tests.json`, record
      the fixture delta in `docs/reference/BOOTUI-2.5.0-DELTA.md`, and move the version pin in `AGENTS.md` and the docs
      to `v2.5.0`. Route status stays measured against the 2.3.0 live goldens (2.5.0 live goldens are recorded below);
      `/mappings/flat` is marked `partial` against the 2.5.0 static contract until A2 lands, and the route ratchet pin
      moves from 5 to 4 with that reason. Depends on W0a; blocks every Track A lane except A5.

### Wave P: contribution

- [ ] **P1 Contributor documents** (do not block anything). `CONTRIBUTING.md` (setup, the four gates, red-first tests,
      the port-BootUI rule, the contribution check, pointer to `AGENTS.md`), `CODE_OF_CONDUCT.md` (Contributor Covenant
      2.1, with an enforcement contact), `.github/PULL_REQUEST_TEMPLATE.md`, bug and feature issue templates.
- [ ] **P2 Contribution check** (decision 1). Blocks E0's merge. Exempts Dependabot. A workflow on
      `pull_request_target` never checks out pull request code and pins every action by commit.

### Track A: what 2.5.0 changed

- [ ] **A1 Retired rules** (#1678, #1680, #1695, #1704). REST API: `RAPI-NAME-002`, `RAPI-DOC-001/002` return
      `SKIPPED` with BootUI's retired definition, and the five REST API skip reasons move to the retired reason.
      Architecture and database: `ARCH-CODE-004/018`, `DB-POOL-004`, `DB-SERVER-002` are removed and their ids reserved,
      with a test that a stored dismissal of a reserved id applies to nothing. Update the four security documentation
      rows; drop or re-cite the ten ported tests BootUI removed.
- [ ] **A2 Mappings base path and route picker** (#1676). `basePath` added to `AppInfo` through the introspector port
      (`engine/spi.py`), filled from the application's `root_path`; the two `bootui-tools.json` description changes;
      the HTTP Probe route picker in the UI. Tested on the `lowest-direct` job.
- [ ] **A3 `route-latency-outliers`** (#1670), *predict*. Port `E/engine/insights/RouteLatencyOutliers.java` with
      BootUI's thresholds; it reads only the HTTP source.
- [ ] **A4a Binding diagnostics** (#1679), *predict*, *council*, masking corpus diff. FastAPI `RequestValidationError`
      mapped to BootUI's `BindingDiagnosticDto` on exception occurrences and request-profile exceptions: pydantic `type`
      as the reason; never `msg`, `ctx` or `input`; map keys and extra-property names in `fieldPath` redacted unless
      `FULL`. The wiring lives in a new module; the host's 422 handler, including a replaced one, still runs.
- [ ] **A4b Literal scrubbing in exception messages** (part of #1679), *predict*, *council*, masking corpus diff. Port
      `MessageExposure.scrubBindingLiterals` with Python message patterns (`int()`, `float()`, `strptime`, `Enum`,
      pydantic) for every exception and cause message outside `FULL`.
- [ ] **A5 Vulnerability scan deadline and accuracy** (#1691, #1703). `scan-timeout` property; whole-scan deadline to
      `PARTIAL`; each request gets min(request timeout, time left) (`ScanDeadline.requestBudget`); the advisory
      interpretation fixes that apply to PyPI packages; the lock releases on every path.
- [ ] **A6 Rule accuracy fixes** (#1682, #1663, #1664). Port the fixes to rules sharpit already has. A per-PR table in
      `docs/reference/BOOTUI-2.5.0-DELTA.md` classifies all 101 commits, including the new rules (`RAPI-MAP-012/013`,
      `RAPI-VER-008`, `RAPI-VALID-007`, `RAPI-PAGE-004`, `ARCH-CODE-019`, `DB-SCHEMA-011`, `DB-PG-006`, `DB-POOL-005`,
      `DB-SERVER-008`, `DB-MYSQL-004`, `DB-DRIVER-010`) and fix PRs #1661, #1662, #1681, #1686, #1690, #1692. Each new
      rule that applies to Python gets a status row (`missing` for the next release); each Java-only rule gets `n-a`
      with its reason. Depends on A1.
- [ ] **A7 Investigation navigation** (#1711–#1713). UI only.
- [ ] **A8 Request ID response header** (#1675), *predict*, *council*. BootUI's four gates, the opt-out property, the
      guard's trusted-source check as the only trust test, an application-set header never overwritten, off whenever
      sharpit is inactive; header name `X-Sharpit-Request-Id`. The wiring lives in a new module.
- [ ] **A9 Contract key completeness.** Emit every new 2.5.0 DTO key: `authorizations: []` and
      `baselineComparison: null` until their routes and sources exist, the four resource-profile pinning keys as
      `false`/`0`, and `requestId` on exception occurrences. Each placeholder carries a deviation row.

### Track E: open issues

- [ ] **E0 #207** — finish the pull request on its own branch (the author allows maintainer edits): merge `main`,
      resolve the conflict in `pytest_plugin/apps.py`, move the changelog entry to 0.8.0 with credit to its author,
      review, approve the fork's CI run, and merge once the contribution check passes. Time-boxed by decision 3.
- [ ] **E1 #68** — name test doubles in swallowed-exception findings and group them by location.
- [ ] **E2 #59 with D6** — SQLite double-quoted runs and the masking double pass, *predict*, *council*, masking corpus
      diff. Runs after A4a and A4b (one masking corpus base at a time). Closes #59 by a merged change, or as a
      documented limitation with the maintainer's word.

### Track F: Flask, gate first (#75)

- [ ] **F1 Flask route model**, *predict*. A Flask `AppIntrospector` under `src/sharpit/flask/` over `url_map` and
      blueprints, converting Werkzeug parameters (`<id>`, `<int:id>`) to `{id}`; an adapter lookup in
      `pytest_plugin/apps.py` that finds Flask through `sys.modules` (the plugin never imports Flask); autodetect
      recognises Flask apps; `sharpit.flask` added to `ADAPTERS` and its import rule in
      `tests/engine/test_import_boundary.py` and `AGENTS.md` in the same pull request. The lowest supported Flask
      version is named in the lane plan. Whichever of E0 and F1 lands second resolves the `apps.py` conflict.
- [ ] **F2 Flask-SQLAlchemy gate test.** A Flask suite proves the N+1 and query-budget gates; `flask` and
      `flask-sqlalchemy` in the test extra. Independent of F1.
- [ ] **F3** — open a follow-up issue for the Flask console (`sharpit.install` for Flask) and link it from #75 when F1
      closes it.

### Recorded, not in this release

Each stays a recorded gap with its blocker.

- **2.5.0 live goldens** (and the 0.7.0 W0 live goldens): need BootUI built into the reference application with its
  databases.
- **Same-route baselines** (#1688): need `GET /activity/request/{id}/journal`, one of the recorded missing routes.
- **Authorization evidence** (#1677): needs the `authorization` journal source (B4).
- **Instance discovery and `init`** (#1687): deviation from safety rule 6.
- **0.7.0 lanes A2 and B2** (transaction boundaries and journal source): over the 30 µs budget; need a constant-time
  design first.
- **0.7.0 lanes B3, B4, B5** (ORM, authorization, app-event, gc and executor sources).
- **0.7.0 lanes B6, B7** (33 missing and 28 partial routes).
- **0.7.0 lanes D1–D4** (SQL capture hot path).
- **D6 remainder:** the `SHARPIT_EMAIL_MASK_CONTENT` fail-safe fallback, unless E2's council folds it in.
- **paged-without-order.**

### Release wave

- [ ] **R** — `ROADMAP.md` and README columns recomputed against 2.5.0; `CHANGELOG.md`; `docs/reference/PARITY.md`
      merged from the lane fragments; `/sharpit:doc-review`; `/sharpit:live-verify`; `/sharpit:release` prepares the
      release and stops.

## Dependencies

```
W0a ── W0b ──┬─ A1 ── A6
             ├─ A2, A3, A7, A9          (A2 and A7 share the committed UI bundle: one merges, the other rebuilds)
             ├─ A4a ── A4b ── E2         (one masking corpus base at a time)
             └─ A8                       (after its council)
A5, P1, E1, F1, F2: start now (no fixture dependency)
P2 ── E0
every lane ── R
```

## Decisions (the recommended option in bold)

1. **Contribution check.** **Developer Certificate of Origin sign-off (`Signed-off-by`), checked on each pull
   request**: Apache-2.0 §5 already licenses inbound contributions, and DCO needs no signing service. Or a contributor
   licence agreement: then an existing text used unmodified, with an individual and a corporate form.
2. **Java-only deviation rows** (#1685, #1697, #1700, #1729, the Spring, Hibernate, Quarkus and JVM rules, and #1687).
   **Record each as `n-a` or a deviation with its reason**; the list needs the maintainer's approval.
3. **#207 time box.** **If the contribution check is not passed within 14 days of the request, the maintainers
   re-implement the change with credit to its author** in the changelog.
4. **Request ID header default (A8).** **Port BootUI's default (on), behind all four gates, subject to the council**;
   or off by default as a deviation row.

Decided on 2026-11-20: the release scope above; Flask in the test extra only; the maintainers build Track F with the
author of #75 invited to review.

## Out of scope

The Flask console and Flask request correlation (F3 tracks them); the lanes recorded above; anything listed as
Java-only; new panels that BootUI 2.5.0 does not have.

## Definition of done

- [ ] Every lane above merged or recorded with its reason.
- [ ] Every row of the 2.5.0 static status files is `matched`, `partial` with a deviation row, `n-a` with a reason, or
      `missing` with a reference to its recorded lane; the route ratchet pin changes only with a stated reason.
- [ ] #207 merged (or re-implemented under decision 3); #75 closed by F1 with F3's follow-up issue open; #68 closed;
      #59 closed by a merged change or as a documented limitation with the maintainer's word.
- [ ] `/sharpit:check` green on the release branch; CI green on the full matrix.
- [ ] Each lane's deviation rows merged into `docs/reference/PARITY.md`.
- [ ] `/sharpit:live-verify` evidence for every changed endpoint and the UI.
