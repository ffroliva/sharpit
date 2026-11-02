# Lane F, Task 4: lane gate handoff

Implementer: claude-subagent-F-gate (resumed after the Codex worker hit its usage limit)
Branch / worktree: `lane/0.4.0-F-gate` in `C:\development\github\sharpit-wt\0.4.0-F-gate`, from lane F head `0cc440a`.
Files: `scripts/dev/lane_gate.py`, `tests/scripts/test_lane_gate.py`, `.superpowers/sdd/0.4.0/handoff-template.md`, this file.

## Commits

| Commit | Kind |
|---|---|
| `910b516a1791ff6022044a49e2471989a921a6f2` | `test: pin lane gate refusal contracts` (red, wrong-value stubs) |
| `e3c14fbd6cf8b872cb86a1b8dcbe3b642e0333c6` | `feat: add mechanical 0.4 lane merge gate` |
| `25ab62d7ce9a443938b8cdcae11bd50bcdaf57df` | `test: pin real pytest junit shapes for red replay` (red, found by replaying F's reds) |
| `4456c0ad49af278500c94c9d53ad4843fc696b29` | `fix: classify replayed reds by the failing exception class` |
| `f4b7deb5f6b7ee366f261e91d5dc97beb87cb241` | `test: pin assert-message and type-attribute reds` (red, coordinator note) |
| `09982c530d3ea89473513ca4d3017ba433c3e902` | `fix: accept assert-message and typed AssertionError reds` |
| `fd63da05523f0def5abea858a665ff81b0e22d61` | `test: pin code-span cells and parametrized red ids` (red, found replaying F at `d37c6f2`) |
| `f58a5be3b6b569082ef5f77aa8aef728291ed4d7` | `fix: read red ids from code spans and match every parametrisation` |

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/scripts/test_lane_gate.py::test_lane_gate_accepts_complete_evidence` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert fx.gate_calls == ["ruff-check", "ruff-format", "pyright", "pytest"]` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_main_exits_zero_only_when_accepted` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert lane_gate.main(argv) == 1` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_missing_verdict_or_wrong_reviewer_or_sha` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), needle)` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_missing_field_map_handoff_or_checklist` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), f"missing evidence: {missing}")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_checklist_item_without_evidence` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(result, "checklist.md: item 1 has no existing evidence path")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_unresolved_finding` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), "findings.md: unresolved finding")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_gate_log_for_other_sha` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), "gate/lowest-direct.log does not name head")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_protected_diff` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), needle)` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_complexity_baseline_increase` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), "complexity baseline")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_when_rerun_gate_fails` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(result, "gate ruff-check failed")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_no_rerun_refused_for_real_lane` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(result, "--no-rerun")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_sha_that_is_not_worktree_head` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(result, "is not the worktree HEAD")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_fake_red` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), f"red {TEST_ID}: passed at red SHA")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_error_as_red` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(result, f"red {TEST_ID}: {needle}")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_collection_error_as_red` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), f"red {TEST_ID}: not collected at red SHA")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_red_that_does_not_pass_at_head` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), f"red {TEST_ID}: does not pass at head")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_missing_red_test` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), f"red {ghost}: test missing at red SHA")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_unknown_or_foreign_red_sha` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(result, "red SHA deadbeef is unknown")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_lane_without_red_tests` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), "no red tests recorded")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_red_test_changed_after_red_commit` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), f"red {TEST_ID}: test body changed after red commit")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_needs_accept_unverified_for_non_pytest_red` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), f"red {vitest}: not a pytest test")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_postgresql_without_leased_db_log` | `910b516a1791ff6022044a49e2471989a921a6f2` | `assert _refused(fx.evaluate(), "leased-pg")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_accepts_rewritten_assert_failure_as_red` | `25ab62d7ce9a443938b8cdcae11bd50bcdaf57df` | `assert _refusals(fx.evaluate()) == []` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_non_assertion_failure_with_assert_like_message` | `25ab62d7ce9a443938b8cdcae11bd50bcdaf57df` | `assert _refused(fx.evaluate(), f"red {TEST_ID}: RpcError failure")` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_replays_with_long_tracebacks` | `25ab62d7ce9a443938b8cdcae11bd50bcdaf57df` | `assert "--tb=long" in calls[0]` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_accepts_assert_message_or_type_without_traceback` | `f4b7deb5f6b7ee366f261e91d5dc97beb87cb241` | `assert _refusals(fx.evaluate()) == []` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_reads_first_code_span_and_parametrized_ids` | `fd63da05523f0def5abea858a665ff81b0e22d61` | `assert _refusals(fx.evaluate()) == []` |

