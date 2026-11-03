# sharpit 0.5.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. Each lane has its own plan file in this folder;
> steps use checkbox (`- [ ]`) syntax. Run `/sharpit:status` for the next unchecked step; `/sharpit:check` before
> every commit.

**Goal:** sharpit 0.5.0 on `release/0.5.0`: every BootUI 2.2.0 panel id answered (eight panels: two resumes, six new),
the 0.3.0 panels caught up with their 2.2.0 drift, the two unverified panels settled, parity claimed only where it is
checked; benchmark depth spiked and built only with the owner's go.

**Architecture:** A gate lane (F5-gate) teaches `lane_gate.py` the 0.5.0 rules; two foundation lanes then put every
shared piece in place (F5a: app-source layer, advisor scan core extracted from rest-api, registry, safety harness,
settings; F5b: the `engine/sqla/` package in a move-only commit, then the MySQL/SQLite read-only path). Panel and drift
lanes run in parallel on disjoint files; each flips its own `IMPLEMENTED` flag. Merges go through `lane_gate.py`
only. Safety model, `sharpit-report/1` (additive) and fingerprints unchanged.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, SQLAlchemy 2 (optional), stdlib `ast`/`tomllib`/`tracemalloc`/`gc`,
pytest + xdist, Svelte 5 + TypeScript (`ui/`), uv.

**Spec:** `docs/superpowers/specs/2026-11-03-sharpit-0.5.0-design.md` (r2; council round 1 resolution in §15). The
0.4.0 spec governs what it does not change.

**Predict verdict:** CAUTION 6/10 (`predict.md`); council r1 BLOCK, resolved in r2 (spec §15). Scenarios:
`scenario.md`.

## Global Constraints

Verbatim from AGENTS.md and the spec; every lane's requirements include these.

- Python `>=3.12`; runtime deps exactly `starlette` and `packaging`. `fastapi` and `pydantic-settings` are optional.
- **No GET route and no MCP tool may open a socket, write a file, change a logger level or change `os.environ`** —
  and (0.4.0 spec §4) run SQL, read a file outside the app, call user code or configure ORM mappers. 0.5.0 adds: or
  change interpreter state (`tracemalloc`, `gc.callbacks`/threshold/enabled, `sys.settrace`/`setprofile`,
  `sys.monitoring` tool ids), or open an application source file (the one exemption: config's lazy getenv scan, 0.3.0
  behaviour, spec §14). F5a's `SideEffectGuard` checks all of it for every lane.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  verbatim from BootUI with `BootUI`→`sharpit`.
- Safety model 1–6 (AGENTS.md) never regresses; fails closed; secrets masked before any output.
- Architecture rules 1–6 (AGENTS.md); no collector imports another; gatekeepers per spec §9; ratchets only go down;
  budgets never raised.
- Each ported test cites `# ported: <BootUI class>.<method>`. A crash is not a red. One condition per assert.
- Conventional commits, explicit `git add` paths, **no AI attribution of any kind**.
- Never push or merge `main`, tag or publish. **No branch pushed without the owner** (O10). Long commands detached with
  a timeout and a log (codex/agy) or `run_in_background` (Claude).

## Red rule (every lane)

A red commit ships the neutral skeleton its tests import (functions and fields that exist and return a wrong value;
never a missing module, never `NotImplementedError`), and each step names the assertion expected to fail. A test that
passes on first run — a pin against existing behaviour, a pre-scan golden F5a's core already matches, a "not reachable"
check — is recorded in `findings.md` as a pin with its mutation (what was reverted in a scratch tree and the assertion
it then failed on). It is never claimed as a red. `lane_gate.py` refuses a red whose replay crashes or passes.

## Review Focus (cross-lane; each line has a test in the owning lane)

1. **MySQL/SQLite reads fail open** (F5b: `test_mysql_read_only_wrapper_rejects_write`,
   `test_sqlite_read_only_wrapper_rejects_write`; A-mysql/A-dbadv-1: `test_*_read_uses_verified_read_only_path`).
2. **The `sqla` split hides a broken patch** (F5b: `test_patch_targets_are_defined_where_called` + mutations).
3. **Wrong advisor enums behind empty goldens** (F5a: `test_advisor_core_matches_rest_api_post_scan_golden`).
4. **Introspection calls user code or drops subclasses** (R-fastapi-security:
   `test_trap_route_untouched_by_every_introspecting_surface`, `test_custom_apiroute_subclass_still_classified`).
5. **`appsource` reads outside the app or imports it** (F5a: `test_appsource_never_imports_or_follows_symlinks`,
   `test_app_package_setting_never_imports`).
