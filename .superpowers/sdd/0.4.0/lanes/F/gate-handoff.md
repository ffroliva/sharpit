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

1. **Worktree:** `--sha` is the lane worktree's HEAD and it has no uncommitted tracked changes (the gates run there,
   using the lane worktree's `.venv`).
2. **Diff** `merge-base(integration HEAD, sha)..sha`: refuses `lanes/*/review.md`, `lanes/*/live-verify.md`,
   `lanes/*/gate/**`; `scripts/dev/lane_gate.py`, `sonar-baseline.txt`, `tests/engine/test_import_boundary.py`,
   `uv.lock`; a `pyproject.toml` change to `project.dependencies`, `optional-dependencies`, `dependency-groups` or
   `build-system.requires` (other pyproject edits pass); any changed `BUDGET*` top-level assignment in a `.py` file;
   `tests/complexity_baseline.json` with an added key or a raised value (F1c). Lane id `F` may change the gate,
   import-boundary, `uv.lock` and `pyproject.toml`, and may re-key the baseline when the total does not rise.
3. **Evidence (C2)** read from the lane head with `git show`: `handoff.md` (and the lane diff touched it),
   `findings.md`, `field-map.md`, `checklist.md`. Checklist: rows for items 1–10, each with `N/A` or a backticked path
   that exists in the lane head or the integration worktree (`::test` and `:line` suffixes are stripped). Findings:
   every row with a `Disposition` column starts `Fixed` (and names a test) or `Parked` plus a reason.
4. **Review** in the integration worktree `lanes/<lane>/review.md`: last non-blank line `VERDICT: APPROVE`, the full
   head SHA somewhere in it, a `Reviewer: <id>` line, and that id differs from the handoff's `Implementer: <id>` line
   when present. `gate/lowest-direct.log` and `gate/no-sqlalchemy.log` must name the head SHA on line 1.
5. **Red integrity:** every `(test, red SHA)` from any table with a `Test id`/`Test` column and a `Red SHA` column in
   `findings.md` and `handoff.md` (short SHAs are fine). Refuses: no reds at all; unknown SHA; SHA not an ancestor of
   head; SHA already in the integration branch (not a lane commit); test function missing at the red SHA or head; the
   function's source (decorators included, via `ast`) differing between red SHA and head. Non-pytest ids (Vitest)
   are `unverified`.
6. **Red replay (R2):** per red SHA a `git worktree add --detach` in a temp folder (removed afterwards), then
   `uv run --project <integration> --frozen python -m pytest -q -p no:cacheprovider -p no:randomly --tb=long
   --junitxml=... <ids>` with `PYTHONPATH=<tree>/src;<tree>` so the replayed tree's code shadows the editable
   install. Accepts only a `<failure>` whose exception class is `AssertionError`; refuses pass, `<error>`, skip, not
   collected, or another exception. Then the same ids must pass at head (same method).
7. **R7:** lane `A-postgresql` needs `gate/leased-pg.log` with the head SHA on line 1 and both
   `test_read_only_wrapper_rejects_write` and `test_autocommit_engine_is_unavailable` on lines containing `PASSED`.
8. **Four gates** in the lane worktree: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`,
   `uv run pytest -q -n 4` (timeouts 300/300/900/1800 s). Each writes `<integration>/.superpowers/sdd/0.4.0/lanes/<lane>/gate/<name>.log`
   (`ruff-check`, `ruff-format`, `pyright`, `pytest`), head SHA on line 1, then the command, exit code and output.

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
- **The gates run in the lane worktree**, so the gate requires `--sha` to be its HEAD and the tree clean. Replays use
  temporary detached worktrees and the integration environment, as R2 says.
- **A lane with no recorded reds is refused** (every task has a red commit, C4).
- **`review.md` format** (coordinator-written): a `Reviewer: <id>` line, the full head SHA, last line
  `VERDICT: APPROVE`. Implementers add `Implementer: <id>` to `handoff.md` (in the template) for the different-reviewer
  check; without it that check is skipped.
- **`.superpowers/sdd/0.4.0/lanes/README.md`** from the F plan's Task 4 file list was not written: the brief limited this
  piece to the gate, its tests, the handoff template and this file. The evidence layout is in this file and the template.
- `uv` hardlinks fail on this machine with os error 1142 (too many links on a cached file). The gate sets
  `UV_LINK_MODE=copy` for its subprocesses unless already set; `uv sync` in a fresh worktree needs the same.

## What the gate says about lane F (replayed at `d37c6f2` with the real runner)

Log: `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\F-gate-replay-F-d37c6f2.log`
(red integrity and replay only; F's `review.md` and gate logs do not exist yet). 55 red rows; 46 replayable; 45 of
those failed with an `AssertionError` at their red SHA and passed at `d37c6f2`. The gate refuses F today for:

1. `tests/fastapi/test_unimplemented_panel_surface.py::test_panel_implemented_defaults_true` and
   `::test_unimplemented_panel_has_no_surface`: recorded SHA `c11ed916979054a6b994c9733964021e4ac5354f` does not exist;
   the real commit is `c11ed911b56c9460d64ad3253809cf729f6622b7` (`c11ed91`). The Vitest `nav.test.ts` row has the same typo.
2. `tests/fastapi/test_capture_hooks.py::test_unimplemented_security_logs_does_not_add_capture_middleware` and
   `::test_unimplemented_database_panels_do_not_enable_discovery`: body changed after red commit `acbccbb` (in
   `4e14bab`). Restore the bodies or record a new red.
3. `tests/engine/test_tools.py::test_call_tool_uses_facade_catalogue`: fails at `45797333` with `RpcError`, not an
   `AssertionError` (a fake red under C4).
4. `tests/test_safety_matrix.py::test_disabled_panel_denies_its_endpoints` has Red SHA `n/a (test scope, not a red)`:
   move that row out of the red tables.
5. Four Vitest rows are `unverified`: replay by hand, then `--accept-unverified`.
6. Not re-checked at `d37c6f2`: at `0cc440a`, three `findings.md` Dispositions read `Wrong-value-stub contract
   characterization; ...` (neither `Fixed` nor `Parked: <reason>`) and `handoff.md` had no `Implementer: <id>` line.

## Verification

- `uv run pytest -q -n 4 tests/scripts/test_lane_gate.py`: 57 passed (~40 s; the cost is real git on Windows).
- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`: clean (406 files formatted, 0 pyright errors).
- Full suite at `f58a5be`: 14 failed, 3581 passed, 5 skipped. All 14 failures (12 x
  `test_safety_matrix.py::test_disabled_panel_denies_its_endpoints[<0.4 panel>]`, 2 x
  `test_plugin_gates.py::test_plugin_hook_raises_session_continues`) fail the same way at lane F's `0cc440a` without
  this work (replayed in a detached worktree: 15 failed there). They are F's own, and the other half's `d37c6f2`
  probably addresses them. Log: `...\logs\F-gate-pytest.log`.
- Real replay of F's reds (above) exercised the default runner end to end: temp worktrees were created and removed
  (`git worktree list` shows none left).