Controls that passed against the stub, by design (they assert acceptance): `test_lane_gate_allows_only_decreasing_complexity_baseline`,
`test_lane_gate_allows_pyproject_change_outside_dependency_lists`, `test_lane_gate_lets_lane_f_rekey_baseline_without_raising_total`,
`test_lane_gate_no_rerun_skips_gates_for_fixture_lane`, `test_lane_gate_ignores_changes_outside_the_red_test_body`,
`test_lane_gate_accepts_postgresql_with_leased_db_log`. Every row above failed with an `AssertionError` at its red SHA.
The test fixture repo sets `core.hooksPath` to an empty folder before the red commit: the owner's global hooks took ~3 s
a commit, which made the file run take 3 minutes.

## CLI

Run the `release/0.4.0` copy from the integration worktree:

```bash
uv run python scripts/dev/lane_gate.py <lane-id> [--worktree PATH] [--sha SHA] [--integration PATH] [--accept-unverified]
```

Defaults: worktree `C:\development\github\sharpit-wt\0.4.0-<lane-id>`, its HEAD, integration = cwd. Prints
`REFUSED: <reason>` per refusal, `unverified: <reason>` per accepted gap, then `lane <id> @ <sha>: ACCEPTED|REFUSED`.
Exit 0 only on ACCEPTED. `--no-rerun` skips the four gates and is refused for any lane id that does not start with
`test-fixture`.

What it checks, in order (the red replays and the four gates run only when the cheap checks found nothing):

1. **Worktree:** `--sha` is the lane worktree's HEAD and it has no uncommitted tracked changes (so the gate checks the
   commit the implementer means; the gates themselves run in a fresh tree, step 8).
2. **Diff** `merge-base(integration HEAD, sha)..sha`: refuses `lanes/*/review.md`, `lanes/*/live-verify.md`,
   `lanes/*/gate/**`; `scripts/dev/lane_gate.py`, `sonar-baseline.txt`, `tests/engine/test_import_boundary.py`,
   `uv.lock`; a `pyproject.toml` change to `project.dependencies`, `optional-dependencies`, `dependency-groups` or
   `build-system.requires` (other pyproject edits pass); any changed `BUDGET*` top-level assignment in a `.py` file;
   `tests/complexity_baseline.json` with an added key or a raised value (F1c). Lane id `F` may change the gate,
   import-boundary, `uv.lock` and `pyproject.toml`, and may re-key the baseline when the total does not rise.
3. **Evidence (C2)** read from the lane head with `git show`: `handoff.md` (and the lane diff touched it),
   `findings.md`, `field-map.md`, `checklist.md`. Checklist: rows for items 1–10, each with `N/A — <reason>` or a
   backticked path that exists in the lane head or the integration worktree (`::test` and `:line` suffixes are
   stripped). Findings: every row with a `Disposition` column starts `Fixed` (and names a test) or `Parked` plus a
   reason.
4. **Review** in the integration worktree `lanes/<lane>/review.md`: last non-blank line `VERDICT: APPROVE`, the head
   SHA (full, or a prefix of 7+ characters) somewhere in it, a `Reviewer: <id>` line, and that id differs from the
   handoff's `Implementer: <id>` line, which is required. `gate/lowest-direct.log` and `gate/no-sqlalchemy.log` must
   name the head SHA on line 1 and contain an `exit 0` line.
5. **Red integrity:** every `(test, red SHA)` from any table with a `Test id`/`Test` column and a column whose header
   contains `Red SHA` (any case) in `findings.md` and `handoff.md` (short SHAs are fine). Refuses: a row naming a test
   with a blank Red SHA (unless its Disposition is `Parked`); a findings table (has `Disposition`) with no Red SHA
   column; no reds at all; unknown SHA (`n/a` included); SHA not an ancestor of head; SHA already in the integration
   branch (not a lane commit); test function missing at the red SHA or head; the function's source (decorators
   included, via `ast`) differing between red SHA and head; the function identical at the merge-base (the lane did not
   add or change it); anything in the red test's file other than newly added top-level test functions changed after
   the red SHA (constants, parametrize lists, helpers, fixtures, other tests); any `conftest.py` on the test's path
   changed after the red SHA. Non-pytest ids (Vitest) are `unverified`.