6. **A read changes interpreter state** (F5a: `test_side_effect_guard_catches_interpreter_state`).
7. **A violation leaks the secret it found** (B-security, C-architecture, C-fastapi:
   `test_violation_never_contains_literal_secret`).
8. **A database scan writes or runs on AUTOCOMMIT** (A-mysql, A-dbadv-1: leased `test_read_only_wrapper_rejects_write`,
   `test_autocommit_engine_is_unavailable`).
9. **The transactions ring grows without bound** (R-transactions: `test_ring_stays_bounded_when_every_entry_is_open`).
10. **A drift route reads with side effects** (D2: `test_capture_drift_get_no_side_effects`).

## Lanes

| Lane | Plan file | Council | Class | Depends on | Worker (coordinator decides; this is the fit) |
|---|---|---|---|---|---|
| T-unbounded-read | `../2026-11-01-sharpit-0.4.0/T-unbounded-read.md` | — | precondition | — | coordinator (Step 0) |
| D3 | `../2026-11-01-sharpit-0.4.0/D3-drift-db-runtime.md` | — | precondition | — | coordinator (Step 0) |
| P-0.4.1 | `P-0.4.1.md` | not required | committed; build now, merge after F5-gate | T-unbounded-read (branch `base/0.4.1`) | Claude subagent |
| T-swallowed-2 | `T-swallowed-2.md` | not required | committed; build now, merge after F5-gate | — (branch `base/0.4.1`) | Claude subagent |
| F5-gate | `F5-gate.md` (lane id `F` under today's gate) | required (checked by hand: today's gate has no council check) | committed, first lane (after Step 0) | preconditions merged | codex gpt-6-luna |
| F5a-harness | `F5a-foundation.md` | not required | committed | F5-gate | codex gpt-6-luna |
| F5a-source | `F5a-foundation.md` | required | committed | F5a-harness | codex gpt-6-luna (high) |
| F5a-core | `F5a-foundation.md` | required | committed | F5a-harness | codex gpt-6-luna (high) or claude-flavio |
| F5b | `F5b-sqla.md` | required | committed | F5a-harness, P-0.4.1 | codex gpt-6-luna (high) |
| A-sqltrace-insights | `A-sqltrace-insights.md` | not required | committed | F5a-harness | agy-flavio Gemini 3.8 or Claude subagent |
| R-fastapi-security | `R-fastapi-security.md` | required | committed | F5a-harness | claude-flavio (Opus) |
| C-architecture | `C-architecture.md` | not required | committed | F5a-source, F5a-core | agy-sergio, Gemini 4 Argon |
| R-transactions | `R-transactions.md` | not required | committed | F5b | codex gpt-6-luna |
| A-mysql | `A-mysql.md` | not required | committed | F5b | agy-flavio, Gemini 3.8 |
| B-security-logs | `B-security-logs.md` | required | committed | R-transactions | codex gpt-6-luna |
| B-security | `B-security.md` | required | committed | R-fastapi-security, F5a-source, F5a-core | claude-flavio (Opus) |
| C-fastapi | `C-fastapi.md` | not required | committed | F5a-source, F5a-core (worker: after C-architecture) | agy-sergio, Gemini 4 Argon |
| A-dbadv-1 | `A-database-advisor.md` | not required | committed | F5a-core, F5b (lease: after A-mysql, or PG-only) | codex gpt-6-luna (high) |
| A-dbadv-2 | `A-database-advisor.md` | not required | committed | A-dbadv-1 | codex or claude-flavio |
| D2 | `D2-capture-drift.md` | not required | committed | A-sqltrace-insights, B-security-logs, R-transactions | codex gpt-6-luna |
| D4 | `D4-drift.md` | not required | committed | F5a-core, D2 | codex gpt-6-luna |
| V-unverified | `V-unverified.md` | not required | committed (Task 3 only without G0) | F5a-harness; G0 Tasks 4–5 (owner-only) | Claude subagent |
| G0 | `G0-goldens.md` | not required | Task 1 groundwork now; Tasks 2–7 **OWNER-ONLY** (O1) | — | agy-sergio, Gemini 3.8 slot |
| U20-memory | `U20-memory.md` | required | spike now; build **OWNER-ONLY** (O3/O4) | D2 | claude-flavio (Opus) |
| T-unbounded-read-2 | `T-unbounded-read-2.md` | not required | spike now; build on GO | D2, U20-memory merged or parked/declined | codex gpt-6-luna |
| W-workload | `W-workload.md` | required | spike only; build **OWNER-ONLY** (O5) | T-unbounded-read-2 | codex or claude-flavio |
| final | Step 5 below | — | — | all above merged or parked | coordinator |

