# sharpit 0.5.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. Each lane has its own plan file in this folder;
> steps use checkbox (`- [ ]`) syntax. Run `/sharpit:status` for the next unchecked step; `/sharpit:check` before
> every commit.

**Goal:** sharpit 0.5.0 on `release/0.5.0`: every BootUI 2.2.0 panel id answered (eight panels: two resumes, six new),
the two unverified panels settled, and the benchmark's inside-panel gaps closed where a spike says they fit.

**Architecture:** One behaviour-neutral foundation (F5: SQLAlchemy gatekeeper package, the shared app-source AST
layer, the shared advisor scan core, pre-created settings, a lane-gate council check) lets panel lanes run in parallel
on disjoint files. 0.4.0 already left each panel a stub route, tool module, `IMPLEMENTED` flag and Svelte placeholder;
each lane fills its own and flips its flag. Merges go through `scripts/dev/lane_gate.py` only. Safety model, report
contract (`sharpit-report/1`, additive) and fingerprints unchanged.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, SQLAlchemy 2 (optional), stdlib `ast`/`tomllib`/`tracemalloc`/`gc`,
pytest + xdist, Svelte 5 + TypeScript (`ui/`), uv.

**Spec:** `docs/superpowers/specs/2026-11-03-sharpit-0.5.0-design.md` (r1). The 0.4.0 spec governs what it does not
change (§4 anti-goals, §6.1 definition of done, §6.4 database access).

**Predict verdict:** CAUTION 6/10 (`predict.md`). Scenarios: `scenario.md` (41 rows; must-cover list per lane).

## Global Constraints

Verbatim from AGENTS.md and the spec; every lane's requirements include these.

- Python `>=3.12`; runtime deps exactly `starlette` and `packaging`. `fastapi` and `pydantic-settings` are optional.
- **No GET route and no MCP tool may open a socket, write a file, change a logger level or change `os.environ`** —
  and (0.4.0 spec §4) run SQL, read a file outside the app, call user code or configure ORM mappers. 0.5.0 adds: or
  start `tracemalloc`, append to `gc.callbacks`, or open an application source file.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  verbatim from BootUI with `BootUI`→`sharpit`.
- Safety model 1–6 (AGENTS.md) never regresses; fails closed; secrets masked before any output.
- Architecture rules 1–6 (AGENTS.md); gatekeepers per spec §9; ratchets only go down; budgets never raised.
- Each ported test cites `# ported: <BootUI class>.<method>`. A crash is not a red. One condition per assert.
- Conventional commits, explicit `git add` paths, **no AI attribution of any kind**.
- Never push or merge `main`, tag or publish. Lane branches pushed only if the owner allows (spec §13 O10). Long
  commands detached with a timeout and a log (codex/agy) or `run_in_background` (Claude).

## Review Focus (cross-lane; each line has a test in the owning lane)

1. **An unimplemented 0.5.0 panel leaks surface** (F5: `test_unimplemented_panel_has_no_surface_05`).
2. **SQLAlchemy imported outside its gatekeeper after the split** (F5: `test_sqla_package_is_the_only_sqlalchemy_importer`
   and the planted violation from `engine/collectors/`).
3. **Introspection calls user code** (R-fastapi-security, B-security, C-fastapi:
   `test_introspection_never_reads_or_calls_custom_route_attributes`).
4. **A GET after a scan opens a source file or runs SQL** (each advisor: `test_get_after_scan_opens_no_source_file`;
   A-mysql, A-database-advisor: `test_<id>_get_no_side_effects`).
5. **A violation leaks the secret it found** (B-security: `test_violation_never_contains_literal_secret`).
6. **A database scan writes or runs on AUTOCOMMIT** (A-mysql, A-database-advisor: `test_read_only_wrapper_rejects_write`,
   `test_autocommit_engine_is_unavailable`, leased MySQL/PostgreSQL).
7. **The transactions ring grows without bound** (R-transactions: `test_ring_stays_bounded_when_every_entry_is_open`).
8. **Memory instrumentation leaks into the host** (U20: `test_get_leaves_tracing_and_gc_callbacks_untouched`).
9. **The workload opens a socket or is reachable from a GET/MCP** (W-workload: `test_workload_opens_no_socket`,
   `test_workload_not_reachable_from_get_or_mcp`).