6. **Red replay (R2):** per red SHA a `git worktree add --detach` in a temp folder (removed afterwards), then
   `uv run --project <integration> --frozen python -m pytest -q -p no:cacheprovider -p no:randomly --tb=long
   --junitxml=... <ids>` with `PYTHONPATH=<tree>/src;<tree>` so the replayed tree's code shadows the editable
   install. Accepts only a `<failure>` whose exception class is `AssertionError` raised from the red test's own file
   (the `--tb=long` last line names the file; an `assert` inside `src/` is a disguised stub); refuses pass, `<error>`,
   skip, not collected, another exception, or an `AssertionError` from another file. Then the same ids must pass at
   head (same method).
7. **R7:** lane `A-postgresql` needs `gate/leased-pg.log` with the head SHA on line 1 and both
   `test_read_only_wrapper_rejects_write` and `test_autocommit_engine_is_unavailable` as `::<name> PASSED`.
8. **Four gates** in a fresh `git worktree add --detach <head>` temp tree (removed and pruned in `finally`), never the
   implementer's tree: first `uv sync --frozen --extra test` builds that tree's own `.venv` from the lane's lock
   (`gate/uv-sync.log`; a failure refuses), then `uv run --no-sync ruff check`, `... ruff format --check`,
   `... pyright`, `... pytest -q -n 4` (timeouts 900 sync, 300/300/900/1800 s). Each writes
   `<integration>/.superpowers/sdd/0.4.0/lanes/<lane>/gate/<name>.log` (`ruff-check`, `ruff-format`, `pyright`,
   `pytest`), head SHA on line 1, then the command, exit code and output.

## Decisions

