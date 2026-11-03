# T-unbounded-read handoff

Implementer: codex gpt-6-luna

## Status

DONE_WITH_CONCERNS. Plan implementation and tests are complete at code head `208229e2caf2aef50d1c903111fa239100760f78` (predecessor base `3ddeaea`). Coordinator-owned review, lowest-direct and no-SQLAlchemy evidence remains open in the integration worktree.

## Done / next

- Completed the remaining Task 2–4 matrix from `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/T-unbounded-read.md`.
- Added a no-install regression red at `c0a4c86a054f1ab0cc88f216eb628803a8c96af6`; `red_check.py` reported `RED (assertion under tests/)`, and detached replay at that SHA with `PYTHONPATH=<tree>/src` failed at the missing-limitations assertion. Fixed it in `c10fa047e8a0c7e5c5db30b76cda5a8b0ad19b98` by tracking test-phase ORM loads that have no `RequestInfo` and reporting the exact limitation in the pytest source row.
- Replayed the F2 reds at `2e373d7bcf262633b98a961e76d942d0b4796dd2` and superseded `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` in detached worktrees with `PYTHONPATH=<tree>/src`; both `red_check.py` runs reported RED.
- Added the full per-statement/request/entity count matrix, identity-map undercount, listener lifecycle/result preservation, limit/fetch, non-paged and unbound-page controls; paging validation/lazy match/reset/page_size cases; JSON round-trip, masking, threshold, lookup, marker, report-only, baseline and factor controls.
- Historical tests at `4541d8e463446148be920cecf831443e651a7e4e` were mutation-proven. `findings.md` records one row per test id, base ids for parametrized tests, the mutation and the assertion message.
- The unbounded-read limitation bookkeeping initially added one C901 finding to `pytest_runtest_makereport`. `test_code_shape.py::test_complexity_only_goes_down` failed at the assertion; `red_check.py` reported RED. The same test passed at untouched base `3ddeaea`. Moved the bookkeeping into `_record_unbounded_read_limitation` in `ccb4f4bbed3eabdae232373325bbb9761a25d32f`; the ratchet now passes without baseline changes.
- Targeted SQLAlchemy, gates, capture paging, pytester, import-boundary and code-shape tests: 106 passed, 1 third-party Starlette deprecation warning. Log: `C:\development\github\sharpit-wt\T-targeted-final.log`.
- Replayed the previous F2 replacement red and original red; no held-out benchmark data was accessed.

## Decisions / limits

- The no-install limitation is attached as an available source with a limitation, so it is visible without making a normal test session unknown solely because capture is absent.
- SQLite `StaticPool` and `check_same_thread=False` in the no-install pytester fixture share the test schema with TestClient's thread. Fixture initialization runs inside the test call so setup SQL does not swamp test attribution.
- Only May-touch files and the lane evidence folder changed. No other lane files, gate logs, or review files were touched.

## Commits

- `011bccd` was an invalid initial no-install red fixture (the nested pytest failed because of SQLite thread sharing); it was replaced before acceptance by `c0a4c86a054f1ab0cc88f216eb628803a8c96af6` with a passing nested pytest and the intended outer assertion red.
- `c10fa047e8a0c7e5c5db30b76cda5a8b0ad19b98` — no-install limitation fix.
- `4541d8e463446148be920cecf831443e651a7e4e` — completed edge-test matrix.
- `ccb4f4bbed3eabdae232373325bbb9761a25d32f` — keep the no-install report bookkeeping under the complexity ratchet.
- `208229e2caf2aef50d1c903111fa239100760f78` — sorted capture-paging test imports.

## Gates

- Targeted lane files: 96 passed (log above).
- `tests/engine/test_import_boundary.py` and `tests/test_code_shape.py`: passed as part of the targeted run.
- `uv run ruff check`: passed (`C:\development\github\sharpit-wt\T-ruff-check-final.log`).
- `uv run ruff format --check`: passed, 492 files (`C:\development\github\sharpit-wt\T-ruff-format-final.log`).
- `uv run pyright`: 0 errors, 0 warnings, 0 informations (`C:\development\github\sharpit-wt\T-pyright-final.log`).
- One final full suite: `uv run pytest -q -n 4`, 4,404 passed, 9 skipped, 45 warnings in 54m 07s. Log: `C:\development\github\sharpit-wt\T-full-pytest.log`.
- Lowest-direct/no-SQLAlchemy and review gate logs are coordinator-owned; this lane does not create those files.

## Session hardening

