# gflow-cli under `pytest --sharpit` (0.3.0 proof, 2026-11-01)

gflow-cli is a public FastAPI daemon that stores everything in raw `sqlite3` (no SQLAlchemy). It was run with the
0.3.0 integration branch to prove the out-of-code use (spec §12, plan Task 10).

## Setup

- gflow-cli worktree `.worktrees/sharpit-proof`, branch `chore/sharpit-dev-wrapper` from `origin/develop` @592f988d.
- `dev/sharpit_app.py` (outside the wheel; hatch packages only `src/gflow_cli`): `sharpit.attach_sql_sources()`, then
  `from gflow_cli.ui.app import app`, then `sharpit.install(app)`. Shipped code never imports sharpit.
- `tests/dev/test_sharpit_wrapper_outside_wheel.py` pins hardening row A1: wheel packages, wrapper location, no runtime
  dependency, no `import sharpit` under `src/`. Red first (wrapper moved away: `test_wrapper_lives_outside_the_package`
  failed on its assertion), then green (4 passed).
- Run: `uv run --with-editable <sharpit 0.3.0 integration> pytest -q -n 4 --sharpit --sharpit-app dev.sharpit_app:app`.

## Result

| | |
|---|---|
| Tests | 5,662 (5,646 passed, 11 skipped, 5 failed by sharpit gates only) |
| Wall time | 5 min 27 s with `-n 4` |
| SQL statements | 27,997 attributed, 25,092 filtered (PRAGMAs and schema reads), **0 unattributed** |
| Sources | `sqlite3` attached, exceptions attached, no SQLAlchemy |
| Status | `fail`: "5 tests failed sharpit gates" |
| Swallowed exceptions | 0 |

The 5 failing tests pass without `--sharpit` (22 passed in those two files), so every failure is a sharpit gate.

Heaviest tests by call-phase queries: `test_cli_run.py` resume tests (101, 90, 88, 81),
`test_reference_uploads.py::test_a_recorded_image_deleted_from_the_project_is_uploaded_again` (71), the
`TestGflowRunCommand` happy paths (65).

## Findings

| Rule | Test | Statement | Read |
|---|---|---|---|
| `sharpit.n-plus-one` ×2 | `tests/mcp/test_wait_false_runs.py::test_a_detached_job_and_a_waiting_call_share_the_profile` | `SELECT version FROM schema_migrations`, `SELECT version, checksum FROM schema_migrations` | noise: gflow's own migration table, opened per connection. The built-in filter knows only `alembic_version` |
| `sharpit.n-plus-one` ×3 | the three cancel/status tests in `test_wait_false_runs.py` | `SELECT task_id, ... FROM` the queue table | polling a job row until it changes state: expected in these tests (`allow_n_plus_one` on them), worth a look in the waiter |
| `sharpit.n-plus-one` | `tests/data/test_repository.py::test_get_asset_by_any_id_resolves_media_workflow_and_asset_ids` | `SELECT ... FROM assets` | a real repeated lookup in `get_asset_by_any_id` |
| REST API (INFO ×7) | app-wide | `RAPI-DOC-001/002`, `RAPI-ERR-001`, `RAPI-MAP-005`, `RAPI-VER-001` | below the HIGH gate; reported, not failing |

The `rest-api` advisor reported `UNKNOWN`: "Mounted application at /mcp/messages has no inspectable routes" (the MCP
SSE sub-app). With no gate failures that alone would make the run `unknown`; gflow would pass
`--sharpit-no-advisors` or accept unknown until mounted sub-apps are inspectable.

## What this changed in sharpit

- The `schema_migrations` noise led to widening the built-in filter to common migration tables (see the 0.3.0 review
  fixes).
- No gflow-cli PR is opened without the owner's yes; the proposed CI job is in this report's companion branch only.
