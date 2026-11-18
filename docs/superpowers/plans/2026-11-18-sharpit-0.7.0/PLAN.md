# sharpit 0.7.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. The pin wave has its own plan file in this folder
> (`W0-pin.md`); every other lane gets its plan file when its predict and scenario steps have run. Run
> `/sharpit:status --feature 0.7.0` for the next unchecked step; `/sharpit:check` before every commit.

**Goal:** sharpit 0.7.0 matches BootUI 2.4.0 at the application level: every BootUI 2.4.0 route, tool, property, rule
and insight kind that applies to a Python application is served with BootUI's shape, or carries a recorded deviation
with its reason.

**Architecture:** A pin wave (W0) captures the BootUI 2.4.0 fixtures and moves the parity tests and status files to
them, without changing behaviour. Four tracks then run in parallel lanes on disjoint files: Track A ports what 2.4.0
changed in features sharpit already has; Track B closes the gaps sharpit still has against 2.4.0 (routes, insight kinds
and the journal sources they read); Track C is the command-line client (#60, its own plan); Track D carries the
engineering items deferred from 0.6.0. Each status file only moves toward `matched`. The safety model, the
architecture rules and `sharpit-report/1` (additive changes only) stay as they are unless a lane's predict step says
otherwise.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, SQLAlchemy 2 (optional), pytest + xdist, Svelte 5 + TypeScript
(`ui/`), uv.

**Reference:** BootUI tag `v2.4.0` (commit `0df7ed764688d04f83c246c9965e90158c1db488`), read in a BootUI clone with
`git show v2.4.0:<path>`. `v2.3.0..v2.4.0` changes 420 files; about 60% of them are CI, GitHub Action, CLI packaging
and documentation. BootUI paths below are shortened: `E/` = `bootui-engine/src/main/java/io/github/jdubois/bootui`,
`S/` = `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure`,
`C/` = `bootui-cli/src/main/java/io/github/jdubois/bootui/cli`.

**Predict verdict:** pending per lane. W0 changes no behaviour and needs none. Lanes marked *predict* below run
`/sharpit:predict` and `/sharpit:scenario` before their plan file is written; lanes marked *council* also run
`/sharpit:llm-council --tier high`.

## What 2.4.0 changes, in brief

- **No HTTP route, `bootui.*` property, panel or MCP tool is added or removed.** `BootUiApiContractCatalog` gains two
  DTO keys; `BootUiProperties.java` has an empty diff; `bootui-tools.json` changes seven description strings.
- **Engine changes that apply to Python:** the `insufficient`/`partial` evidence counters (#1589); observed
  transaction boundaries `NEW`/`REQUIRES_NEW`/`NESTED`/`UNKNOWN` and failed begins (#1599); the static-analysis rule
  `SEC-STATIC-001` (#1597); incomplete Database advisor discovery never reading as clean (#1600); journal ordering and
  idempotent aggregate registration (#1598); the read-only panel policy in the UI (#1602); HTTP exchange recording
  that never disrupts a response (#1615).
- **Java-only:** `bootui ci`, `bootui docs`, `bootui update` and their installers, the GitHub Action, Spring bean
  ordering, `HttpExchangesFilter` subclasses, Hibernate `JDBCException` classification, Logback thread-local holders,
  Quarkus wiring, and the VuePress docs site.

BootUI 2.5.0 (tag `v2.5.0`, 2026-11-17) is out of scope; it is the next release's target. Every BootUI test class and
case this plan names for Track A still exists at `v2.5.0`. Track B's kinds and routes were not compared with 2.5.0;
each Track B lane checks its BootUI sources at `v2.5.0` before porting, and a kind or route that 2.5.0 removes or
retires is a question for the release scope, not a default port.

## Global Constraints

From `AGENTS.md`; every lane's requirements include these.

- Python `>=3.12`; runtime dependencies are exactly `starlette` and `packaging`. `fastapi` and `pydantic-settings` are
  optional.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  are verbatim from BootUI with `BootUI`→`sharpit`.
- **Reads have no side effects**; actions follow BootUI's gates (MCP or CLI enabled, the guard chain, the panel
  enabled, the panel not read-only, single-flight where BootUI has it).
- Safety model 1–6 never regresses. A lane that touches activation, the guard chain, masking or introspection runs
  `/sharpit:known-issues` first.
- Architecture rules 1–6; a collector never imports another; gatekeepers stay in their named files; ratchets only go
  down. A change to a rule happens in `tests/engine/test_import_boundary.py` and `AGENTS.md` in the same pull request.
- **Port BootUI, do not reinvent:** each lane reads BootUI's source at `v2.4.0` before writing code, keeps its
  structure, checks, thresholds and texts, and cites each ported test with `# ported: <Class>.<case>`. Each
  adaptation is one deviation row in the lane's fragment `docs/reference/matrix-updates/<lane>.tsv`.
- Each defect found becomes a regression test seen red first (`scripts/dev/red_check.py`); one condition per assert.
- Hot-path overhead budgets (capture middleware, SQL listener) are never raised to pass.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A new journal source (transaction, orm, authorization, gc) adds side effects to a read, or overhead past a budget | Each source lane runs predict; `no_side_effects` on every read; budget tests run unchanged |
| Critical | `SEC-STATIC-001` reads files outside the application, follows a symlink, or reads without bounds | Port BootUI's bounds verbatim (1 MiB per file, symlink and special-file refusal, `INDETERMINATE` on oversize or malformed input) |
| High | Parity tests turn red when fixtures move to 2.4.0 and block unrelated work | W0 records every known difference in the status files, so CI stays green; later lanes only move rows toward `matched` |
| High | Observed transaction labels claim more than SQLAlchemy shows (`REQUIRES_NEW` false positives) | Spike first; `UNKNOWN` when ownership is not verified, as BootUI does |
| High | The command-line client gate on insufficient evidence needs counters the server does not emit yet | A1 lands the counters before CLI Task 6 merges |
| Medium | A gap route classified "missing" at 2.3.0 is Java-only on reading 2.4.0's source | The owning lane reclassifies it to `n-a` with a deviation row before writing code |
| Medium | The no-Spring-Security capture variant does not exist, so the static-only security report has no golden | Open decision 2 |

## Lanes

Status: `[ ]` not started, `[~]` in flight, `[x]` merged.

### Wave 0: pin BootUI 2.4.0 (no behaviour change)

- [ ] **W0** — [W0-pin.md](W0-pin.md). Capture `tests/fixtures/bootui/2.4.0/`, add the 2.4.0 parity tests and status
      files, record the fixture delta, and move the version pin in the docs. Blocks every Track A and B lane.

### Track A: what 2.4.0 changed in existing features

- [ ] **A1 — evidence counters and text** (after W0). Add `insufficient` and `partial` to the caught-exceptions
      report and summary (zeros: sharpit has no caught-exception sensor) and to the agent runtime-insights report,
      counted over every matching observation including rows cut by `limit`
      (`E/engine/insights/RuntimeInsightsAgentView.java:185-190`; `E/core/dto/CaughtExceptionsReport.java:27-28,46`;
      `E/core/dto/RuntimeInsightsAgentReportDto.java:42-43`). Port the seven `bootui-tools.json` description changes
      (`E/engine/mcp/McpToolDescriptions.java`), adapting analyzer names to the Python set from A3. Sharpit files:
      `engine/capture/exceptions.py` (`caught_report`), `engine/tools.py` (`caughtInCode`),
      `engine/collectors/insights/agent_view.py`, `engine/tools04/{runtime_insights,security,transactions}.py`.
      Tests: `RuntimeInsightsAgentViewTests`, `McpToolDescriptionsTests` (two cases). Unblocks CLI Task 6.
- [ ] **A2 — observed transaction boundaries** (after W0; *predict*; one lane with B2, sequenced A2 then B2, since
      both change `engine/capture/transactions.py`). Port `TransactionBoundary.observed(known, nested, savepoint)`
      and `begun`: failed begins become `ERROR`/"begin failed" in the activity feed and request profile
      (`E/engine/transactions/TransactionBoundary.java:4-21`; `TransactionRecorder.java:61-66,271`;
      `E/engine/journal/JournalActivityFeed.java:660,907`; `RequestJournalProfiles.java:627`). Replace the
      hard-coded `"PARTICIPATING" if parent is not None else "NEW"` (`engine/capture/transactions.py:166`). Starts
      with a spike on which SQLAlchemy shapes are `NESTED` (`begin_nested`, SAVEPOINT) and which, if any, are
      `REQUIRES_NEW` without false positives. Tests: `TransactionRecorderTests`,
      `JournalActivityFeedTests.failedBeginsRemainVisibleWhenFilteringTransactionErrors`.
- [ ] **A3 — `SEC-STATIC-001`** (after W0; *predict*: it reads project files). Port
      `E/engine/staticsecurity/StaticSecurityAnalysisDetector.java` and `StaticSecurityAnalysisRule.java`: the rule
      ID, INFO severity, title, bounds, silence when no build file is readable, and the rule that it never runs an
      analyzer and adds no runtime evidence or score. Adapt the declaration set to Python (open decision 1). The
      security panel stays available without a FastAPI security surface, reporting the static-only result
      (`S/web/PanelsController.java:653-666`). Tests: `StaticSecurityAnalysisDetectorTests` (22 cases, adapted).
      Docs: `docs/security-advisor-checks.md`.
- [ ] **A4 — Database advisor incomplete discovery** (after W0). Absent ORM metadata is a neutral INFO skip, and a
      failed model discovery is incomplete (WARNING), even with zero models
      (`E/engine/hibernate/EntityDiscovery.java:9,27`; `DatabaseAdvisorScanner.java:700`). Blank driver
      name, version or URL is a WARNING and incomplete evidence (`SchemaIntrospector.java:253-272`, read from
      `engine.dialect.driver`, the driver's `__version__` and `engine.url`). An incomplete PostgreSQL relation
      inventory is a WARNING, and an empty complete inventory is complete (`DatabaseAdvisorScanner.java:259-270`).
      Sharpit files: `engine/collectors/database_advisor/`, `engine/collectors/postgresql/`. Tests:
      `SchemaIntrospectorTests` (four named cases),
      `DatabaseAdvisorScannerTests.distinguishesAbsentJpaFromAZeroEntityDiscoveryFailure`.
- [ ] **A5 — journal robustness** (after W0). Make aggregate listener registration idempotent
      (`E/engine/journal/RuntimeJournal.java:625`;
      `RuntimeJournalTests.registeringTheSameAggregateAgainNeitherCountsTwiceNorRepairsMissingCoverage`). Break
      request-profile timeline ties by SQL start, then by sequence (`RequestJournalProfiles.java:272-293,525-536`).
      Spike whether SQL can reach sharpit's aggregates after its execution has completed; if it can, port
      `rememberCompletedExecution` and the three `JournalAggregatesTests` cases (`JournalAggregates.java:110-111,888-901`).
- [~] **A6 — read-only policy in the UI** (after W0). A Svelte port of #1602: `ApiError` shows `"<reason> (HTTP 403)"`
      for a panel-access refusal, which is not treated as "server unreachable", plus a `panelActionReason(panel)`
      helper (disabled, unavailable, read-only, unknown) used by every panel that runs a confirmed action. Server
      behaviour is unchanged (`engine/guard.py` already returns the reason). Tests: `actionPolicy.test.js`,
      `panelState.test.js`, `loadError.test.js`, ported to the `ui/` test runner. Rebuild `src/sharpit/ui/static/`.
- [ ] **A7 — exchange recording never disrupts a response** (after W0). Port the #1615 test scenarios, not the
      Spring filter: a recording failure leaves status, body and headers of a streamed or committed response
      unchanged, never masks an application exception, and logs only the exception class
      (`S/web/HttpExchangeRecording.java:21-76`; `BootUiHttpExchangesFilterTests`). Fix only what turns red.

### Track B: gaps against 2.4.0 (carried from 2.3.0)

The 2.3.0 status at release: 33 of 66 applicable routes served (5 matched, 28 partial), 33 missing; 8 of 28 insight
kinds implemented; 7 journal sources produced (`ai`, `connection`, `exception`, `http`, `log`, `mail`, `sql`). W0
re-measures all of this against 2.4.0.

- [ ] **B1 — SQL-only insight kinds** (after W0). `repeated-selects` (with 2.4.0's monotonic-start ordering and new
      limitation text, `E/engine/insights/RepeatedSelects.java:77,152-186`), `paged-without-order`,
      `unbatched-write-loop`, `event-loop-blocking`, `proxy-bypass`. Each reads only `sql` (transaction optional), so
      each can be built today; one kind module per lane step, `IMPLEMENTED = True` flipped by its own commit.
- [ ] **B2 — transaction journal source and kinds** (after A2, same lane; *predict*). Rebase the 0.6.0
      P-transaction branch (#166) onto A2's boundaries, then `split-transaction-writes` and
      `transaction-across-remote-call`. The overhead budget (30 µs per transaction pair) stays as it is; #166 measured
      +11.6 µs on one machine and 31.3 µs on Windows, so the lane starts with `/sharpit:perf-audit`.
- [ ] **B3 — ORM journal source and kinds** (*predict*). SQLAlchemy `Session` events as the `orm` source, then
      `orm-auto-flush`, `slow-flush`, `large-persistence-context`, `connection-reacquisition` and
      `readonly-candidate-transaction` (the last also needs B2).
- [ ] **B4 — authorization source and kinds** (*predict*, *council*: it observes the security surface). FastAPI
      security dependencies as the `authorization` source, then `anonymous-success-on-restricted-route` and
      `anonymous-data-reach`.
- [ ] **B5 — remaining kinds, classify first** (*predict*). `after-commit-writes` and
      `transactional-listener-skipped` (`app-event`), `gc-inflated-latency` and `heap-growth-after-gc` (`gc`,
      `resources`; a runtime `gc.callbacks` hook changes architecture rule 4, so *council*), `work-after-response`
      (`agent.executors`: asyncio tasks and `BackgroundTasks`), `changed-code-not-executed`. Each kind is either
      ported or recorded as not applicable, with a deviation row.
- [ ] **B6 — missing routes, by group.** Each group lane reads BootUI 2.4.0's controller and DTO for each route,
      reclassifies Java-only routes to `n-a`, then builds the rest:
      - *scan results* (8): `{architecture,database-advisor,fastapi,memory,postgresql,rest-api,security,vulnerabilities}/scanned`;
      - *runtime insights* (3): `runtime-insights/comparison`, `runtime-insights/impact`, `runtime-insights/impact-symbols`;
      - *activity and traces* (4): `activity/service-map`, `traces/detail`, `rest-client-trace`, `threads/captures`;
      - *memory* (3): `memory`, `live-memory`, `heap-dump` (GET; BootUI's heap-dump capture actions follow the
        action rule and single-flight);
      - *application structure* (6): `mappings`, `conditions`, `cache`, `http-sessions`, `dev-services`, `devtools`;
      - *classify first* (9): `fault-tolerance`, `pentesting`, `liquibase/changesets`, `kafka`, `crac`, `graalvm`,
        `graalvm/metadata`, `graalvm/scan-progress`, `jvm-tuning`.
- [ ] **B7 — partial routes.** The 28 partial routes move to `matched`, or keep a deviation row, inside the lane that
      owns their panel; there is no separate partial-routes lane.

### Track C: command-line client (#60)

- [~] **C** — [2026-11-16-sharpit-cli.md](../2026-11-16-sharpit-cli.md), executed from its own plan. Task 6
      (`--fail-on`, including the insufficient-evidence gate) merges after A1. Task 4's drift test reads BootUI's
      command paths from `tests/fixtures/bootui/2.3.0/tools.json` until W0 lands and from `2.4.0/tools.json` after
      it; 2.4.0 changes no command path, so the switch is a path change only.

### Track D: engineering deferred from 0.6.0

- [ ] **D1 — class-level SQLAlchemy listener race** (Engine, Pool, Mapper, transaction check-in): one lane for all of
      them.
- [ ] **D2 — the SQL listener's per-statement path.** Starts with a spike on whether BootUI 2.4.0's
      `RuntimeEventSink.beginCapture(source)` / `offer` / `discard` shape (`E/engine/journal/RuntimeEventSink.java:36-60`;
      `RuntimeJournal.java:308-363`) lowers sharpit's per-statement cost; verdict before code.
- [ ] **D3 — SQL Trace panel availability** before a data source is wrapped (the #185 gap row).
- [ ] **D4 — #184 and #185 audit follow-ups** (connection source and recorded-SQL fact).
- [ ] **D5 — hygiene:** unused aliases in `settings.py`; the `IdleTracker` private lock.
- [ ] **D6 — safety-path items** (*predict*, *council*, base-against-branch masking corpus diff): the masking double
      pass (BootUI masks quoted text once, `FrameworkWarningsByRoute.java:240-244`); an invalid
      `SHARPIT_EMAIL_MASK_CONTENT` value falling back to `False`.

### Track E: open bugs

Each follows `/sharpit:issue-resolve`: a worktree from `origin/main`, the regression test seen red first, the
smallest fix, a draft pull request. Port BootUI's behaviour where it has one.

- [ ] **E0 — #207** (`--sharpit-app` naming an object with no route list passes as empty). A draft pull request
      from a fork: it needs its CI workflows approved, `/sharpit:pr-council-review`, and the contributor's updates. It
      changes `fastapi/introspector.py` and `pytest_plugin/apps.py`, so it merges before E3.
- [ ] **E1 — #65** (a run with no findings exits 1 when one advisor assessed the app only in part; *predict*: it
      changes what the gate counts as a pass). Port the severity-gate semantics of BootUI's `FailOn`
      (`C/FailOn.java`): a `PARTIAL` assessment with no finding at or above the threshold passes and says it is not
      proof; a finding still fails; a gate that cannot be evaluated exits 1. Lost capture stays `unknown` (#19).
      Files: `engine/testsession/outcome.py`, `engine/testsession/gates.py` (the gate only), the advisors' statuses.
      Shares its semantics with CLI Task 6; whichever lands second reuses the first's tests.
- [ ] **E2 — #66** (a dismissed swallowed-exception finding comes back when a line above it moves). Key the
      identity on something that survives unrelated edits (path, qualified function, exception type), and check the
      baseline fingerprint for the same exposure. Existing `dismissedFindings` entries keep matching, or the
      changelog states the migration. Files: `engine/testsession/gates.py` (identity), the swallowed-exception fact.
- [ ] **E3 — #67** (the detected app depends on which tests imported it). After E0. The same flags must give the same
      advisors on a subset and on the full suite, or the report says why they differ. Files: `pytest_plugin/apps.py`.

#59 (a SQLite double-quoted run read as an identifier) is a documented limitation, not a regression. A change there
touches masking and goes through `/sharpit:predict` and `/sharpit:llm-council --tier high`; it is not part of this
track.

### Release wave

- [ ] **R** — `ROADMAP.md` and README columns recomputed against 2.4.0; `CHANGELOG.md`; `docs/reference/PARITY.md`
      merged from the lane fragments; `/sharpit:doc-review`; `/sharpit:live-verify`; `/sharpit:release` prepares the
      release and stops.

## Dependencies

```
W0 ──┬─ A1 ── C/Task 6
     ├─ A2 ── B2 ── B3 (readonly-candidate-transaction)
     ├─ A3, A4, A5, A6, A7, B1, B4, B5, B6 (parallel, disjoint files)
     └─ R (after every lane)
C (Tasks 2, 3, 5, 7): independent of W0; C/Task 4 switches fixture after W0
D1 ── D2 ── D3 ; D4, D5 independent ; D6 after its council
```

## Decisions (2026-11-18; the chosen option in bold)

1. **Python analyzer set for `SEC-STATIC-001`.** Build files: `pyproject.toml`, `setup.cfg`, `tox.ini`,
   `.pre-commit-config.yaml`, `requirements*.txt`. Analyzers: Bandit, Semgrep, a `sonar-project.properties` file,
   CodeQL workflow actions, and **ruff with the `S` rules selected counts as a declaration**. Blocks A3.
2. **Static-only security golden.** Both BootUI capture apps include Spring Security. **Default: capture the
   with-security variant only, and pin the static-only report by a ported unit test, not a golden.** Blocks nothing
   in W0.
3. **`REQUIRES_NEW` in SQLAlchemy.** **Default: `NESTED` for SAVEPOINTs, `NEW` for an unparented physical
   transaction, `UNKNOWN` for every other shape until the A2 spike proves a shape.** Blocks A2.
4. **BootUI `ci`, `docs`, `update`, and the #1626 reason column in `summary.py`.** **Default: not ported**; recorded as
   deviations (the client's plan already excludes `ci`, `docs` and `update`).
5. **Caught-exception counters.** **Default: emit zeros**, since sharpit has no caught-exception sensor; BootUI emits
   zeros when unavailable (`CaughtExceptionsReport.java:46`).

## Out of scope

BootUI 2.5.0; the Flask adapter (#75); anything listed as Java-only above; new panels that BootUI 2.4.0 does not have.

## Definition of done

- [ ] Every lane above merged or recorded as deferred with its reason.
- [ ] Every row of the 2.4.0 status files is `matched`, `partial` with a deviation row, or `n-a` with a reason; every
      insight kind is implemented or recorded as not applicable.
- [ ] `/sharpit:check` green on the release branch; CI green on the full matrix.
- [ ] Each lane's deviation rows merged into `docs/reference/PARITY.md`.
- [ ] `/sharpit:live-verify` evidence for every changed endpoint and the UI.
