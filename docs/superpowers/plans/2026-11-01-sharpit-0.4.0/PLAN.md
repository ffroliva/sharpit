# sharpit 0.4.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. Each lane has its own plan file in this folder;
> steps use checkbox (`- [ ]`) syntax. Run `/sharpit:status` for the next unchecked step; `/sharpit:check` before
> every commit.

**Goal:** sharpit 0.4.0 on `release/0.4.0`: adoptable in a pipeline (report-only, baselines, a GitHub Action,
procurement hygiene), caught up with BootUI 2.2.0 on its 20 panels, and the database panels that carry the pitch.

**Architecture:** One behaviour-neutral foundation commit (file splits, an `implemented` flag on panels, per-panel route
modules, pre-wired hook points, the mechanical merge gate) lets lanes run in parallel in their own worktrees without
touching shared files. Each lane adds its own modules, flips its own `implemented` flag, and merges into
`release/0.4.0` only through `scripts/dev/lane_gate.py`. The safety model, the 0.3.0 report contract and fingerprints
are unchanged.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, SQLAlchemy 2 (optional), pytest + xdist, OpenTelemetry SDK (optional,
test extra), Svelte 5 + TypeScript (`ui/`), uv.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` (r5: r4 council consensus + §5.5 spike findings).
Executors read the spec and their lane plan, nothing else is authoritative.

**Predict verdict:** replaced by the three-family spec council (3 rounds, consensus; spec §15). Ruling (coordinator,
2026-11-01): the release-level predict is the council; lanes D1, B-* run their own `/sharpit:predict` +
`/sharpit:llm-council --tier high` as Task 0. Cost if wrong: a lane-level risk missed until review.

## Global Constraints

Verbatim from AGENTS.md and the spec; every lane's requirements include these.

- Python `>=3.12`; runtime deps exactly `starlette` and `packaging`. `fastapi` and `pydantic-settings` are optional.
- **No GET route and no MCP tool may open a socket, write a file, change a logger level or change `os.environ`** —
  and (spec §4) run SQL, read a file outside the app, call user code or configure ORM mappers.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  verbatim from BootUI with `BootUI`→`sharpit`.
- Safety model 1–6 (AGENTS.md) never regresses; fails closed; secrets masked before any output.
- Architecture rules 1–6 (AGENTS.md); gatekeepers per spec §6.3; ratchets only go down; budgets never raised.
- Each ported test cites `# ported: <BootUI class>.<method>`. A crash is not a red. One condition per assert.
- Conventional commits, explicit `git add` paths, **no AI attribution of any kind**.
- **Never** push or merge `main`, tag, publish, or push any branch tonight. Long commands detached with a timeout and a
  log (codex/agy) or `run_in_background` (Claude).
- `sharpit-report/1` stays; additions only; fingerprints unchanged (`advisors/findings.py:30`).

## Review Focus (cross-lane; each line has a test in the owning lane)

1. **Report-only hides blindness** — a run that is `fail` and has unknown reasons must exit 1 (G1G2:
   `test_report_only_still_fails_on_unknown_reason_when_status_is_fail`).
2. **A partial xdist run writes or trusts a baseline** — `-n 2 -k x --sharpit-write-baseline` refuses; `fixed` is null
   (G1G2: `test_write_baseline_refused_on_partial_xdist_run`).
3. **A parked lane leaves surface** — an `implemented=False` panel is absent from `/panels`, MCP `tools/list`, the CLI,
   the nav and 404s on its path (F: `test_unimplemented_panel_has_no_surface`).
4. **A database panel writes or runs on AUTOCOMMIT** — a write inside `bounded_read_only` is rejected on PostgreSQL;
   an AUTOCOMMIT engine yields `unavailableReason` (A-postgresql: `test_read_only_wrapper_rejects_write`,
   `test_autocommit_engine_is_unavailable`).
5. **A GET configures mappers or runs SQL** — `data` GET under `no_side_effects` with an unconfigured registry
   (A-data: `test_get_never_configures_mappers`).
6. **Autodetection picks the wrong app or imports something** — two FastAPI instances in `sys.modules` → none used,
   candidates printed; detection never imports a module (G6: `test_autodetect_ambiguous_uses_none`,
   `test_autodetect_never_imports`).
7. **The spike's own cases** — each of F1, F2, F3, F5 reproduced in a fixture app; each test asserts the **desired**
   finding, so it is red on 0.3.0 (G6: `test_spike_f3_clean_suite_reaches_green`; T-swallowed-exceptions:
   `test_spike_f1_swallowed_attribute_error_fails`; T-unbounded-read: `test_spike_f2_unbounded_read_found`;
   T-n-plus-one-message: `test_spike_f5_message_names_relationship`).
