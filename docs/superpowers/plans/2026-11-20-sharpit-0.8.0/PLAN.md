# sharpit 0.8.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. Every lane gets its own plan file in this folder
> when its predict and scenario steps have run. Run `/sharpit:status --feature 0.8.0` for the next unchecked step;
> `/sharpit:check` before every commit.

**Goal:** sharpit 0.8.0 is measured against BootUI 2.5.0, ports the 2.5.0 changes that apply to a Python application,
and closes the open issue list: #207, #75 (Flask, gate first), #68 and #59.

**Architecture:** A pin wave (W0) repairs the capture pipeline, captures the BootUI 2.5.0 static fixtures and moves the
parity tests and status files to them without changing behaviour. A contribution wave (P) adds the contributor
documents and the contributor licence agreement check before the first outside contribution merges. Track A ports
what 2.5.0 changed; Track E closes the open issues; Track F adds the Flask gate. Each status file only moves toward
`matched`. The safety model, the architecture rules and `sharpit-report/1` (additive changes only) stay as they are
unless a lane's predict step and council say otherwise.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, SQLAlchemy 2 (optional), Flask (optional, Track F), pytest + xdist,
Svelte 5 + TypeScript (`ui/`), uv.

**Reference:** BootUI tag `v2.5.0` (commit `c4458db8dd18c08074119f22a79dda3e714abbda`, tag object
`80a4ee22affd9d1544c9eaf4b3b876e16b2c7bfc`), read in a BootUI clone with `git show v2.5.0:<path>`. `v2.4.0..v2.5.0`
is 101 commits and 629 files. BootUI paths below are shortened: `E/` = `bootui-engine/src/main/java/io/github/jdubois/bootui`,
`S/` = `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure`,
`C/` = `bootui-cli/src/main/java/io/github/jdubois/bootui/cli`.

**Predict verdict:** pending per lane. W0 and P change no runtime behaviour and need none. Lanes marked *predict* run
`/sharpit:predict` and `/sharpit:scenario` before their plan file is written; lanes marked *council* also run
`/sharpit:llm-council --tier high`.

## What 2.5.0 changes, in brief

- **No HTTP route, panel or tool is added or removed.** The 269 starter mappings and 78 actions are unchanged; the
  catalog adds three read sub-contracts of `GET /exceptions/{id}`. `bootui-tools.json` changes two descriptions
  (`get_mappings`, `get_request_profile`).
- **Three properties are added:** `bootui.vulnerabilities.scan-timeout` (60s), `bootui.http-exchanges.expose-request-id-header`
  (**true**), `bootui.cli.instances-dir`.
- **One insight kind is added:** `route-latency-outliers` (28 → 29 kinds), which needs only the HTTP source.
- **Forty-one rules are retired**, seven of which sharpit evaluates today (`RAPI-NAME-002`, `RAPI-DOC-001`,
  `RAPI-DOC-002`, `ARCH-CODE-004`, `ARCH-CODE-018`, `DB-POOL-004`, `DB-SERVER-002`); sixty rules are added, most of
  them Spring, Hibernate, Quarkus, WebFlux, pentesting or JVM memory checks.
