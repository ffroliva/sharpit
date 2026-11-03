# Lane F5-gate: the merge gate learns 0.5.0

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development, one task at a time,
> `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `F` under today's gate (the only id allowed to change `scripts/dev/lane_gate.py`, `lane_gate.py:62,243`); recorded as `F5-gate` in the ledger. Worktree `C:\development\github\sharpit-wt\0.5.0-F5-gate`, branch `lane/0.5.0-F` |
| **Goal** | `lane_gate.py` stops hardcoding 0.4.0 and enforces the 0.5.0 rules without loosening any current protection: release, reviewer-owned paths per release, per-lane protected files, leased-DB and must-cover checks on full node ids, council checks, and the findings format PLAN.md prescribes. |
| **Spec** | §4.0 |
| **Worker** | codex gpt-6-luna; reviewer Opus |
| **Council** | **required** (council r2 H5: a change to the merge gate). Today's gate does not check `council.md`, so the coordinator checks it by hand before merging this lane, and records that in the ledger |
| **Depends on** | the preconditions merged into `release/0.5.0` (PLAN Step 0). Gated by **today's** gate: `uv run python scripts/dev/lane_gate.py F --worktree C:\development\github\sharpit-wt\0.5.0-F5-gate` from `release/0.5.0`; today's gate reads evidence from `.superpowers/sdd/0.4.0/lanes/F/`, so this lane's evidence lives there |
| **May touch** | `scripts/dev/lane_gate.py`, `tests/scripts/test_lane_gate.py` (**add tests only**: no existing test function changes; the reviewer checks the diff with `git diff -U0` on that file), `docs/development/workflow.md` (the gate section), `.superpowers/sdd/0.4.0/lanes/F/` |
| **Must NOT touch** | `src/`, every other test |

## Must-cover

`tests/scripts/test_lane_gate.py::test_lane_gate_release_is_a_parameter`,
`tests/scripts/test_lane_gate.py::test_lane_gate_refuses_unresolvable_release`,
`tests/scripts/test_lane_gate.py::test_reviewer_owned_paths_follow_release`,
`tests/scripts/test_lane_gate.py::test_protected_allowed_per_lane`,
`tests/scripts/test_lane_gate.py::test_baseline_rekey_only_for_foundation_lanes`,
`tests/scripts/test_lane_gate.py::test_leased_check_uses_full_node_ids`,
`tests/scripts/test_lane_gate.py::test_must_cover_uses_full_node_ids_and_refuses_skips`,
`tests/scripts/test_lane_gate.py::test_council_required_read_per_lane_from_plan_table`,
`tests/scripts/test_lane_gate.py::test_lane_gate_refuses_shallow_council_file`,
`tests/scripts/test_lane_gate.py::test_findings_accept_pin_and_na_rows`,
`tests/scripts/test_lane_gate.py::test_existing_protections_still_refuse`.

## Tasks

Each red uses the existing throwaway-repo fixture in `tests/scripts/test_lane_gate.py` (`_fixture`), calls
`lane_gate.evaluate(...)` (`:743`), or `diff_refusals`/`evidence_refusals`/`_findings_refusals` directly, and asserts on
the returned refusals, so a red is an `AssertionError`, never an argparse `SystemExit`. Neutral skeleton: new
`Options` fields with defaults equal to today's behaviour.

### Task 1: release, reviewer-owned paths
- [ ] **Step 1:** Red commit:
  - `test_lane_gate_release_is_a_parameter` — `Options(release="0.5.0")` reads evidence from
    `.superpowers/sdd/0.5.0/lanes/<lane>`; expected failure: "missing handoff.md" (`LANES`, `:41`).
  - `test_lane_gate_refuses_unresolvable_release` — detached integration HEAD and no `--release` → refused with a
    message (not a silent fall-back to 0.4.0).
  - `test_reviewer_owned_paths_follow_release` — with `release="0.5.0"`, a lane diff adding
    `.superpowers/sdd/0.5.0/lanes/X/review.md` (or `live-verify.md`, `gate/pytest.log`) is refused; expected failure:
    accepted (`REVIEWER_OWNED` built from the 0.4.0 `LANES`, `:67`).
- [ ] **Step 2:** `release` from `--release`, else from the integration branch name `release/<x>`, else refuse;
  `REVIEWER_OWNED` and the worktree default built from it.
- [ ] **Step 3:** Commit `feat: lane gate takes the release; reviewer-owned paths follow it`.

### Task 2: protected files per lane, baseline re-key, leased evidence
- [ ] **Step 1:** Red commit:
  - `test_protected_allowed_per_lane` — `PROTECTED_ALLOWED` in the gate: `F` (today's `F_MAY_CHANGE`), `F5a-harness`:
    `{tests/conftest.py, pyproject.toml, uv.lock, tests/engine/test_import_boundary.py, src/sharpit/settings.py}`,
    `F5b`: `{tests/engine/test_import_boundary.py}`, `U20-memory`: `{pyproject.toml, uv.lock, src/sharpit/settings.py}`,
    `W-workload`: `{pyproject.toml, uv.lock}`. One parametrised case per entry: allowed for that lane, refused for
    `C-fastapi`. (Entries for U20/W are inert until the owner's O3/O4/O5 let those lanes build.)
  - `test_baseline_rekey_only_for_foundation_lanes` — `_baseline_refusals` takes the foundation flag (today
    `lane == "F"`, `:216`): `F5a-core` may re-key moved code with the total not rising; `C-fastapi` may not.
  - `test_leased_check_uses_full_node_ids` — `LEASED` maps lane → `(log name, (full node ids,))`:
    `A-postgresql` → `leased-pg.log`, its two existing node ids; `F5b` → `leased-mysql.log`,
    `tests/fastapi/test_mysql_read_only_leased.py::test_mysql_read_only_wrapper_rejects_write`; `A-mysql` →
    `leased-mysql.log`, `tests/fastapi/test_mysql_leased.py::test_read_only_wrapper_rejects_write` and
    `::test_full_read_against_mysql_84`; `A-dbadv-1` → `leased-pg.log` + `leased-mysql.log`,
    `tests/fastapi/test_database_advisor_leased.py::...` node ids; `A-dbadv-2` → the vendor-rule node ids. A log
    line `tests/engine/test_sqla_read_only.py::test_read_only_wrapper_rejects_write PASSED` does **not** satisfy
    A-mysql (expected failure today: the regex `::{name}\s+PASSED`, `:385-387`, accepts it).
- [ ] **Step 2:** Implement; `leased_pg_problem` → `leased_problem(opts, log, node_ids)`; non-leased tests (e.g.
  `test_autocommit_engine_is_unavailable`) leave the leased list.
- [ ] **Step 3:** Commit `feat: per-lane protected files and node-id leased evidence in the lane gate`.

### Task 3: council and must-cover
- [ ] **Step 1:** Red commit:
  - `test_council_required_read_per_lane_from_plan_table` — PLAN.md's Lanes table has a `Council` column; the lane's
    row says `required` and `council.md` is absent → refused. Multi-lane plan files (`F5a-foundation.md`,
    `A-database-advisor.md`) resolve per lane id from the table, not from the file header.
  - `test_lane_gate_refuses_shallow_council_file` — no `VERDICT:` line, one model family, or no head SHA → refused.
  - `test_must_cover_uses_full_node_ids_and_refuses_skips` — the lane's `## Must-cover` paragraph (prefixed
    `<lane id>:` in multi-lane files) lists tests; a full node id is used as is, a bare name is resolved only among the
    test files in the lane's diff and refused if absent or ambiguous; each must exist and pass at the lane head. A skipped one
    is refused unless (a) it is in the lane's `LEASED` list (then the leased check decides), or (b) its skip reason
    starts `post-scan golden absent` (then the gate reports it `unverified`, not refused).
