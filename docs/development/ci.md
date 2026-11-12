# CI: every job, what it guards, and how to run it locally

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`. A green local `/sharpit:check` runs one
environment; CI runs several. Before a PR that adds a dependency, a pytest plugin or test-time code, reproduce the jobs
below locally, each in its own environment so the worktree's `.venv` stays intact:

```bash
export UV_PROJECT_ENVIRONMENT="$TEMP/sharpit-ci-<job>"   # a throwaway env per job
```

sharpit 0.3.0 passed the full local gate and still failed three of these jobs on its first PR run (retrospective:
[`../reports/2026-11-01-0.3.0-retrospective.md`](../reports/2026-11-01-0.3.0-retrospective.md)).

| Job | Guards | Run it locally |
|---|---|---|
| `test` (Python 3.12, 3.13, 3.14; Windows 3.14) | the full suite on every leg; lint, format, pyright strict and the github.com link check on the Ubuntu 3.12 leg only (version-independent: pyright pins 3.12). uv's cache is on in every job. The suite runs in `test shard (os, python, i/n)` jobs; each required `test (os, python)` check only reports whether every shard passed (see *Shards* below) | `uv sync --locked --extra test && uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -q -n auto` (add `--python 3.12` / `3.14` to change interpreter; `SHARPIT_SHARD=2/4` runs one shard) |
| `coverage` | coverage for the code-scan, with the `sys.monitoring` tracer, in three `coverage shard (i/3)` jobs; `coverage` fails unless every shard passed, then `coverage combine`s their data into the `coverage.xml` sonar reads. Every overhead budget test skips itself while a tracer runs (`tests/overhead.py::paired`) and the plain `test` legs enforce it | `COVERAGE_CORE=sysmon COVERAGE_FILE="$TEMP/.coverage" uv run pytest -q -n auto --cov=sharpit --cov-report=xml`. Subprocess runs (pytester) are measured through `[tool.coverage.run] patch = ["subprocess"]`. `COVERAGE_FILE` must stay outside the repo: `no_side_effects` treats files in the cwd as writes |
| `sonar` (needs `coverage`) | the code-scan quality gate (new-code coverage ≥ 85%, no new issues) and the ratchet: open issues on `main` equal `sonar-baseline.txt` | not reproducible offline; read the PR's quality gate and issues on the code-scan dashboard. When a merged PR fixed issues, `main` goes red until `sonar-baseline.txt` is lowered in a one-line PR (`scripts/ci/sonar_ratchet.py` prints the number) |
| `lowest` | the lowest direct dependency versions sharpit claims to support (Python 3.12), in two `lowest shard (i/2)` jobs | `uv sync --extra test --no-dev --resolution lowest-direct --python 3.12 && uv run --no-sync pytest -q -n auto` (`--no-sync`: a plain `uv run` re-locks and undoes the resolution). Restore `uv.lock` afterwards if the sync rewrote it |
| `no-sqlalchemy` | sharpit installs, imports and serves every panel without SQLAlchemy | `uv sync --locked --extra test --no-install-package sqlalchemy --no-install-package aiosqlite --no-install-package alembic --no-install-package greenlet && uv run --no-sync pytest -q -n auto -m "not needs_sqlalchemy"`. A test that needs SQLAlchemy uses `pytest.importorskip` and the `needs_sqlalchemy` marker |
| `sharpit-gate` | dogfood: the example's fixed route passes `pytest --sharpit`, its planted N+1 fails it; reports uploaded as an artifact | `uv run --no-sync pytest examples/fastapi_sqla/tests_gate -k fixed --sharpit --sharpit-junit=sharpit-junit.xml` (must pass) and `-k n_plus_one --sharpit` (must fail) |
| `ui` | the committed build in `src/sharpit/ui/static` matches `ui/` | `cd ui && npm ci --ignore-scripts && npm run build && git diff --exit-code -- ../src/sharpit/ui/static`. Never build while the worktree's pytest runs: `no_side_effects` sees the new files |
| `vitest` | UI component and unit tests | `cd ui && npm ci --ignore-scripts && npm test` |
| `wheel` | the built wheel installs into a clean venv and imports | `uv build --out-dir "$TEMP/dist"`, then install `sharpit-*.whl fastapi pydantic-settings uvicorn httpx` into a fresh venv and run `scripts/ci/wheel_smoke.py` |

Not in `ci.yml`: the Playwright end-to-end suites (`ui/`, `npx playwright test` with `SHARPIT_E2E_PORT` set to an
`agentctl`-leased port; `-c playwright.sqla.config.ts` for the SQLAlchemy sample) and the release workflow
(`.github/workflows/release.yml`, run by a signed tag; see `skills/release/SKILL.md`).

## Shards

Where one runner would take well over two minutes, the suite is split by test file: `SHARPIT_SHARD=i/n` makes
`tests/_shard.py` (a plugin loaded by `tests/conftest.py`) skip collecting every test file outside shard `i`. A file
with a measured weight for the runner's platform in `tests/shard_weights.json` goes longest first onto the lightest
shard; any other file goes by a hash of its path, so adding a file never moves the others. `tests/test_shard.py` proves
the shards are disjoint, their union is the unsharded collection, no shard of the real suite is empty, and the weighted
split stays within the longest-first bound. The weights come from the shards' JUnit artifacts (`junit-*`, kept 7 days):
refresh them with `gh run download <run id> -p 'junit-*' -D <dir> && python scripts/ci/shard_weights.py <dir>` when a
shard runs well past the others. They are not the pytest-speed baseline (`tests/test_durations.json`), which is never
refreshed to balance shards.

The four files heavier than any shard alone (`tests/_shard.py` `OWN_JOB`: the masking gates and
`tests/scripts/test_lane_gate.py`) run whole in the `masking gates (os, part)` jobs, never in a shard.
`tests/test_shard.py` fails when more than 10% of the sharded test files have no weight: refresh the weights then.

| Leg | Shards |
|---|---|
| Windows 3.14 (listed first: the long pole) | 6 |
| Ubuntu 3.12, 3.14 | 4 each |
| `coverage` (the 3.13 leg) | 5 |
| `lowest` | 4 |
| `no-sqlalchemy` | 3 |

Branch protection requires the job names in the first table, so each keeps a job that `needs:` its shards and runs
`if: always()` (a skipped required check counts as green): it fails unless the whole shard matrix succeeded. `sonar` does the same with `coverage` (it
fails, never skips, when coverage did not succeed; forks and Dependabot still skip it for want of a token). One red
shard therefore turns all four `test` checks red; the shard job's own name says which leg failed. To add a shard,
change the matrix only; never shard to hide a slow test (`skills/optimize/SKILL.md`).

## Wall clock

Target (owner, top priority): a PR's run, first job queued to last check green, averages 3-5 minutes, and so does an
sbx full-suite run. Measure a run with the jobs API (`gh api repos/ffroliva/sharpit/actions/runs/<id>/jobs`): wall is
the last `completed_at` minus the first `created_at`, runner-minutes the sum of job durations.

| Run | Layout | Wall | Runner-min | Long pole |
|---|---|---|---|---|
| 43178363371 (PR #153) | stale weights; Windows 4 shards, Ubuntu 5 | 10.8 | 89.9 | `test shard (windows, 1/4)` 5.1 min (841 test-s; 2/4 had 397) |
| 43183266267 (PR #156) | fresh weights; Windows 6, Ubuntu 4 | 14.6 | 102.0 | `test shard (windows, 5/6)` 8.0 min (962 test-s; 4/6 had 211) |
| 43186443513 (PR #156) | same, plus `--dist worksteal` (reverted, see below) | 6.4 | 80.0 | `test shard (windows, 6/6)` 3.9 min (its shards 1.6-2.7 min) |
| 43187639646 (PR #156) | worksteal reverted | 8.1 | 96.5 | `test shard (ubuntu, 3.14, 1/4)` 4.5 min |
| 43199441634 (PR #156) | sqlite heap-walk fix | 6.7 | 77.5 | `test shard (windows, 6/6)` 3.3 min; jobs queued up to 2.9 min, 20 at once |
| 43201435266 (PR #156) | weights refreshed after the fix | 6.7 | 77.7 | `test shard (ubuntu, 3.14, 4/4)` 4.3 min; queued up to 3.0 min |

After the heap-walk fix the shards are balanced and no test file drifts by worker; the wall is the account's 20-runner
pool (77 runner-min, so ~3.9 min even perfectly packed) plus `sonar` (~2 min) after the coverage shards. Its Python
sensor re-parses every file each run because the base branch's analysis cache is stale. The remaining levers are the
layout and runner options (O1-O3 in the 0.6.0 plan's `W0b-ci-method.md`), queued for the owner.

What the numbers say:

- **Setup is not the cost.** With uv's cache hot, checkout, setup-uv and `uv sync` take 10-25 s a job.
- **The pool is.** ~52 jobs share an account-wide pool of ~20 runners with every other lane's runs; in 43183266267
  only 10-14 of ours ran at once and Windows shards started 4-8 minutes in. Job order in the file does not change
  which job gets a runner first.
- **Shard times swing with what shares a worker, not with the weights.** The same `tests/test_safety_matrix.py`
  slice cost 33-69 s on five Windows shards and 464 s on the sixth: its tests ran at ~0.8 s each, then ~11 s each
  after some earlier test on that worker. Same file, 92 s on `lowest` and 382 s on Ubuntu 3.12 in one run. Candidate
  cause (its effect on CI not yet measured): `engine/sources/sqlite.py` `_count_preexisting` called
  `gc.get_referrers`, a whole-heap walk, once per live sqlite3 connection on every attach, so a worker that piles up
  connections paid heap x connections on every `install()` (scratch: 300k objects, 200 connections, 755 ms). It now
  makes two walks for any count (75 ms there); `test_preexisting_count_walks_the_heap_a_fixed_number_of_times` pins it.
- **Tail stragglers.** `--dist load` left one worker with a 3-minute queue after the other three were idle
  (ubuntu 3.14 3/4: 98% -> 100% took 3 min). `--dist worksteal` evened the Windows shards (1.6-2.7 min) but reorders
  tests across workers, and that exposed a logging-state leak older than this change: seven `caplog` tests in
  `tests/fastapi/test_install.py` saw no records on coverage shard 4/5. The logging guard (`_logging_unchanged` in
  `tests/conftest.py`) covers only `pytest_plugin/` and `testsession/`, so the leaking test is not named. worksteal
  comes back once the guard covers the whole suite and the leak is fixed.

## Reading a red job

- **Only on CI, never locally.** Reproduce that job's command in its own env first; the difference is the environment
  (an older dependency, a missing optional package, a different test order), not flakiness.
- **An overhead budget test.** Compare against the base with `scripts.dev.overhead_check`, alternating runs
  (`docs/development/overhead-budgets.md`); never raise a budget.
- **Order-dependent.** A test that passes alone and fails in the suite is a state leak; bisect the predecessor in one
  process (`-p no:xdist`). The `tests/conftest.py` logging guard makes a plugin test that changes logging fail itself.