- **Engine changes that apply to Python:** same-route request baselines (#1688); the mappings `basePath` and the HTTP
  Probe route picker (#1676); binding diagnostics on validation failures (#1679); the request ID response header on by
  default (#1675); a whole-scan deadline and accuracy fixes in the vulnerability scan (#1691, #1703); accuracy fixes in
  ported rules (#1682, #1663, #1664); investigation navigation in the UI (#1711–#1713).
- **Depends on a deferred source:** authorization evidence per request (#1677) reads the `authorization` journal source
  (lane B4, deferred).
- **Java-only:** virtual-thread pinning (#1685), startup compatibility checks (#1697), Spring CI evidence (#1700), the
  Quarkus LTS baseline (#1729) and the Spring, Hibernate, Quarkus and JVM rules.
- **Changes the CLI network rule:** local instance discovery and `init` (#1687) read lease files, connect to URLs the
  user did not name and write MCP client configuration files; the host application writes a lease file at startup.

## Global Constraints

From `AGENTS.md`; every lane's requirements include these.

- Python `>=3.12`; runtime dependencies are exactly `starlette` and `packaging`. `fastapi`, `pydantic-settings` and
  `flask` are optional.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  are verbatim from BootUI with `BootUI`→`sharpit`.
- **Reads have no side effects**; actions follow BootUI's gates.
- Safety model 1–6 never regresses. A lane that touches activation, the guard chain, masking or introspection runs
  `/sharpit:known-issues` first.
- Architecture rules 1–6. A change to a rule happens in `tests/engine/test_import_boundary.py` and `AGENTS.md` in the
  same pull request.
- **Port BootUI, do not reinvent:** each lane reads BootUI's source at `v2.5.0` before writing code and cites each
  ported test with `# ported: <Class>.<case>`. Each adaptation is one deviation row in
  `docs/reference/matrix-updates/<lane>.tsv`.
- Each defect found becomes a regression test seen red first (`scripts/dev/red_check.py`); one condition per assert.
- Hot-path overhead budgets (capture middleware, SQL listener) are never raised to pass.
- An outside contribution merges only with a signed contributor licence agreement; its commits keep their author.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | Binding diagnostics put a rejected input value into an output (FastAPI 422 errors carry `input`) | A4 runs predict and a base-against-branch masking corpus diff; the rejected value never leaves the capture |
| Critical | The request ID header changes every host response by default and trusts a forwarded address | A8 runs predict and council; trust comes from the socket peer only; capture middleware budget unchanged |
| High | The capture script no longer reproduces the committed 2.4.0 fixtures, so a 2.4.0 → 2.5.0 diff mixes pipeline drift with BootUI changes | W0 re-captures 2.4.0 with the repaired script first and records the drift separately |
| High | Retiring evaluated rules removes findings users rely on | A1 follows BootUI's retirement exactly (rule kept, result `SKIPPED` with BootUI's retired reason); changelog lists each id |
| High | Instance discovery widens the CLI's network and file-write surface | A9 runs predict and council before any code; out of the release if the council does not approve |
| Medium | Flask introspection breaks on Flask internals between versions | Track F follows safety rule 5: degrade, never crash; tested on the lowest and latest supported Flask |
| Medium | The vulnerability scan deadline leaves the single-flight lock held | A5 ports BootUI's `PARTIAL` on deadline and tests that the lock releases |

## Lanes

Status: `[ ]` not started, `[~]` in flight, `[x]` merged.

### Wave 0: pin BootUI 2.5.0 (no behaviour change)

- [ ] **W0** — Repair `scripts/capture_bootui.py`: classify the `BOOTUI-COMPAT-*` ids (`E/engine/compatibility/PlatformCompatibility.java`),
      read the Java `RETIRED_*` sets and the REST API retired definitions as retired, and handle Windows long paths.
      Re-capture 2.4.0 with the repaired script and record any drift from the committed fixtures. Capture
      `tests/fixtures/bootui/2.5.0/`, retarget the parity tests and status files to 2.5.0, record the fixture delta in
      `docs/reference/BOOTUI-2.5.0-DELTA.md`, and move the version pin in `AGENTS.md` and the docs to `v2.5.0`. Blocks
      every Track A lane.

### Wave P: contribution (before any outside contribution merges)

- [ ] **P1** — `CONTRIBUTING.md` (setup, the four gates, red-first tests, port-BootUI rule, licence agreement, pointer
      to `AGENTS.md`), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `.github/PULL_REQUEST_TEMPLATE.md`, bug and
      feature issue templates, and the contributor licence agreement check (decision 1). Blocks E0's merge.

### Track A: what 2.5.0 changed

- [ ] **A1 Retired rules** (#1678, #1680, #1695, #1704). Retire `RAPI-NAME-002`, `RAPI-DOC-001/002`, `ARCH-CODE-004/018`,
      `DB-POOL-004`, `DB-SERVER-002` as BootUI does; move the five REST API skip reasons to the retired reason; update
      the four security documentation rows; drop or re-cite the ten ported tests BootUI removed.
- [ ] **A2 Mappings base path and route picker** (#1676). `basePath` from the ASGI `root_path` in
      `engine/collectors/mappings.py`; the HTTP Probe route picker in the UI.
- [ ] **A3 Same-route baselines and `route-latency-outliers`** (#1688), *predict*. Port
      `E/engine/journal/RequestJournalProfiles.java` and `E/engine/insights/RouteLatencyOutliers.java` with BootUI's caps;
      baselines computed at read time from retained events, read overhead measured.
- [ ] **A4 Binding diagnostics** (#1679), *predict*, masking corpus diff. FastAPI `RequestValidationError` mapped to
      BootUI's diagnostics without rejected values.
- [ ] **A5 Vulnerability scan deadline and accuracy** (#1691, #1703). `scan-timeout` property, whole-scan deadline to
      `PARTIAL`, the advisory interpretation fixes that apply to PyPI packages.
- [ ] **A6 Rule accuracy and new rules** (#1682, #1663, #1664, #1689–#1709). Classify each candidate (`RAPI-MAP-013`,
      `RAPI-VER-008`, `DB-SCHEMA-011`, `DB-PG-006`, `DB-POOL-005`, `DB-SERVER-008`, `DB-MYSQL-004`,
      `DB-DRIVER-010`) as applicable or Java-only, then port the applicable ones and the accuracy fixes.
- [ ] **A7 Investigation navigation** (#1711–#1713). UI only.
- [ ] **A8 Request ID response header** (#1675), *predict*, *council*. Port `RequestCorrelationFilter`'s header with
      BootUI's default and opt-out property, socket-peer trust only (decision 4).
- [ ] **A9 Instance discovery and `init`** (#1687), *predict*, *council*. Ported only if the council approves the
      change to safety rule 6 and the host-side lease write (decision 5); otherwise a deviation row.

### Track E: open issues

- [ ] **E0 #207** — finish the pull request on its branch: merge `main`, resolve the conflict in
      `pytest_plugin/apps.py`, move the changelog entry to 0.8.0 with credit to its author, review, and merge after
      the contributor licence agreement is signed (P1).
- [ ] **E1 #68** — name test doubles in swallowed-exception findings and group them by location.
- [ ] **E2 #59 with D6** — SQLite double-quoted runs and the masking double pass, *predict*, *council*, base-against-branch
      corpus diff.

### Track F: Flask, gate first (#75)

- [ ] **F1** *predict*. A Flask `AppIntrospector` under `src/sharpit/flask/` over `url_map` and blueprints, an adapter
      lookup in `pytest_plugin/apps.py` in place of the direct `FastApiIntrospector` import, a `flask` optional extra,
      and the import-boundary rule for `sharpit/flask/` (`tests/engine/test_import_boundary.py` and `AGENTS.md` in the
      same pull request). Depends on E0.
- [ ] **F2** — a Flask-SQLAlchemy test that pins the N+1 and query-budget gates on a Flask suite; `flask` and
      `flask-sqlalchemy` in the test extra only.

### Recorded, not in this release

Carried from 0.7.0 with their blockers unchanged; each stays a recorded gap.

- **W0 live goldens:** need BootUI built into the reference application with its databases.
- **A2 and B2** (transaction boundaries and journal source): over the 30 µs budget; need a constant-time design first.
- **B3, B4, B5** (ORM, authorization, app-event, gc and executor sources): new hot-path or security-surface sources;
  #1677 (authorization evidence) waits for B4 and is a deviation row until then.
- **B6, B7** (33 missing and 28 partial routes).
- **D1–D4** (SQL capture hot path).
- **paged-without-order.**

### Release wave

- [ ] **R** — `ROADMAP.md` and README columns recomputed against 2.5.0; `CHANGELOG.md`; `docs/reference/PARITY.md`
      merged from the lane fragments; `/sharpit:doc-review`; `/sharpit:live-verify`; `/sharpit:release` prepares the
      release and stops.

## Dependencies

```
W0 ──┬─ A1 … A9 (parallel, disjoint files; A8 and A9 after their council)
     └─ R
P1 ── E0 ── F1 ── F2
E1 independent ; E2 after its council
```

## Decisions (the recommended option in bold where still open)

1. **Contributor licence agreement text.** **An individual agreement based on the Apache Individual Contributor
   License Agreement, collected by a bot on the pull request**; or an existing text.
2. **Who builds F1 (decided 2026-11-20).** The maintainers build Track F; the author of #75 is invited to review it.
3. **W0 baseline.** **Re-capture 2.4.0 with the repaired script before capturing 2.5.0**, so the delta report shows
   BootUI's changes only.
4. **Request ID header default (A8).** **Port BootUI's default (on) with its opt-out property, subject to the
   council**; or off by default as a deviation row.
5. **Instance discovery (A9).** **Run predict and council in this release, port only on approval**; or record it as a
   deviation now.
6. **Java-only deviation rows** (#1685, #1697, #1700, #1729 and the Spring, Hibernate, Quarkus and JVM rules). **Record
   each as `n-a` with its reason**; the list needs the maintainer's approval.

## Out of scope

The Flask console (`sharpit.install` for Flask) and Flask request correlation; the lanes recorded above; anything
listed as Java-only; new panels that BootUI 2.5.0 does not have.

## Definition of done

- [ ] Every lane above merged or recorded with its reason.
- [ ] Every row of the 2.5.0 status files is `matched`, `partial` with a deviation row, or `n-a` with a reason.
- [ ] #207, #75 (gate), #68 and #59 closed by merged changes.
- [ ] `/sharpit:check` green on the release branch; CI green on the full matrix.
- [ ] Each lane's deviation rows merged into `docs/reference/PARITY.md`.
- [ ] `/sharpit:live-verify` evidence for every changed endpoint and the UI.