- [ ] **Step 2:** Plan path from PLAN.md's "Plan file" column (`--plan` overrides); presence by `ast` scan of the named
  file; pass by one pytest call on the exact node ids with `-rs` to read skip reasons.
- [ ] **Step 3:** Commit `feat: council and must-cover checks in the lane gate`.

### Task 4: findings format
- [ ] **Step 1:** Red commit `test_findings_accept_pin_and_na_rows` — a `findings.md` table with the PLAN.md header
  (`finding | test (node id) | red SHA | red output | disposition`) and rows `fixed`, `pin: reverted X, failed on Y`,
  `N/A — deletion`, `parked: reason` → no refusal; `pin:` with no mutation text, or `N/A` with no reason → refused.
  Expected failure: pin and N/A rows refused today (`_findings_refusals`, `:316-334`, accepts only `fixed`/`parked`).
- [ ] **Step 2:** Implement; a `pin` or `N/A` row needs no red SHA and is not replayed.
- [ ] **Step 3:** `test_existing_protections_still_refuse` — mutation guard over today's refusals (protected file by a
  non-foundation lane, raised budget, crash red, missing review verdict) all still refused. Full `tests/scripts/` suite
  (background). Commit `feat: lane gate accepts pin and N/A findings rows`.

## Evidence

`.superpowers/sdd/0.4.0/lanes/F/` (today's gate checks it, so its `findings.md` uses only `fixed`/`parked`
dispositions in a `Disposition` column; pins go in `handoff.md`): `council.md`, `handoff.md` (the exact command the coordinator uses from now on),
`findings.md`, `field-map.md` (`N/A — not a panel lane`), `checklist.md`.