This table is the single source for ids, plan files and council requirements (F5-gate reads the "Plan file" and
"Council" columns per lane id, so multi-lane files resolve correctly) and for dependencies. A precondition is done when
it is **merged into `release/0.5.0` through `lane_gate.py`** (Step 0), not when its review said APPROVE: heads move
after review (T-unbounded-read's head has moved several times since its review; D3's head `74aee39` is after its
reviewed `290478a`), and D3's last gate run failed two overhead budget tests on a loaded machine
(`gate/pytest.log`: 2 failed, 4,410 passed). Step 0 compares each `review.md` SHA with the head at gate time.

**Rule R0: two lanes whose May-touch lists intersect never run at the same time.** Known chains:

| Shared file(s) | Chain (order) |
|---|---|
| `engine/sqla.py` → `engine/sqla/` | T-unbounded-read → P-0.4.1 → F5b; then per submodule: `events.py` R-transactions, `inspect.py` A-dbadv-1 (disjoint, may overlap; neither adds names to `sqla/__init__.py`) |
| `fastapi/capture.py`, `fastapi/install.py` | R-transactions → B-security-logs → D2 → T-unbounded-read-2 |
| `engine/capture/activity.py` | D2 → U20-memory |
| `fastapi/introspector.py`, `engine/spi.py` | R-fastapi-security → B-security |
| `fastapi/routes/sql_trace.py`, `engine/tools.py` | A-sqltrace-insights → D2 → D4 |
| `engine/collectors/restapi/{service,report}.py`, `engine/advisors/{rules,report}.py` | F5a-core (status vocabulary, `sampleLocations` key) → D4 (fills `sampleLocations`, new rules) |
| `engine/collectors/data.py`, `engine/models.py` | F5a-harness → V-unverified |
| `engine/testsession/facts.py`, `gates.py`, `pytest_plugin/session.py`, `marker.py` | P-0.4.1 → U20-memory → T-unbounded-read-2 → W-workload |
| `pytest_plugin/options.py` | U20-memory → W-workload |
| `pytest_plugin/apps.py`, `engine/advisors/scan.py`, `registry.py`, `tests/golden.py` | F5a-core |
| `engine/appsource.py`, `engine/collectors/config/` | F5a-source |
| `tests/conftest.py`, `tests/safety/__init__.py`, `tests/test_safety_matrix.py`, `tests/engine/test_import_boundary.py` | F5a-harness, then F5b (boundary gatekeeper key); consumers never edit; a needed change is a coordinator fix commit on `release/0.5.0`, then the lane rebases |
| `settings.py` | F5a-harness; later only U20-memory (`memory_*`, after O3) |
| `tests/fastapi/test_introspection_trap.py` | R-fastapi-security only; later lanes add `trap_surfaces_<lane>.py` files |
| `ui/src/lib/panels04/index.ts`, `nav.ts`, `App.svelte`, `types.ts` | nobody |
| `src/sharpit/__init__.py` | B-security-logs only |

Dropped as false edges (council r1 M10): T-swallowed-2 → P-0.4.1, U20 → T-swallowed-2, A-dbadv-1 → R-transactions,
C-fastapi → B-security.

**Critical path:** Step 0 → F5-gate → F5a-harness → F5b → R-transactions → B-security-logs → D2 → D4.
**Start order:** coordinator runs Step 0 (re-review and re-gate both preconditions); meanwhile Claude subagents build
P-0.4.1 and T-swallowed-2 on `base/0.4.1` (merge after F5-gate), and spikes plus G0 Task 1 run in scratch worktrees.
codex runs F5-gate, then F5a-harness; then F5a-source and F5a-core in parallel (codex + claude-flavio) and F5b
(its council may run earlier; its move commit only after `council.md` APPROVE). After F5a-harness: claude-flavio
R-fastapi-security (if not on F5a-core), agy-flavio A-sqltrace-insights. After F5a-source + F5a-core: agy-sergio
C-architecture. After F5b: codex R-transactions, agy-flavio A-mysql. As slots free: codex B-security-logs → D2 → D4
and A-dbadv-1/2; claude-flavio B-security; agy-sergio C-fastapi. At most four code lanes, two full suites, one gate
run at a time.

**Large-lane split/stop:** a lane whose rule tasks pass ~600 source lines parks the remaining rules as `<lane>-2` with
catalogue rows "not yet" (B-security, C-architecture already have this line; A-database-advisor is pre-split).