8. **A swallow gate breaks green 0.3.0 suites** — a broad handler swallowing a `ValueError` is a note, not a failure
   (T-swallowed-exceptions: `test_non_programming_error_swallow_is_a_note`).

## Lanes

| Lane | Plan file | Class | Depends on | Default worker (coordinator decides) |
|---|---|---|---|---|
| F | `F-foundation.md` | committed | — | codex (gpt-6-luna, high) |
| G0a | `G0-goldens-and-tiny-ledger-py.md` §G0a | parallel, never blocking | F | codex (medium) |
| G0b | `G0-goldens-and-tiny-ledger-py.md` §G0b (own repo, not gated by lane_gate) | parallel, never blocking | — | agy (Argon), a different account from G0a |
| D1 | `D1-drift-envelope.md` | committed | F | claude-flavio (Opus) — guard.py |
| G6 | `G6-gate-defaults.md` (spike F3 + F4; owns advisor `SKIPPED`) | committed | F | codex |
| G4 | `G4-hygiene.md` | committed | F | agy (Flash) |
| A-data | `A-data.md` | committed | F | agy (Argon) |
| A-transactions | `A-transactions.md` | committed | F | codex |
| A-sqlalchemy-statistics | `A-sqlalchemy-statistics.md` | committed | F | claude-flavio (Sonnet) |
| A-postgresql | `A-postgresql.md` | committed | F | codex (high) |
| G1G2 | `G1G2-report-only-baselines.md` | committed | F, D1, G6 | codex (high) |
| G3 | `G3-action.md` | committed | G1G2 | claude-flavio (Sonnet) |
| T-n-plus-one-message | `T-n-plus-one-message.md` (spike F5 + F6) | best effort 1 | G1G2, A-sqlalchemy-statistics | codex (high) |
| T-swallowed-exceptions | `T-swallowed-exceptions.md` (spike F1) | best effort 2 | T-n-plus-one-message | claude-flavio (Opus) |
| T-unbounded-read | `T-unbounded-read.md` (spike F2) | best effort 3 | T-swallowed-exceptions | codex |
| A-traces | `A-traces.md` | best effort 4 | F | agy (Argon) |
| A-sqltrace-insights | `A-sqltrace-insights.md` | best effort 5 | F | agy (Flash) |
| B-fastapi-security | `B-fastapi-security.md` | best effort 6 | F | claude-flavio (Opus) |
| B-security-logs | `B-security-logs.md` | best effort 7 | F | claude-flavio (Opus) |
| D2 | `D2-drift-capture.md` | best effort 8 | D1, every A-* merged or parked, B-security-logs if it runs (both edit `fastapi/capture.py`) | agy / codex |
| D3 | `D3-drift-db-runtime.md` | best effort 9 | D1 | agy |
| D4 | `D4-drift-vulns-mcp-restapi.md` | best effort 10 | D1, G1G2 | codex |
| stretch | none yet | stretch | all above merged or parked | plan in-session with `/sharpit:plan` |

This table is the single source for ids and dependencies; a lane header that disagrees is wrong. The T-* lanes are
serial because they share `facts.py`, `gates.py` and `marker.py`.

**Critical path:** F → (D1 ∥ G6 ∥ A-* ∥ G4 ∥ G0a) → G1G2 → G3. Parallelism: at most **four sharpit lanes in flight**
at once (one per worker account), plus G0a/G0b. `agent_capacity.py` before each start.

**Lane evidence (one layout, plan-fixes C2):** the implementer writes `handoff.md`, `findings.md`, `field-map.md`
(`N/A — not a panel lane` outside panels) and `checklist.md` in the lane worktree under
`.superpowers/sdd/0.4.0/lanes/<lane id>/`. The coordinator and reviewer write `review.md`, `gate/<name>.log` and
`live-verify.md` **in the integration worktree only**; a lane diff touching those paths is refused by `lane_gate.py`.

## Execution protocol (the coordinator's loop)

### Step 0: launch (once)

- [ ] Read the spec, this file, `.superpowers/sdd/0.4.0/progress.md` if it exists (resume), `git log` of
      `release/0.4.0`. Trust the ledger and git over recollection.
- [ ] Record **T0** and the owner's wake time (default 07:00 local) in the ledger (spec §10.6).
- [ ] `agentctl.py join` as the coordinator; confirm the global leases for the reference stack (5432, 6379, 9092,
      8080, plus 80/443 for Traefik when G0 needs it).