- **Exception class, not message prefix.** The plan says "a `<failure>` whose message starts with `AssertionError`".
  Replaying F's real reds showed pytest's junit `message` for a rewritten `assert` is `assert 1 == 2`, with no
  exception name, so the literal rule refuses every real red. The gate replays with `--tb=long`, whose last traceback
  line is `<file>:<line>: <ExceptionClass>`, and requires that class to be `AssertionError` (falling back to the
  `type` attribute, then to a message starting `AssertionError` or `assert `, per the coordinator's note). The intent
  (refuse errors and non-assertion failures) is unchanged; red commits `25ab62d`, `f4b7deb`.
- **Table cells:** the test and red-SHA values are the first `code span` in the cell, so notes after it
  (`` `test_x` (7 params) ``, `` `sha` (parent of fix `...`) ``) are fine. A bare function id matches every
  parametrisation: at the red SHA all of them must fail with `AssertionError`, at head all must pass. A `[param]` id
  matches that case only. A non-SHA value such as `n/a` is refused as an unknown SHA (it is not silently skipped).
- **`--accept-unverified` also covers non-pytest reds.** The plan only names it for the leased database. A Vitest red
  cannot be replayed by a pytest runner; the gate refuses it unless the coordinator passes `--accept-unverified`, which
  prints `unverified: ...`. The gate prints the ledger word; it does not write `progress.md` (the coordinator owns it).
- **The gates run in a fresh detached tree with a freshly synced env** (round 1, finding 4). I chose `uv sync --frozen
  --extra test` in the temp tree over reusing the integration venv through `UV_PROJECT_ENVIRONMENT`: a lane can
  change the lock (F adds `psycopg[binary]`), so the integration venv is not equivalent. `VIRTUAL_ENV` and
  `UV_PROJECT_ENVIRONMENT` are dropped from the subprocess env so a caller's venv cannot stand in. The cost is one sync
  per gate run (minutes with `UV_LINK_MODE=copy`). Replays still use the integration environment, as R2 says.
- **Message fallback keeps the frame file unknown.** Without a `--tb=long` tail (never seen from real pytest) the
  `type` attribute or an `assert ` message is still accepted as `AssertionError`, per the coordinator's earlier note;
  the frame-file check then cannot run. Real replays always have the tail.
- **A lane with no recorded reds is refused** (every task has a red commit, C4).
- **`review.md` format** (coordinator-written): a `Reviewer: <id>` line, the head SHA (7+ characters), last line
  `VERDICT: APPROVE`. `handoff.md` must carry `Implementer: <id>` (in the template).
- **Canonical test names (review finding 14):** `test_lane_gate_refuses_missing_verdict` and
  `test_lane_gate_refuses_wrong_reviewer_or_sha` from F Task 4 Step 1 are one parametrized test,
  `test_lane_gate_refuses_missing_verdict_or_wrong_reviewer_or_sha`, with the same cases. Not renamed: renaming a
  recorded red changes its id.
- **Not enforced by the gate, left to the reviewer** (review finding 15): the red commit subject starting `test:`, and
  "a review-finding red is replayed on the parent of its fix commit" (the gate replays the recorded SHA, whatever it
  is, so record the parent).
- **`.superpowers/sdd/0.4.0/lanes/README.md`** from the F plan's Task 4 file list was not written: the brief limited this
  piece to the gate, its tests, the handoff template and this file. The evidence layout is in this file and the template.
- `uv` hardlinks fail on this machine with os error 1142 (too many links on a cached file). The gate sets
  `UV_LINK_MODE=copy` for its subprocesses unless already set; `uv sync` in a fresh worktree needs the same.

## Review round 1 (`review-gate.md`, verdict CHANGES at `6ae8e23`)

| Finding | Test | Red SHA | Fix |
|---|---|---|---|
| 1 major: a red built on a test already on the integration branch passed | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_red_test_already_on_integration_branch` | `e2e3dc064a94c6536b3d534a15df5c6eabf8d36b` | `6d02a5d` |
| 2 major: an `AssertionError` raised in `src/` counted as a red | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_assertion_raised_outside_the_test` | `0a3a7eb1c2b5bbd2f12f2bcb6248dc95b48c0340` | `bc166f8` |
| 3 major: a blank Red SHA cell skipped replay | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_fixed_finding_without_red_sha` | `2e4a2a0f492433a74ac71c519c307190ae66164c` | `8d33cef` |
| 3 major: a findings table without a `Red SHA` column was ignored | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_findings_table_without_red_sha_column` | `2e4a2a0f492433a74ac71c519c307190ae66164c` | `8d33cef` |
| 5 major: a module constant edited after the red commit | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_red_module_constant_changed_after_red_commit` | `6bd513dca27cb1e2e1edcdf71debc6f08d207918` | `578be8d` |
| 5 major: a conftest edited after the red commit | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_conftest_changed_after_red_commit` | `6bd513dca27cb1e2e1edcdf71debc6f08d207918` | `578be8d` |
| 4 major: the gates ran in the implementer's tree and venv | `tests/scripts/test_lane_gate.py::test_lane_gate_runs_gates_in_a_fresh_tree_at_head` | `008744a66bc01b375a373603c4148b00c9837879` | `d9126ef`, `33ef522`, `4fb06fb` |
| 4 major: a failed env sync must refuse | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_when_the_fresh_environment_fails_to_sync` | `008744a66bc01b375a373603c4148b00c9837879` | `d9126ef` |
| 8 minor: a short head SHA in `review.md` was refused | `tests/scripts/test_lane_gate.py::test_lane_gate_accepts_review_with_short_head_sha` | `1f1f94362e1eba9694a080e543efe249fbabcf72` | `ff187f2` |
| 7 minor: a failed lowest-direct/no-sqlalchemy log was accepted | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_failed_sha_log` | `1f1f94362e1eba9694a080e543efe249fbabcf72` | `ff187f2` |
| 10 minor: a bare `N/A` checklist item was accepted | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_bare_na_checklist_item` | `1f1f94362e1eba9694a080e543efe249fbabcf72` | `ff187f2` |
| 12 minor: the leased-pg log matched by substring | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_leased_log_with_prefix_match_only` | `1f1f94362e1eba9694a080e543efe249fbabcf72` | `ff187f2` |
| 9 minor: a missing `Implementer:` line switched off the reviewer check | `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_handoff_without_implementer` | `1f1f94362e1eba9694a080e543efe249fbabcf72` | `ff187f2` |

All 13 rows were replayed with the gate's own real runner (`...\logs\F-gate-replay-self-r1.log`): each fails with an
`AssertionError` from `tests/scripts/test_lane_gate.py` at its red SHA and passes at head (0 replay refusals).
The red commits were checked first with the `-k` subset, which showed only `AssertionError` failures.

Finding 6 (untested checks): coverage tests that pass at commit `1f1f943` (the checks already existed):
`test_lane_gate_refuses_red_sha_that_is_not_an_ancestor_of_head`, `test_lane_gate_refuses_red_test_missing_at_head`,
`test_lane_gate_refuses_dirty_worktree`, `test_lane_gate_refuses_handoff_not_updated_by_the_lane`,
`test_lane_gate_refuses_lane_f_rekey_that_raises_the_total`,
`test_lane_gate_refuses_bare_id_when_one_parametrisation_passes_at_red`,
`test_lane_gate_removes_the_replay_tree_when_pytest_raises`, plus the control
`test_lane_gate_refuses_review_with_too_short_or_wrong_prefix`. Finding 13 is fixed in `d9126ef`: one
`_temp_tree` context manager, `mkdtemp` inside the `try`, and `git worktree prune` in `finally`. Finding 14 and
finding 15 are logged under Decisions. Finding 11 (wider protected set: `tests/test_code_shape.py`,
`scripts/ci/sonar_ratchet.py`, `[tool.ruff]`/`[tool.pyright]`, `.github/workflows/ci.yml`, budget comparison lines) is
left as the owner's call; the reviewer checklist still covers it.

**Two consequences the coordinator must decide on:**

- **Rule 5 (whole red file) refuses most of lane F's own reds.** F kept adding imports and helpers to its red test
  files after each red commit, which the rule counts as a change. At `d37c6f2`, 24 F rows are refused for this. The
  same applies to this half's 13 round-1 reds: the shared `Fixture` in `test_lane_gate.py` was extended after them
  (they are recorded only in this file, not in F's `handoff.md`/`findings.md`, so the gate does not read them). The
  options are: keep the rule and have F record new reds, or loosen it to "existing non-test lines unchanged, lines may
  be added". The loose version still lets a later-added fixture or `pytestmark` shadow earlier content.
- **Rule 1 (lane must add or change the red test) refuses review-finding reds on pre-existing tests.** F's two
  `test_plugin_gates.py::test_plugin_hook_raises_session_continues[...]` rows (review finding, replayed on the parent
  of fix `65c5026`) use tests that already exist on `release/0.4.0`. They replay correctly (fail at `ba095ef`, pass at
  head), but the rule refuses them. If review-finding regressions caught by an existing test should pass, the rule
  needs an exception, for example for rows marked as review findings.

## What the gate says about lane F (round-1 rules, replayed at `d37c6f2` with the real runner)

Log: `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\F-gate-replay-F-d37c6f2-r1.log`
(red integrity and replay only). 55 red rows. Refusals:

1. 24 rows: test file changed outside added test functions after the red commit (rule 5, above).
2. 2 rows (`test_plugin_gates.py`): test unchanged from the integration branch (rule 1, above).
3. `test_unimplemented_panel_surface.py` rows: recorded SHA `c11ed916979054a6b994c9733964021e4ac5354f` does not exist;
   the real commit is `c11ed911b56c9460d64ad3253809cf729f6622b7`.
4. 2 `test_capture_hooks.py` rows: function body changed after red commit `acbccbb`.
5. `test_safety_matrix.py::test_disabled_panel_denies_its_endpoints`: Red SHA `n/a` (move it out of the red table).
6. `test_tools.py::test_call_tool_uses_facade_catalogue`: fails with `RpcError` at `45797333`, a fake red.
7. 4 Vitest rows `unverified` (replay by hand, then `--accept-unverified`).

## Verification

- `uv run pytest -q -n 4 tests/scripts/test_lane_gate.py tests/test_code_shape.py`: 84 passed at `4fb06fb` (about
  2 min under load; real git on Windows plus a temp worktree per gate run).
- **Real end-to-end four-gate step** (round 1), using the gate's own `gate_refusals` with the real runners at `ff187f2`
  (log `...\logs\F-gate-selfcheck.log`, gate logs under `...\logs\F-gate-selfcheck\`): the fresh detached tree was
  created, `uv sync --frozen --extra test` built its `.venv` (exit 0), ruff check, ruff format and pyright passed
  (exit 0), the tree was removed (0 `lane-gate-` worktrees left). Its pytest run caught a real regression from
  round 1: `test_complexity_only_goes_down` (`red_integrity` reached C901 12), fixed by the split in `4fb06fb`.
  The other failures in that run were F's 14 known ones plus two overhead budgets
  (`test_request_overhead_budget`, `test_statement_overhead_budget`) under heavy machine load (the suite took 7m40s
  against 2m20s earlier; both passed in the earlier full run, and this work touches no runtime code).
- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`: clean (406 files formatted, 0 pyright errors).
- Full suite at `f58a5be`: 14 failed, 3581 passed, 5 skipped. All 14 failures (12 x
  `test_safety_matrix.py::test_disabled_panel_denies_its_endpoints[<0.4 panel>]`, 2 x
  `test_plugin_gates.py::test_plugin_hook_raises_session_continues`) fail the same way at lane F's `0cc440a` without
  this work (replayed in a detached worktree: 15 failed there). They are F's own, and the other half's `d37c6f2`
  probably addresses them. Log: `...\logs\F-gate-pytest.log`.
- Real replay of F's reds (above) exercised the default runner end to end: temp worktrees were created and removed
  (`git worktree list` shows none left).
