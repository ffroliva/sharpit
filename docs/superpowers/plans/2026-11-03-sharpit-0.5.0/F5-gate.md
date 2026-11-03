# Lane F5-gate: the merge gate learns 0.5.0

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development, one task at a time,
> `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `F` under today's gate (it is the only id allowed to change `scripts/dev/lane_gate.py`, `lane_gate.py:62,243`); recorded as `F5-gate` in the ledger. Worktree `C:\development\github\sharpit-wt\0.5.0-F5-gate`, branch `lane/0.5.0-F` |
| **Goal** | `lane_gate.py` stops hardcoding 0.4.0 and enforces the 0.5.0 rules: release, foundation-lane ids, per-lane allowed paths, leased-DB mapping, council and must-cover checks. |
| **Spec** | §4.0 |
| **Worker** | codex gpt-6-luna; reviewer Opus |
| **Council** | not required (gate tooling; reviewed by `/code-review high` + `ponytail-review`) |
| **Depends on** | preconditions merged (T-unbounded-read, D3). Gated by **today's** gate: `uv run python scripts/dev/lane_gate.py F --worktree C:\development\github\sharpit-wt\0.5.0-F5-gate` from `release/0.5.0`; today's gate reads evidence from `.superpowers/sdd/0.4.0/lanes/F/`, so this lane's evidence lives there (the only lane that does) |
| **May touch** | `scripts/dev/lane_gate.py`, `tests/scripts/test_lane_gate.py`, `docs/development/workflow.md` (the gate section only), the lane folder `.superpowers/sdd/0.4.0/lanes/F/` |
| **Must NOT touch** | `src/`, every other test |

## Must-cover

`test_lane_gate_release_is_a_parameter`, `test_lane_gate_foundation_lanes_may_change_protected_files`,
`test_lane_gate_allowed_paths_per_lane`, `test_lane_gate_leased_mapping_per_lane`,
`test_lane_gate_refuses_missing_council_verdict`, `test_lane_gate_refuses_shallow_council_file`,
`test_lane_gate_refuses_missing_must_cover_test`.

## Tasks

Each red uses the existing throwaway-repo fixture in `tests/scripts/test_lane_gate.py` (`_fixture`), calls
`lane_gate.evaluate(...)` (`:743`), or `diff_refusals`/`evidence_refusals` directly, and asserts on the returned refusals, so a red is an
`AssertionError` on refusals, never an argparse `SystemExit`. Neutral skeleton: new `Options` fields with defaults
equal to today's behaviour.

### Task 1: release and foundation ids
- [ ] **Step 1:** Red commit:
  - `test_lane_gate_release_is_a_parameter` — `Options(release="0.5.0")` reads evidence from
    `.superpowers/sdd/0.5.0/lanes/<lane>`; expected failure: refusal "missing handoff.md" because the gate looks under
    `0.4.0` (`LANES`, `:41`).
  - `test_lane_gate_foundation_lanes_may_change_protected_files` — lane `F5a` changing `pyproject.toml` with
    `Options(foundation_lanes={"F5a","F5b"})` → no refusal; expected failure: "protected file changed" (`is_f`, `:243`).
- [ ] **Step 2:** `release` defaults from `git rev-parse --abbrev-ref HEAD` of the integration worktree
  (`release/<x>`), else `0.4.0`; `foundation_lanes` default `{"F"}`. Worktree default `WORKTREE_ROOT / f"{release}-{lane}"`.
- [ ] **Step 3:** Green. Commit `feat: lane gate takes the release and foundation lanes as parameters`.

### Task 2: allowed paths and leased mapping
- [ ] **Step 1:** Red commit:
  - `test_lane_gate_allowed_paths_per_lane` — `ALLOWED_PATHS = {"U20-memory": {"pyproject.toml","uv.lock"}}`;
    lane `U20-memory` changing `pyproject.toml` → accepted; lane `C-fastapi` changing it → refused.
  - `test_lane_gate_leased_mapping_per_lane` — `LEASED = {"A-postgresql": ("leased-pg.log",), "A-mysql":
    ("leased-mysql.log",), "A-dbadv-1": ("leased-pg.log","leased-mysql.log")}`; lane `A-mysql` with no
    `gate/leased-mysql.log` → `unverified` entry; expected failure: no entry (today only `A-postgresql`, `:64`, `:769`).
- [ ] **Step 2:** Implement; `leased_pg_problem` generalised to `leased_problem(opts, logs, tests)`; the test-name list
  per lane (`test_read_only_wrapper_rejects_write`, `test_autocommit_engine_is_unavailable`).
- [ ] **Step 3:** Green. Commit `feat: per-lane allowed paths and leased-database evidence in the lane gate`.

### Task 3: council and must-cover
- [ ] **Step 1:** Red commit:
  - `test_lane_gate_refuses_missing_council_verdict` — the lane plan's header row `| **Council** |` starts with
    `required` or `**required**` and `council.md` is absent → refusal naming the file.
  - `test_lane_gate_refuses_shallow_council_file` — `council.md` without a `VERDICT:` line, or naming one model family,
    or without the head SHA → refused.
  - `test_lane_gate_refuses_missing_must_cover_test` — the lane plan lists `test_x` under `## Must-cover`; no test
    function `test_x` at the lane head → refused; present and passing → accepted.
- [ ] **Step 2:** Implement: the plan path comes from the `Lanes` table of
  `docs/superpowers/plans/*-sharpit-<release>/PLAN.md` (column "Plan file", lane id → file; `--plan` overrides); must-cover
  names are backticked `test_*` tokens under that heading, and when the section has paragraphs prefixed `<lane id>:`
  (a file holding two lanes, e.g. `A-database-advisor.md`), only that lane's paragraph counts. Add
  `test_lane_gate_must_cover_reads_lane_paragraph` for that case; presence by `ast` scan of `tests/`, pass by one pytest call with `-k` on those names.
- [ ] **Step 3:** Green + `tests/scripts/` suite (background). Commit `feat: council and must-cover checks in the lane gate`.

## Evidence

`.superpowers/sdd/0.4.0/lanes/F/` (see Depends on): `handoff.md` (the exact command the coordinator uses from now on),
`findings.md`, `field-map.md` (`N/A — not a panel lane`), `checklist.md`.