## Lanes

| Lane | Plan file | Class | Depends on | Worker (coordinator decides; this is the fit) |
|---|---|---|---|---|
| T-unbounded-read (0.4.x) | `../2026-11-01-sharpit-0.4.0/T-unbounded-read.md` (already built; coordinator review + gate) | precondition | — | coordinator (Opus) review, codex fixes |
| F5 | `F5-foundation.md` | committed, 1st | T-unbounded-read merged (or F5 rebases onto it) | codex gpt-6-luna (high); council (Opus + codex + agy Argon) on §4.1 |
| G0 | `G0-goldens.md` (reference repo; only fixture files land here) | parallel, never blocking; owner-gated (O1) | — | agy-sergio, Gemini 3.8 slot (Argon stays free for C-architecture) |
| R-transactions | `R-transactions.md` | committed | F5 | codex gpt-6-luna (the original implementer; reviewer: Opus, another family) |
| R-fastapi-security | `R-fastapi-security.md` (Council: required) | committed | F5 | claude-flavio (Opus) |
| A-mysql | `A-mysql.md` | committed | F5 | agy-flavio, Gemini 3.8 (A-postgresql is the template) |
| C-architecture | `C-architecture.md` | committed | F5 | agy-sergio, Gemini 4 Argon |
| P-0.4.1 | `P-0.4.1.md` (test-first; tiny) | committed | — (from `main` if O7 = 0.4.1, else F5) | Claude subagent (Sonnet-class) |
| T-swallowed-2 | `T-swallowed-2.md` (test-first; tiny) | committed | P-0.4.1 (R0: `gates.py`) | Claude subagent |
| B-security-logs | `B-security-logs.md` (Council: required) | committed | R-transactions (R0: `fastapi/capture.py`) | codex gpt-6-luna |
| B-security | `B-security.md` (Council: required) | committed | R-fastapi-security (R0: `introspector.py`, `spi.py`) | claude-flavio (Opus) |
| A-database-advisor | `A-database-advisor.md` | committed | R-transactions (R0: `engine/sqla/`), A-mysql (shares the leased MySQL and the vendor SQL style) | codex gpt-6-luna (high) |
| C-fastapi | `C-fastapi.md` | committed | C-architecture (worker), B-security (R0: `introspector.py` read helper) | agy-sergio, Gemini 4 Argon |
| V-unverified | `V-unverified.md` | committed | G0 (if it delivers), A-database-advisor not needed | Claude subagent |
| U20-memory | `U20-memory.md` (spike → owner O3/O4 → build) | gated | T-swallowed-2 (R0: `facts.py`, `session.py`), B-security-logs (R0: `fastapi/capture.py`) | claude-flavio (Opus) |
| T-unbounded-read-2 | `T-unbounded-read-2.md` (spike → build or log) | gated | T-unbounded-read on main; U20-memory (R0: capture middleware, `facts.py`) | codex gpt-6-luna |
| W-workload | `W-workload.md` (spike → owner O5 → build) | gated | U20-memory (R0: `pytest_plugin/options.py`) | codex gpt-6-luna or claude-flavio |
| final | Step 5 below | — | all above merged or parked | coordinator |

This table is the single source for ids and dependencies; a lane header that disagrees is wrong.

**Rule R0: two lanes whose May-touch lists intersect never run at the same time.** Before starting a lane, compare
its May-touch list with every lane in flight; any overlap → wait. Known chains:

| Shared file(s) | Chain (order) |
|---|---|
| `engine/sqla/` (after F5; `engine/sqla.py` before) | T-unbounded-read → F5 → R-transactions → A-database-advisor |
| `fastapi/capture.py` | R-transactions → B-security-logs → U20-memory → T-unbounded-read-2 |
| `fastapi/introspector.py`, `engine/spi.py` | R-fastapi-security → B-security → C-fastapi |
| `engine/testsession/facts.py`, `gates.py`, `pytest_plugin/session.py`, `marker.py` | P-0.4.1 → T-swallowed-2 → U20-memory → T-unbounded-read-2 |
| `pytest_plugin/options.py` | U20-memory → W-workload |
| `engine/appsource.py`, `engine/advisors/scan.py`, `engine/advisors/registry.py`, `settings.py` | F5 only; consumers never edit (a needed change is a coordinator fix commit on `release/0.5.0`, then the lane rebases) |
| `ui/src/lib/panels04/index.ts`, `nav.ts`, `App.svelte`, `types.ts` | nobody (0.4.0 O4: flag files only) |
| `src/sharpit/__init__.py` | B-security-logs only (`record_security_event` export) |

