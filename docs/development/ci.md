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
| `test` (Python 3.12, 3.13, 3.14; Windows 3.14) | lint, format, pyright strict, the full suite; links point at github.com | `uv sync --locked --extra test && uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest -q -n auto` (add `--python 3.12` / `3.14` to change interpreter) |
| `coverage` | coverage for the code-scan; the two overhead budget tests are deselected (the tracer distorts timing) | `COVERAGE_FILE="$TEMP/.coverage" uv run pytest -q -n auto --cov=sharpit --cov-report=xml --deselect tests/fastapi/test_capture_overhead.py::test_request_overhead_budget --deselect tests/fastapi/test_sql_trace_overhead.py::test_statement_overhead_budget`. Subprocess runs (pytester) are measured through `[tool.coverage.run] patch = ["subprocess"]`. `COVERAGE_FILE` must stay outside the repo: `no_side_effects` treats files in the cwd as writes |
| `sonar` (needs `coverage`) | the code-scan quality gate (new-code coverage ≥ 85%, no new issues) and the ratchet: open issues on `main` equal `sonar-baseline.txt` | not reproducible offline; read the PR's quality gate and issues on the code-scan dashboard. When a merged PR fixed issues, `main` goes red until `sonar-baseline.txt` is lowered in a one-line PR (`scripts/ci/sonar_ratchet.py` prints the number) |
| `lowest` | the lowest direct dependency versions sharpit claims to support (Python 3.12) | `uv sync --extra test --no-dev --resolution lowest-direct --python 3.12 && uv run --no-sync pytest -q -n auto` (`--no-sync`: a plain `uv run` re-locks and undoes the resolution). Restore `uv.lock` afterwards if the sync rewrote it |
| `no-sqlalchemy` | sharpit installs, imports and serves every panel without SQLAlchemy | `uv sync --locked --extra test --no-install-package sqlalchemy --no-install-package aiosqlite --no-install-package alembic --no-install-package greenlet && uv run --no-sync pytest -q -n auto -m "not needs_sqlalchemy"`. A test that needs SQLAlchemy uses `pytest.importorskip` and the `needs_sqlalchemy` marker |
| `sharpit-gate` | dogfood: the example's fixed route passes `pytest --sharpit`, its planted N+1 fails it; reports uploaded as an artifact | `uv run --no-sync pytest examples/fastapi_sqla/tests_gate -k fixed --sharpit --sharpit-junit=sharpit-junit.xml` (must pass) and `-k n_plus_one --sharpit` (must fail) |
| `ui` | the committed build in `src/sharpit/ui/static` matches `ui/` | `cd ui && npm ci --ignore-scripts && npm run build && git diff --exit-code -- ../src/sharpit/ui/static`. Never build while the worktree's pytest runs: `no_side_effects` sees the new files |
| `vitest` | UI component and unit tests | `cd ui && npm ci --ignore-scripts && npm test` |
| `wheel` | the built wheel installs into a clean venv and imports | `uv build --out-dir "$TEMP/dist"`, then install `sharpit-*.whl fastapi pydantic-settings uvicorn httpx` into a fresh venv and run `scripts/ci/wheel_smoke.py` |

Not in `ci.yml`: the Playwright end-to-end suites (`ui/`, `npx playwright test` with `SHARPIT_E2E_PORT` set to an
`agentctl`-leased port; `-c playwright.sqla.config.ts` for the SQLAlchemy sample) and the release workflow
(`.github/workflows/release.yml`, run by a signed tag; see `skills/release/SKILL.md`).

## Reading a red job

- **Only on CI, never locally.** Reproduce that job's command in its own env first; the difference is the environment
  (an older dependency, a missing optional package, a different test order), not flakiness.
- **An overhead budget test.** Compare against the base with `scripts.dev.overhead_check`, alternating runs
  (`docs/development/overhead-budgets.md`); never raise a budget.
- **Order-dependent.** A test that passes alone and fails in the suite is a state leak; bisect the predecessor in one
  process (`-p no:xdist`). The `tests/conftest.py` logging guard makes a plugin test that changes logging fail itself.