- **Outcome:** T-unbounded-read implementation and edge matrix are complete; lane is not merged or pushed.
- **Worked:** red commits were replayed detached with the worktree `src` first on `PYTHONPATH`; mutation tests prove existing guards; the full suite and static gates passed.
- **Did not work at first:** the first no-install fixture red failed inside nested pytest because an in-memory SQLite engine was not shared with TestClient, and ORM was imported after the pytest session tried to attach its listener. Fixed the fixture with `StaticPool`, `check_same_thread=False`, early fixture import and call-phase initialization; the valid no-install red then failed only at its assertion.
- **Did not work at first:** inline limitation-source bookkeeping pushed `pytest_runtest_makereport` above the C901 ratchet. `test_complexity_only_goes_down` caught it; moving bookkeeping to `_record_unbounded_read_limitation` fixed it without changing the ratchet.
- **Rulings:** stayed inside the May-touch list; no push, PR, or integration-owned gate files. External memory/vault files were not changed because the lane scope says out-of-list work belongs in this handoff.
- **Open:** integration reviewer, lowest-direct and no-SQLAlchemy checks remain with the coordinator. Repo OKF, auto-memory, MemPalace and Obsidian retrospective layers were not written because they are outside this lane's allowed touch list; this handoff carries the retrospective and resume point.

## Review round 1 continuation

- Red commits: `5d99628` (Core-only host, statement identity, row-path cost and loader accounting), `c8b26a6` (session capture limitation and finding location), and `59cf19c` (relationship-load findings). Each red was replayed detached with the red tree's `src` on `PYTHONPATH`; the final relationship replay used `uv run --extra test` and reported RED.
- Red audit follow-up: at detached SHA `59cf19c9927cfb9eb17917cfb004785ce8a1d115`, `test_multiple_entities_count_separately` failed on an unrelated key-set mismatch (`{'rows'}` vs `{'Team', 'Owner'}`), and `test_identity_map_hits_are_not_counted` crashed with `TypeError` because it treated a load list as a dict. Neither is a valid red claim; `findings.md` records both under `### Historical SHA`. At lane head `5c514bfd19cb1738ebdf8303e54b1c8256a4b5d0`, constant entity naming mutation made the first assert on `{'Entity'}` vs `{'Owner', 'Team'}`, and double-increment mutation made the second assert on `4 == 2`. `src/` was restored after each mutation.
- Fixes: ORM listener attachment now checks `sys.modules` without importing `sqlalchemy.orm`; pytest retries attachment in each phase. Relationship loaders and non-primary joined rows are excluded. Statement contexts stay alive as mapping keys, SQL shape is normalized/masked once at the configured count threshold, and the aggregate fact is updated in place. Capture limitations are decided at session end from whether any request was captured. Gate messages include the first application location. The missing-capture flag takes its lock once per test, not once per ORM row.
- Review disposition: findings 1–7 and 9–10 are fixed. Finding 8 is declined: the duplicate F2 test is retained as historical acceptance evidence, and the fixture-conftest cleanup is unrelated to the correctness fixes.
- Validation: targeted review set 118 passed, including the SQLAlchemy listener overhead budget; isolated overhead test 1 passed. Ruff check, Ruff format check (492 files), and Pyright (0 errors) passed. Final full suite `uv run --extra test pytest -q -n 4`: 4,414 passed, 9 skipped, 45 warnings in 5m 57s. Log: `C:\development\github\sharpit-wt\T-full-round2.log`.
- The first `-n auto` full run was discarded: temporary validation logs were removed while it ran, causing side-effect fixture errors, and the lazy-hook budget failed under noisy worker contention. The per-test missing-capture lock was removed from the per-row path; the isolated budget and clean four-worker suite then passed.

## Reactivation prompt

Resume sharpit 0.4.0 T-unbounded-read. Read `C:\development\github\sharpit-wt\0.4.0-T-unbounded-read\.superpowers\sdd\0.4.0\lanes\T-unbounded-read\handoff.md`, the lane plan and the spec. Review fixes and the final full suite are green at `a2c9cc346b258ba4a4577a6cbd4141f5626c8578`; the branch is not pushed. Next: coordinator review, lowest-direct and no-SQLAlchemy gates, then integrate only through `scripts/dev/lane_gate.py`. Do not re-ask decisions already in the lane brief; do not push.

## Red-integrity follow-up

- Superseded the three stale SQLAlchemy red rows in `findings.md` with new, independently named tests. The old test bodies/helpers remain unchanged; the fixed statement-count code now requires the hashable `_LoadContext` helper, so restoring the old `_load_context` would cause a `TypeError` instead of proving behavior. The relationship test was formatter-touched after its red commit, so its source was also left untouched and superseded.
- Mutation proofs at the lane head: use `id(context)` as the statement-count key → identity test assertion failed (`len(info.loads) == 2`, got 1); duplicate SQL normalization → once-only test assertion failed (`calls == 1`, got 2); make every mapper load primary → selectin relationship assertion failed because child `Member` findings appeared. Restored `src/sharpit/engine/sqla.py` after each mutation.
- All five new test cases passed before mutation and again at the final test source. The affected lane set passed 112 tests with one upstream Starlette deprecation warning. Repo-wide Ruff check, Ruff format check (496 files), and Pyright (0 errors/warnings/informations) passed.
- At committed head `ee3908c`, `lane_gate.py ... --no-rerun` reported no red-integrity refusals. The integration gate currently rejects `--no-rerun` for this non-fixture lane, and reports only stale coordinator-owned `review.md`, lowest-direct and no-SQLAlchemy stamps; those are coordinator-restamped. Re-run the command after the final local style commit; never push.