A-mysql edits no `engine/sqla/` file (the MySQL branch of `bounded_read_only` exists, `sqla.py:644`); if it needs one,
it joins the `engine/sqla/` chain after R-transactions.

**Critical path:** T-unbounded-read merge → F5 (+ council) → R-transactions → A-database-advisor, about 3 lane-lengths.
**Start order after F5 (four code slots, one per account):** codex R-transactions, claude-flavio R-fastapi-security,
agy-flavio A-mysql, agy-sergio (Argon) C-architecture; Claude subagents run P-0.4.1 then T-swallowed-2 (test-first,
small) and agy-sergio's Gemini 3.8 slot runs G0 in the reference repo. As slots free: codex B-security-logs then
A-database-advisor; claude-flavio B-security; agy-sergio C-fastapi; Claude subagent V-unverified. The gated lanes start
only after their spike verdict and the owner's call, and never ahead of a committed lane.

**Leased-database evidence:** the coordinator runs A-mysql's and A-database-advisor's leased tests itself
(`agentctl lease database`, a MySQL 8.4 container and the reference compose's PostgreSQL) and writes
`gate/leased-mysql.log` / `gate/leased-pg.log`; skipped = unverified (not committed-done).

**Lane evidence (0.4.0 C2 layout):** the implementer writes `handoff.md`, `findings.md`, `field-map.md`
(`N/A — not a panel lane` outside panels), `checklist.md` and, for `Council: required` lanes, `council.md`, in the lane
worktree under `.superpowers/sdd/0.5.0/lanes/<lane id>/`. The coordinator and reviewer write `review.md`,
`gate/<name>.log` and `live-verify.md` **in the integration worktree only**; a lane diff touching those paths is
refused by `lane_gate.py`.

**What `lane_gate.py` checks (0.4.0 rules, release-parametrised by F5):** every red test named in `findings.md` has a
committed red SHA that is an ancestor of the head; replayed at that SHA in a fresh tree it fails with an
`AssertionError` whose last frame is under `tests/` (a crash, a pass or an assert in `src/` is refused); the test is
unchanged from the red SHA to the head and passes at the head; the four gates re-run at the head; `review.md` ends
`VERDICT: APPROVE` with a reviewer id other than the implementer's and the head SHA; `checklist.md` has an evidence
path or `N/A` + reason per item; the complexity baseline only went down; and (F5) `council.md` exists when the lane
header says `Council: required`. `findings.md` rows:

```
| finding | test (node id) | red SHA | red output (last assertion line) | status (fixed / parked: reason / N/A — deletion) |
```

A test that passed first time is recorded as a pin with its mutation (what was reverted in a scratch tree, the
assertion it then failed on); it is never claimed as a red.

## Workers

| Worker | Fits | Avoid |
|---|---|---|
| codex gpt-6-luna | event/hot-path work, SQL, resumes of its own 0.4.0 lanes (A-transactions, T-unbounded-read), F5's mechanical split | being its own reviewer |
| agy-flavio (Gemini 3.8) | template-following panel lanes (A-mysql on A-postgresql) | guard, masking, activation |
| agy-sergio (Gemini 4 Argon — only here) | the AST-heavy advisors (C-architecture, C-fastapi) | — |
| agy-sergio (Gemini 3.8, separate quota) | G0 in the reference repo | — |
| claude-flavio (Opus) | security lanes (R-fastapi-security, B-security), memory instrumentation (U20), councils | long mechanical work |
| Claude subagents | test-first small lanes (P-0.4.1, T-swallowed-2, V-unverified), reviewers (a family other than the implementer's) | lanes over ~300 lines of source |

Councils: `/sharpit:llm-council --tier high` = Opus + codex gpt-6-luna + agy Argon (sergio).

## Execution protocol (the coordinator's loop)

### Step 0: launch (once)

- [ ] Read the spec, this file, `.superpowers/sdd/0.5.0/progress.md` if it exists (resume), `git log` of
      `release/0.5.0`. Trust the ledger and git over recollection.
- [ ] Owner answers to spec §13 recorded in the ledger; a lane whose question is open does not start.
- [ ] T-unbounded-read: coordinator review → `lane_gate.py T-unbounded-read` on the 0.4.0 integration copy → merged to
      `main` by the owner (or carried into `release/0.5.0` per O7).
- [ ] `agentctl.py join` as the coordinator; leases for the reference stack and a MySQL 8.4 container.
- [ ] Create `release/0.5.0` from `origin/main` in `C:\development\github\sharpit-wt\0.5.0-integration`; cherry-pick
      this plan's commits.

### Step 1: per lane

- [ ] Worktree `C:\development\github\sharpit-wt\0.5.0-<lane>` on branch `lane/0.5.0-<lane>` from the current
      `release/0.5.0` head (resumes: rebase the 0.4.0 lane branch onto it, recorded in `handoff.md`).
- [ ] Brief from `~/.agents/skills/harness-delegation/SKILL.md` + the lane plan + the spec + the background rule +
      "touch only the files your lane plan lists".
- [ ] Launch in the background; ledger `start <lane> <worker> <model> <time>`.

### Step 2: review (per lane)

- [ ] A fresh reviewer subagent (another model family) gets the lane plan, the spec sections, the lane diff and the
      0.4.0 §6.1 checklist; writes `review.md` in the integration worktree ending `VERDICT: APPROVE|CHANGES`, reviewer
      id, head SHA.
- [ ] `/code-review high` + `ponytail-review` on every lane (owner rule: lane review = code-review + ponytail-review).
- [ ] Each finding → a red test first → fix; `finding → test → red` row in `findings.md`; fix commits re-reviewed.
      A red that crashed or passed is re-redded or mutation-proven, never accepted by ruling.
- [ ] Two failed review rounds → park with the reason.

### Step 3: merge (one lane at a time)

- [ ] `uv run python scripts/dev/lane_gate.py <lane id>` from the `release/0.5.0` copy → exit 0.
- [ ] `git merge --no-ff lane/0.5.0-<lane>`; the four gates on the integration worktree (backgrounded). Red → reset
      the local `release/0.5.0` to the pre-merge SHA, lane back to Step 2.
- [ ] Ledger `merged <lane> <sha> <gate logs>`; update `docs/reference/PARITY.md`.

### Step 4: per wave

- [ ] `npm --prefix ui run build` (never while pytest runs there), static drift, lowest-direct, no-SQLAlchemy,
      coverage, `/sharpit:live-verify` on `examples/fastapi_sqla` and tiny-ledger-py.

### Step 5: final integration

- [ ] Full gate set on `release/0.5.0`; outputs under `.superpowers/sdd/0.5.0/final/`.
- [ ] Merge every lane's `docs.md` into `README.md` / `skills/sharpit/SKILL.md` in one reviewed commit.
- [ ] `PARITY.md`: 31 rows, counts, no `not started`.
- [ ] Report: shipped lanes (sha), parked lanes (reason + handoff path), rulings, open findings, spike verdicts.
- [ ] Release every lease; `session-hardening`.

## Ledger format (`.superpowers/sdd/0.5.0/progress.md`)

```
<ISO time> start|review|changes|approve|merged|parked|reset <lane> <worker/model> <sha> <note>
Ruling: <decision> — cost if wrong: <…>
```

## Definition of done

- [ ] Every committed lane merged on `release/0.5.0` through `lane_gate.py`, or parked with its reason.
- [ ] `/sharpit:check` green on `release/0.5.0`, plus lowest-direct, no-SQLAlchemy, coverage, the UI build drift check.
- [ ] Every Review Focus line and every must-cover test in `scenario.md` exists and is green.
- [ ] Deviations logged in the spec §14; `PARITY.md` updated; spike verdicts in `docs/superpowers/spikes/`.
- [ ] Nothing pushed to `main`, no tag, no publish.