**Leased-database evidence:** the coordinator runs leased tests itself (`agentctl lease database`; MySQL 8.4 container
and the reference compose's PostgreSQL) and writes `gate/leased-mysql.log` / `gate/leased-pg.log`. F5-gate's mapping
makes a skip `unverified`, never committed-done. No MySQL lease → A-mysql `unverified`, A-dbadv-1 PostgreSQL + SQLite.

**Budgets under load:** a budget red at a gate is `parked: budget under load`, re-run paired lane-vs-base once in a
quiet window; never merged on the lane's own number.

**Lane evidence (0.4.0 C2 layout):** the implementer writes `handoff.md`, `findings.md`, `field-map.md` (`N/A — not a
panel lane` outside panels), `checklist.md` and, for `Council: required` lanes, `council.md` (a `VERDICT:` line, two
or more model families, the head SHA), in the lane worktree under `.superpowers/sdd/0.5.0/lanes/<lane id>/` (F5-gate's
own evidence: `.superpowers/sdd/0.4.0/lanes/F/`, because today's gate reads it there). The coordinator and reviewer
write `review.md`, `gate/<name>.log` and `live-verify.md` **in the integration worktree only**.

**What `lane_gate.py` checks (after F5-gate):** every red in `findings.md` has a committed red SHA that is an ancestor
of the head; replayed there in a fresh tree it fails with an `AssertionError` whose last frame is under `tests/` (crash,
pass or `src/` assert refused); the test is unchanged to the head and passes there; the four gates at the head;
`review.md` `VERDICT: APPROVE` by a reviewer other than the implementer, with the head SHA; `checklist.md` evidence per
item; the complexity baseline only went down (re-keying only for the foundation set `F`, `F5a-harness`,
`F5a-source`, `F5a-core`, `F5b`); protected files changed only per the lane's `PROTECTED_ALLOWED` entry; dependency
lists in `pyproject.toml` changed only by `DEPENDENCY_ALLOWED` lanes (`[tool.*]` by `F` only); reviewer-owned paths of the current release never in a lane diff; leased logs per the lane mapping; `council.md` for `Council: required` lanes; every `## Must-cover`
test present and passing (full node ids; a skip refused unless leased or `post-scan golden absent`). `findings.md`
rows (the column is named `disposition`, values `fixed`, `pin: <mutation>`, `parked: <reason>`, `N/A — <reason>`;
`pin` and `N/A` rows carry no red SHA):

```
| finding | test (node id) | red SHA | red output (last assertion line) | disposition |
```

## Workers

| Worker | Fits | Avoid |
|---|---|---|
| codex gpt-6-luna | gate and foundation work, event/hot-path, SQL, resumes of its 0.4.0 lanes, drift lanes | being its own reviewer |
| agy-flavio (Gemini 3.8) | template-following lanes (A-mysql on A-postgresql, A-sqltrace-insights) | guard, masking, activation |
| agy-sergio (Gemini 4 Argon, only here) | AST-heavy advisors (C-architecture, C-fastapi) | — |
| agy-sergio (Gemini 3.8, separate quota) | G0 (groundwork now; captures with the owner's go) | — |
| claude-flavio (Opus) | security lanes, U20, councils | long mechanical work |
| Claude subagents | small test-first lanes (P-0.4.1, T-swallowed-2, V-unverified), reviewers of another family | lanes over ~300 source lines |

Councils: `/sharpit:llm-council --tier high` = Opus + codex gpt-6-luna + agy Argon (sergio).

## Execution protocol (the coordinator's loop)

### Step 0: launch (once)

- [ ] Read the spec, this file, `.superpowers/sdd/0.5.0/progress.md` if it exists, `git log` of `release/0.5.0`.
- [ ] Record the provisional decisions (O2 no, O6 yes, O8 no, O9 0.6.0, O10 overnight) and the OWNER-ONLY list (O1,
      O3, O4, O5, O7, O10 push) in the ledger; a lane or task waiting on an owner call does not start.
- [ ] `agentctl.py join`; leases for the reference stack and a MySQL 8.4 container.
- [ ] Create local `release/0.5.0` from `origin/main` in `C:\development\github\sharpit-wt\0.5.0-integration`;
      cherry-pick this plan's commits.
- [ ] Preconditions (council r2 H9), each until merged. First **freeze** `lane/0.4.0-T-unbounded-read` and
      `lane/0.4.0-D3` (ledger line with the head SHA; no worker commits to them after that):
      - re-review the commits after the reviewed SHA on each head (T-unbounded-read `lane/0.4.0-T-unbounded-read`,
        D3 `lane/0.4.0-D3` @ `74aee39` after `290478a`): a fresh reviewer, `review.md` re-stamped with the current head;
      - D3: re-run its two failed overhead budget tests paired lane-vs-base in a quiet window (one full suite at a time,
        no other agent's suite running); a budget is never raised; still red → D3 parks and its rows stay drift;
      - `uv run python scripts/dev/lane_gate.py <lane> --integration C:\development\github\sharpit-wt\0.4.0-integration`
        (the 0.4.0 copy, where their evidence lives) → exit 0, then `git merge --no-ff` into `release/0.5.0`.
- [ ] Create local `base/0.4.1` = `main` + the T-unbounded-read merge commit (never pushed) for P-0.4.1 and
      T-swallowed-2. Before gating either, merge the current `release/0.5.0` into it (council r3 L1: the merge base
      is criss-cross, so the gated diff must hold only the lane's own changes).

### Step 1: per lane

- [ ] Worktree `C:\development\github\sharpit-wt\0.5.0-<lane>` on `lane/0.5.0-<lane>` from the current
      `release/0.5.0` head (resumes: rebase the 0.4.0 branch; P-0.4.1 and T-swallowed-2: from `base/0.4.1`).
- [ ] Brief from `~/.agents/skills/harness-delegation/SKILL.md` + the lane plan + the spec + the background rule +
      "touch only the files your lane plan lists" + PLAN.md §Red rule.
- [ ] Launch in the background; ledger `start <lane> <worker> <model> <time>`.

### Step 2: review (per lane)

- [ ] A fresh reviewer subagent (another family) writes `review.md` in the integration worktree, ending
      `VERDICT: APPROVE|CHANGES`, reviewer id, head SHA; its checklist includes the lane's `## Must-cover` list and,
      for introspecting lanes, the trap test.
- [ ] `/code-review high` + `ponytail-review` on every lane.
- [ ] Each finding → red test first → fix; fix commits re-reviewed. Two failed rounds → park.

### Step 3: merge (one lane at a time)

- [ ] `uv run python scripts/dev/lane_gate.py <lane id> --release 0.5.0` from the `release/0.5.0` copy → exit 0.
- [ ] `git merge --no-ff lane/0.5.0-<lane>`; the four gates on the integration worktree (backgrounded). Red → reset
      the local `release/0.5.0` to the pre-merge SHA.
- [ ] Ledger `merged <lane> <sha> <gate logs>`; the coordinator updates `docs/reference/PARITY.md` (it alone edits it).

### Step 4: per wave, and when G0 lands

- [ ] `npm --prefix ui run build` (never while pytest runs there), static drift, lowest-direct, no-SQLAlchemy,
      coverage, `/sharpit:live-verify` on `examples/fastapi_sqla` and tiny-ledger-py.
- [ ] When G0's fixture commit lands: cherry-pick it and run every `test_post_scan_golden_parity` (they stop skipping)
      and every `test_report_golden_parity` on `release/0.5.0`; update PARITY rows (`unverified (post-scan)` →
      `parity` only when the post-scan test passes, enum values included).

### Step 5: final integration

- [ ] Full gate set; outputs under `.superpowers/sdd/0.5.0/final/`.
- [ ] Merge every lane's `docs.md` into `README.md` / `skills/sharpit/SKILL.md` in one reviewed commit.
- [ ] `PARITY.md`: 31 rows plus the drift rows, counts, no `not started`.
- [ ] `/sharpit:release` prepares the CHANGELOG entry and the version bump, then stops for the owner.
- [ ] Morning report: lane head SHAs (so the owner can push with one command each), parked lanes, rulings, spike
      verdicts, which branch holds which doc change (AGENTS.md rule 4 edit vs a 0.4.1 release), open owner calls.
- [ ] Release every lease; `session-hardening`.

## Ledger format (`.superpowers/sdd/0.5.0/progress.md`)

```
<ISO time> start|review|changes|approve|merged|parked|reset <lane> <worker/model> <sha> <note>
Ruling: <decision> — cost if wrong: <…>
```

## Definition of done

- [ ] Every committed lane merged on `release/0.5.0` through `lane_gate.py`, or parked with its reason.
- [ ] `/sharpit:check` green, plus lowest-direct, no-SQLAlchemy, coverage, the UI build drift check.
- [ ] Every Review Focus line and every `## Must-cover` test exists and is green.
- [ ] Post-scan parity re-run after G0 (if it landed); PARITY rows match the evidence.
- [ ] Spec §14 deviations complete; spike verdicts in `docs/superpowers/spikes/`.
- [ ] CHANGELOG and version prepared, not released. Nothing pushed without the owner, no tag, no publish.