- [ ] Create `release/0.4.0` from `origin/main` in `C:\development\github\sharpit-wt\0.4.0-integration` (if absent);
      cherry-pick the spec and plan commits from `docs/0.4.0-spec`.
- [ ] Edit issue #24 (keep baselines, point the rest at 0.5.0) and open one issue per committed lane on the 0.4.0
      milestone — `gh` writes to the owner's repo are allowed for issues only.

### Step 1: per lane

- [ ] Worktree `C:\development\github\sharpit-wt\0.4.0-<lane>` on branch `lane/0.4.0-<lane>` from the current
      `release/0.4.0` head; lane folder `.superpowers/sdd/0.4.0/lanes/<lane>/` with `handoff.md` from the template.
- [ ] Brief from `~/.agents/skills/harness-delegation/SKILL.md`'s template + the lane plan path + the spec path + the
      background rule + "touch only the files your lane plan lists". Pick model and effort by the lane's class.
- [ ] Launch in the background; ledger line `start <lane> <worker> <model> <time>`.
- [ ] On completion: read the lane's `handoff.md` and its last commits, not the full log.

### Step 2: review (per lane)

- [ ] A **fresh reviewer subagent** (different model family from the implementer where possible) gets the lane plan,
      the spec sections, `git diff release/0.4.0...lane/0.4.0-<lane>`, and the §6.1 checklist; it writes
      `review.md` **in the integration worktree** (`.superpowers/sdd/0.4.0/lanes/<lane id>/review.md`, never in the
      lane worktree) ending `VERDICT: APPROVE` or `VERDICT: CHANGES` with the reviewer id and the head SHA.
- [ ] `/code-review high` on the lane diff; `ponytail-review` for F, D1, B-*, and anything touching `sqla.py`,
      activation, guard, masking or introspection.
- [ ] Each finding → a fix brief to the implementer: one regression test seen red first per finding, the
      `finding → test → red` row in `findings.md`. Fix commits get their own re-review.
- [ ] Two failed review rounds, or 3 h since start without reaching review → **park** (spec §10.6).

### Step 3: merge (one lane at a time)

- [ ] `uv run python scripts/dev/lane_gate.py <lane id>` **from the `release/0.4.0` copy** (it re-runs the four gates
      at the lane head and writes `gate/*.log` into the integration worktree) → exit 0, else back to Step 2.
- [ ] `git merge --no-ff lane/0.4.0-<lane>` into `release/0.4.0`; the four gates on the integration worktree
      (backgrounded). Red → `git reset --hard <pre-merge sha>` on the local `release/0.4.0`, lane back to Step 2.
- [ ] Ledger: `merged <lane> <sha> <gate log paths>`; update `docs/reference/PARITY.md`.

### Step 4: per wave (after F; after the committed set; at the end)

- [ ] `npm --prefix ui run build` (never while pytest runs there), the static drift check, lowest-direct,
      no-SQLAlchemy, coverage, `/sharpit:live-verify` on `examples/fastapi_sqla` and tiny-ledger-py if up.

### Step 5: final integration (wake time − 90 min; no new lane after wake time − 2 h)

- [ ] Full gate set on `release/0.4.0`; outputs saved under `.superpowers/sdd/0.4.0/final/`.
- [ ] `PARITY.md` counts (parity / unverified / parked / not started).
- [ ] `.superpowers/sdd/0.4.0/morning-report.md`: shipped lanes (sha), parked lanes (reason + handoff path), rulings,
      open findings, the side-by-side check (tiny-ledger-bootui under BootUI vs sharpit on tiny-ledger-py or the
      example app), the token/time spent per worker.
- [ ] Leave the reference stack and tiny-ledger-py running on their leases; release every other lease; list the lane
      worktrees (kept, not removed).
- [ ] `session-hardening` (MemPalace through `~/.mempalace/ops/daemon_write.py`).

## Ledger format (`.superpowers/sdd/0.4.0/progress.md`)

```
<ISO time> start|review|changes|approve|merged|parked|reset <lane> <worker/model> <sha> <note>
Ruling: <decision> — cost if wrong: <…>
```

## Definition of done

- [ ] Every committed lane merged on `release/0.4.0` through `lane_gate.py`, or parked with its reason in the morning
      report (a committed lane parked is a failed night for that lane, reported as such).
- [ ] `/sharpit:check` green on `release/0.4.0` (ruff check, ruff format --check, pyright strict, pytest -n auto),
      plus lowest-direct, no-SQLAlchemy, coverage, the UI build drift check.
- [ ] Every Review Focus line above has its named test, green.
- [ ] Deviations logged in the spec §11; `PARITY.md` and the morning report written.
- [ ] Nothing pushed, no tag, no publish; `main` untouched.
