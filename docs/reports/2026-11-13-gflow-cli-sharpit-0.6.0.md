# gflow-cli under `pytest --sharpit` (0.6.0, 2026-11-13)

A re-run of the [0.3.0 proof](2026-11-01-gflow-cli-sharpit.md) with the released sharpit 0.6.0, by sharpit's author.

## Setup

- gflow-cli (a public FastAPI daemon using raw `sqlite3`), branch `develop` at `96339be1` ("back-merge main (v0.98.0)
  into develop"), in a detached worktree. No gflow-cli file was changed.
- The dev wrapper is gflow-cli's own `dev/sharpit_app.py` (outside the wheel, pinned by
  `tests/dev/test_sharpit_wrapper_outside_wheel.py`): `sharpit.attach_sql_sources()`, then the app, then
  `sharpit.install(app)`. Shipped gflow-cli code never imports sharpit.
- sharpit 0.6.0 from PyPI:
  `uv run --with "sharpit==0.6.0" pytest -q -n 4 --sharpit --sharpit-app dev.sharpit_app:app --sharpit-report=report.json --sharpit-junit=junit.xml`.

## Result

| | 0.6.0 (2026-11-13) | 0.3.0 (2026-11-01) |
|---|---|---|
| Tests | 6,804 (6,786 passed, 14 skipped, 4 failed by sharpit gates only) | 5,662 (5 failed by sharpit gates) |
| Wall time, `-n 4` | 3 min 21 s | 5 min 27 s |
| SQL statements | ~58k: 25,772 attributed, 32,583 filtered, **0 unattributed** | ~53k: 27,997 attributed, 25,092 filtered, 0 unattributed |
| N+1 findings | **0** | 6 (1 real defect, 2 noise, 3 expected polling) |
| Swallowed exceptions | 4 HIGH (gate), 114 INFO | - |
| Status | `fail`: 4 tests failed sharpit gates; the REST API advisor is `UNKNOWN` | `fail` |

The 4 failing tests pass without `--sharpit` (`4 passed`), so every failure is a sharpit gate.

## Findings

| Gate | Tests | Where | Reading |
|---|---|---|---|
| `sharpit.swallowed-exception` (HIGH) ×4 | `tests/test_telemetry.py::test_corrupt_db_is_silent`, `tests/test_telemetry_notice.py` (3 tests) | `DatabaseError` swallowed by a broad `except` at `src/gflow_cli/telemetry.py:339` and `:472`, and `src/gflow_cli/cli_telemetry.py:99`, neither re-raised nor logged | Deliberate in gflow-cli: a corrupt telemetry database must never break the CLI, and the tests are named for it. sharpit reports a real, unlogged swallow; a log line or a baseline entry would record the choice |

114 more swallowed exceptions are reported as INFO (below the `HIGH` fail threshold), mostly in the browser
transports. The REST API advisor reads `UNKNOWN` (`Mounted application at /mcp/messages has no inspectable routes`),
as in 0.3.0, with 7 INFO notes (`RAPI-DOC-002` ×3, `RAPI-DOC-001`, `RAPI-ERR-001`, `RAPI-MAP-005`, `RAPI-VER-001`).

## Not claimed

- Whether gflow-cli fixed the 0.3.0 N+1 defect or changed its tests: this run reports 0 N+1 findings, nothing more.
- No gflow-cli PR or issue was opened.
