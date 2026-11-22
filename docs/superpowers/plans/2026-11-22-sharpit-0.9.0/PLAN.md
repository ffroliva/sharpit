# sharpit 0.9.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. Every lane gets its own plan file in this folder
> when its predict and scenario steps have run. Run `/sharpit:status --feature 0.9.0` for the next unchecked step;
> `/sharpit:check` before every commit.

**Goal:** sharpit 0.9.0 closes the gaps recorded against BootUI 2.5.0 and the open issue list. Wave H takes the
0.8.1 issues (#284–#288), the CI scan gap and the known flakes. Four tracks follow. Track S makes the SQL capture hot
path fast. Track J adds the journal sources that need that headroom. Track R ports the missing and partial API
routes. Track M ports the ten 2.5.0 rules recorded as `missing`. Track F adds the embedded console for Flask (#260),
and Track X adds the masking follow-ups (#253, trace and journal masking).

**Architecture:** No new BootUI version is ported. BootUI has no tag after `v2.5.0` yet, so the reference stays
`v2.5.0`; the next tag becomes the pin for the release after this one. Two overhead budgets set the order. The SQL
listener budget (50 µs per statement) has the least headroom, so Track S measures and cuts it before anything adds
work to that path. The transaction budget (30 µs per transaction pair) held back the 0.7.0 transaction lanes (A2,
B2), so Track J starts from a constant-time design measured before the behaviour is ported. The safety model, the architecture rules and `sharpit-report/1` (additive changes only) stay as they are
unless a lane's predict step and council say otherwise. A change to a safety-model rule also needs the maintainer's
decision and the `AGENTS.md` change in the same pull request.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, Flask (optional, Track F), SQLAlchemy 2 (optional), pytest + xdist,
Svelte 5 + TypeScript (`ui/`), uv.

**Reference:** BootUI tag `v2.5.0` (commit `c4458db8dd18c08074119f22a79dda3e714abbda`), read in a BootUI clone with
`git show v2.5.0:<path>`. BootUI `main` after `v2.5.0` is not a reference for this release. BootUI paths below are
shortened: `E/` = `bootui-engine/src/main/java/io/github/jdubois/bootui`, `S/` =
`bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure`.

**Review:** Lanes marked *predict* run `/sharpit:predict` and `/sharpit:scenario` before their plan file is written.
Lanes marked *council* also run `/sharpit:llm-council --tier high`. This master plan is reviewed by a high-tier
council before Wave H starts.

## Where 0.9.0 starts

- 0.8.0 shipped on 2026-11-22 (BootUI 2.5.0). Its recorded gaps are listed in
  `docs/reports/2026-11-22-0.8.0-decisions.md` ("Moved to the next release") and in the 0.8.0 plan ("Recorded, not in
  this release"). This plan takes every one of them. Each gap gets either a lane below or a row under "Recorded, not
  in this release" with its blocker.
- The SQL listener budget (`tests/fastapi/test_sql_trace_overhead.py`, 50 µs per statement) has thin headroom. The
  per-statement cost was 46–51 µs on the sbx fleet for both 0.7.0 and 0.8.0, and one Windows CI shard measured
  51.5 µs on the 0.8.0 release pull request. A paired audit found no regression between the two versions. The budget
  is not raised; the cost is cut.
- The 0.7.0 transaction lanes measured 26–28 µs (A2) and 31.3 µs (B2) per transaction pair against the 30 µs budget
  of `tests/fastapi/test_transactions_overhead.py`, against 10.4 µs on the base.
- `ROADMAP.md` still describes 0.8.0 as next. It is rewritten in Wave H and recomputed in the release wave.

## Global Constraints

From `AGENTS.md`; every lane's requirements include these.

- Python `>=3.12`; runtime dependencies are exactly `starlette` and `packaging`. `fastapi`, `pydantic-settings` and
  `flask` are optional and imported only inside their gatekeeper (`sharpit/fastapi/`, `sharpit/flask/`, or a
  `try/except ImportError`).
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  are verbatim from BootUI with `BootUI`→`sharpit`.
- **Reads have no side effects**; actions follow BootUI's gates.
- Safety model 1–6 never regresses. A lane that touches activation, the guard chain, masking or introspection runs
  `/sharpit:known-issues` first. A masking change runs a base-against-branch masking corpus diff before merge, and
  only one masking lane holds the corpus base at a time.
- Architecture rules 1–6. A change to a rule happens in `tests/engine/test_import_boundary.py` and `AGENTS.md` in the
  same pull request. No module under `src/` passes 1000 lines.
- **Port BootUI, do not reinvent:** each lane reads BootUI's source at `v2.5.0` before writing code and cites each
  ported test with `# ported: <Class>.<case>`. Each adaptation is one deviation row in
  `docs/reference/matrix-updates/<lane>.tsv`.
- Each defect found becomes a regression test seen red first (`scripts/dev/red_check.py`); one condition per assert.
- Hot-path overhead budgets are never raised to pass, and a budget test is never marked slow or deselected.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | The Flask console is a second home for the guard chain; one gate missing or reordered exposes the console | F0 decides where the chain runs before any code; F1 runs the guard corpus through both adapters and requires byte-identical decisions; *predict*, *council* |
| Critical | A swallowed-exception finding prints an exception message that carries user input (#253) | X1 uses the existing exception-message scrubbing and masking; corpus rows added before the diff; *predict*, *council* |
| High | A Track J source pushes the per-statement, per-transaction or per-request cost over budget | J0 measures the transaction design before J1 and J2; nothing adds per-statement work before S2; each source has its own budget test, measured on the sbx fleet |
| High | Hosting the Starlette console inside a WSGI application adds a runtime dependency or a second event loop | F0 is a spike with a written verdict; no new runtime dependency (architecture rule 4 and the global constraint) |
| High | Flask request correlation misses requests (streamed bodies, an aborting earlier hook, session cleanup, as recorded on #75) | F2 wraps `wsgi_app`, as the T1 HTTP security observer already does, instead of `before_request` and `teardown_request`; tests cover each case |
| High | New routes in Track R read state that has side effects or leaks unmasked text | Every new GET route uses the `no_side_effects` fixture and the masking path of its panel |
| Medium | Tool calls on a host with several event loops run on the wrong loop (#287) | H3 is *predict*: BootUI has no counterpart (one JVM, no loops), so the design is sharpit's own |
| Medium | The scope is larger than one release | The release ships once every lane is merged or recorded as deferred with its reason (as for 0.8.0); Wave H and Track S come first because the other tracks depend on them |

## Lanes

Status: `[ ]` not started, `[~]` in flight, `[x]` merged.

### Wave H: housekeeping (the 0.8.1 issues, CI, flakes)

- [ ] **H1 Dead code** (#284, #286). Remove `is_validation_error` (`fastapi/binding_diagnostics.py`) and the dead
      `or text == ""` clause in the found-at scan test.
- [ ] **H2 Cancel on caller timeout** (#285). The MySQL, PostgreSQL and Database advisor tools cancel their work on a
      caller timeout, as the pentest tool does. A red test per tool.
- [ ] **H3 Tool calls with several event loops** (#287), *predict*. A tool call runs on the loop of the request that
      issued it, not on the last recorded loop; this covers the pentest scan and the database advisor scan.
- [ ] **H4 Tests on production code** (#288). The two 0.8.0 tests that use a stand-in (`_Store` stub, copied
      `run_probe` acquire and release) exercise the production code; delete the control and re-run to prove each one bites.
- [ ] **H5 Flakes.** `test_session_stream_sends_sessions_then_dashboard` (intermittent on Windows CI): systematic
      debugging and a fix on the cause, never a retry or a skip.
- [ ] **H6 Scans before the release pull request.** CodeQL runs on pull requests into `release/**`, and
      `skills/release/SKILL.md` runs Sonar and CodeQL on the ship branch before the release pull request opens. This
      is a workflow change into `main` and needs the maintainer's go.
- [ ] **H7 Documents.** `ROADMAP.md` rewritten (0.8.0 delivered, 0.9.0 next, Flask); the live-verify skill uses the
      CLI's `--url` option; the 0.8.1 milestone issues move to 0.9.0.
- [ ] **H8 Dependency updates.** The open Dependabot pull requests are triaged and merged or closed with a reason.

### Track S: SQL capture hot path (runs first; nothing adds per-statement work before S2)

- [ ] **S0 Measure**, `/sharpit:perf-audit`. A per-function profile of the per-statement path on the sbx fleet and on
      a Windows runner, with the runner offset separated from split-half noise. The output is a ranked cost table and
      a headroom target that Track J's sources fit inside. No code change.
- [ ] **S1 Listener registration race** (0.7.0 D1). Class-level listener registration on Engine, Pool and Mapper is
      race-free under concurrent `install()` and test sessions.
- [ ] **S2 Per-statement path** (0.7.0 D2), *predict*. Port BootUI 2.5.0's event-sink capture where it applies, guided
      by S0's table. Done when the 50 µs budget passes on every fleet box with the headroom S0 set.
- [ ] **S3 SQL Trace panel availability** (0.7.0 D3). The panel reports available as BootUI does before a data source
      is wrapped.
- [ ] **S4 Connection and SQL facts** (0.7.0 D4). The connection statement counts and recorded-SQL presence flags
      follow BootUI.

### Track J: journal sources and insight kinds

Each source runs `/sharpit:predict` and measures its overhead before code.

- [ ] **J0 Transaction pair design**, `/sharpit:perf-audit`. A design whose begin and commit stay constant-time when no
      second transaction is open, measured on `tests/fastapi/test_transactions_overhead.py` inside the 30 µs budget
      before any behaviour is ported.
- [ ] **J1 Observed transaction boundaries** (0.7.0 A2), *predict*. Port `TransactionBoundary.observed` and failed
      begin reporting on J0's design.
- [ ] **J2 Transaction journal source** (0.7.0 B2). `transaction` events, `split-transaction-writes` and
      `transaction-across-remote-call`, inside the same budget.
- [ ] **J3 ORM journal source** (0.7.0 B3), *predict*. SQLAlchemy session events as the `orm` source; the ORM flush and
      context kinds. After S2 if it adds work per statement.
- [ ] **J4 Authorization journal source** (0.7.0 B4, BootUI #1677), *predict*, *council*. FastAPI security
      dependencies as the `authorization` source, the anonymous-access kinds and the request journal's
      `authorizations` key, which is a placeholder today.
- [ ] **J5 Remaining kinds** (0.7.0 B5). App-event, garbage collection and background executor kinds are each ported or
      recorded as a deviation with its reason.

### Track R: API route parity

- [ ] **R1 Missing routes** (0.7.0 B6). The 32 BootUI API routes marked `missing` in `tests/parity/routes_status.json` sharpit does not serve, across scan results, runtime
      insights, traces, memory and application structure. `GET /activity/request/{id}/journal` comes first.
- [ ] **R2 Same-route baselines** (BootUI #1688), *predict*. `baselineComparison` on the request journal, after R1's
      journal route. Retention and overhead are measured.
- [ ] **R3 Partial routes** (0.7.0 B7). The 28 partial route differences are closed or recorded per panel.

### Track M: the 2.5.0 rules recorded as missing

- [ ] **M1 REST API rules.** `RAPI-MAP-012`, `RAPI-MAP-013`, `RAPI-VER-008`, `RAPI-VALID-007`, `RAPI-PAGE-004`.
- [ ] **M2 Database rules.** `DB-SCHEMA-011`, `DB-PG-006`, `DB-POOL-005`, `DB-SERVER-008`, `DB-MYSQL-004`.
- [ ] **M3 `paged-without-order`**, *predict*. It needs SQL row-limit and shape analysis that holds under default
      masking; without that analysis, it is recorded with its reason, not approximated by a regex.

Each rule is ported from its BootUI class at `v2.5.0`, its PARITY row moves from `missing`, and each ported test cites
its source.

### Track F: the embedded console for Flask (#260)

- [ ] **F0 Hosting spike**, `/sharpit:spike`, *predict*, *council*. How `sharpit.install(app)` serves the console and
      its API inside a WSGI application with no new runtime dependency, and where the activation rules and the guard
      chain run. The verdict names the design and its measured cost per request.
- [ ] **F1 `sharpit.install` for Flask**, *council*. Activation, the guard chain, panel access and masking as on
      FastAPI. Flask imports stay in `sharpit/flask/`. The guard corpus passes through both adapters with identical
      decisions.
- [ ] **F2 Request correlation.** Captured SQL and exceptions link to the Flask request that caused them, through a
      `wsgi_app` wrapper. Tests cover streamed bodies, an earlier hook that aborts, and session cleanup. It has an
      overhead budget test.
- [ ] **F3 Example application.** `examples/flask_sqla`, with a gate test like the FastAPI samples.
- [ ] **F4 Route model limits.** `strict_slashes` and subdomain or host matching are shown in the route model or
      recorded as limits.

Closes #260 when F1–F3 merge.

### Track X: masking follow-ups (one corpus base at a time)

- [ ] **X1 Exception message in swallowed-exception findings** (#253 item 1), *predict*, *council*, masking corpus
      diff. Masked like other captured text; the lane decides which exposure levels show it.
- [ ] **X2 Reason for an accepted finding** (#253 item 2). A `reason=` argument on the accept marker, and a setting that
      makes it required in CI.
- [ ] **X3 Trace and journal masking on the matrix path**, masking corpus diff. Trace masking and journal masking move
      onto the matrix masking path; the gate corpora are byte-identical before and after.
- [ ] **X4 Email mask fail-safe** (0.7.0 D6 remainder). An invalid `SHARPIT_EMAIL_MASK_CONTENT` takes the strict
      fail-safe and adds a warning.

Closes #253 when X1 and X2 merge.

### Recorded, not in this release

Each stays a recorded gap with its blocker.

- **2.5.0 and 0.7.0 live goldens:** they need BootUI built into the reference application with its databases.
- **Instance discovery and `init`** (BootUI #1687): a deviation from safety rule 6.
- **BootUI changes after `v2.5.0`:** they are ported once a tag exists, in the release that pins it.

### Release wave

- [ ] **RW** — `ROADMAP.md` and README columns recomputed against 2.5.0; `CHANGELOG.md`; `docs/reference/PARITY.md`
      merged from the lane fragments; Sonar and CodeQL on the ship branch (H6); `/sharpit:doc-review`;
      `/sharpit:live-verify` on a FastAPI and a Flask sample; `/sharpit:release` prepares the release and stops.

## Dependencies

```
H1-H8: start now (H6 needs the maintainer's go)
S0 ── S2;  S1, S3, S4 start now (S1 before S2 if both touch registration)
J0 ── J1 ── J2;  S2 ── J3 (if J3 adds per-statement work);  J4, J5 after their predict
R1 ── R2;  R3 any time
M1, M2: start now;  M3 after its predict
F0 ── F1 ── F2 ── F3;  F4 with F1
X1 ── X3   (one masking corpus base at a time);  X2, X4 any time
J4 and R2 both fill a request-journal key (`authorizations`, `baselineComparison`): the second to merge updates the DTO test
every lane ── RW
```

## Decisions (2026-11-22)

1. **Reference:** BootUI `v2.5.0`. BootUI has no newer tag, and the port rule reads a tag. The release after 0.9.0
   pins the next BootUI tag.
2. **The 0.8.1 issues are fixed in this cycle** (Wave H). Whether they also ship early as a 0.8.1 patch is open.
3. **The Flask console is in scope.** On #75 (2026-11-20) the console was planned only if Flask users asked for it.
   The maintainer decided on 2026-11-22 to build it in 0.9.0 under #260, now that the route model and the gate have
   shipped. F0 decides its design first.
4. **All four parity tracks are in scope** (S/J, R, M, F). Tracks S and J0 run first, because the lanes after them
   need their measured headroom.
