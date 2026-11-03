# Handoff: lane F5a-harness (sharpit 0.5.0)

Implementer: claude-flavio / Claude Opus 5.5 (claude-opus-5-5)
Branch `lane/0.5.0-F5a-harness`, from `release/0.5.0` @ b2fc0ca. Plan: `docs/superpowers/plans/2026-11-03-sharpit-0.5.0/F5a-foundation.md` (F5a-harness Task 1). Spec §4.4, §4.5.

## Status

DONE: Task 1 (red `eb5aff6`, fix `ff610d5`, evidence commit after). Gates: see "Gates" below.

## Reds

| Test | Red SHA | Assertion message |
|---|---|---|
| `tests/test_side_effect_guard.py::test_side_effect_guard_catches_interpreter_state` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `verify() did not report <change>` |
| `tests/engine/test_import_boundary.py::test_interpreter_state_call_sites_only_in_session_modules` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert [] == [... probe.py:5 calls tracemalloc.start, ...]` |
| `tests/test_safety_matrix.py::test_cli_actions_declared_per_lane` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert None == 'postgresql'` |
| `tests/engine/test_models.py::test_mapper_walk_in_engine_never_configures` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert [] == [<registry>]` |
| `tests/test_settings_05.py::test_05_settings_defaults_and_env` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert '<name>' in {...fields}` |

Pins and mutation proofs: `findings.md`.

## Consumer interface (what later lanes use)

| Symbol | Where | Use |
|---|---|---|
| `SideEffectGuard.verify` | `tests/conftest.py` | now also fails on a change of `tracemalloc.is_tracing()`, `gc.callbacks`, `gc.isenabled()`, `gc.get_threshold()`, `sys.gettrace()`, `sys.getprofile()`, `sys.monitoring` tool ids 0-5 |
| `SideEffectGuard.watch_sources(root)` / `unwatch_sources()` | `tests/conftest.py` | **opt-in**: a GET test names its app root; every `open`/`io.open`/`tokenize.open` of a file under it is reported, except from a frame in `sharpit.engine.collectors.config*` (`SOURCE_READ_EXEMPT`, spec §14). The `no_side_effects` fixture unwatches in teardown |
| `CLI_ACTIONS = ["<tool>", ...]` | a lane's `tests/safety/test_<lane>_safety.py` | `test_cli_action_tools_gated` checks each (403 when gated, never on MCP) while the lane's flag is on |
| `INTERPRETER_STATE_CALLS`, `SESSION_MODULES` | `tests/engine/test_import_boundary.py` | rule 5: interpreter-state calls only in `sharpit/pytest_plugin/`, `sharpit/engine/testsession/` |
| `registries(models)`, `mappers_configured(registry, mappers)` | `src/sharpit/engine/models.py` | the mapper walk and configured-gate (A-dbadv-2, V-unverified); never configures, no SQLAlchemy import |
| settings | `src/sharpit/settings.py` | `mysql_max_{sessions,statements,indexes,tables,lock_waits,replication_channels,settings}` (1..2147483646), `database_advisor_max_{tables,columns,indexes_per_table,vendor_rows}`, `architecture_max_files` 2000, `architecture_max_file_bytes` 524288, `app_package` (dotted name or None) |
| `pymysql>=1.1` | `pyproject.toml` test extra, `uv.lock` | leased MySQL tests (F5b, A-mysql) |

## Decisions (nobody to ask; recorded here)

1. **Source-read spy is opt-in** (`watch_sources`). The guard cannot know an app root by itself, and a default root
   (`examples/`) would flag the existing MCP sweep, whose seed runs a REST API scan that reads handler source
   (`restapi/rules.py:783`) under the guard. Interpreter-state checks are always on.
2. **`tests/test_settings.py` edited** (not in May-touch): `test_env_name_table_covers_every_field` requires a
   PROPERTIES row per settings field, so the 14 new fields got rows (additive). Not a protected file.
3. **Mapper-walk tests not moved**: `tests/engine/test_data.py` is unchanged; its `data.registries` calls now reach
   `models.registries` (same function object, asserted by the must-cover test). Moving them was optional churn.
4. The configured-gate's private-flag reads switched from `getattr` to `inspect.getattr_static` (plan: "`getattr_static`
   only"); verified on SQLAlchemy 2's registry (`_new_mappers`, `_dependencies` are instance attributes).
5. `postgresql_read` added to the base CLI list in `tests/test_safety_matrix.py` (its lane file predates
   `CLI_ACTIONS` and is outside May-touch). `_postgresql_limit` renamed `_row_limit` (shared by MySQL).
6. Boundary rule set also covers `tracemalloc.stop/clear_traces`, `gc.set_threshold/disable/enable/freeze/unfreeze/
   set_debug`, `threading.settrace*/setprofile*`, and the `sys.monitoring` registration calls.

## Gates

At `ff610d5` (Windows, Python 3.13.7): `ruff check` clean; `ruff format --check` 532 files formatted; `pyright`
0 errors; full `pytest -q -n 4` **4595 passed, 9 skipped, 0 failed** in 12 min (log:
`0.5.0-integration/.superpowers/sdd/0.5.0/logs/F5a-harness-pytest.log`). `red_check.py` on the 27 red cases at
`eb5aff6`: all `RED (assertion under tests/)` (`logs/F5a-harness-redcheck.log`). Lowest-direct and no-SQLAlchemy:
coordinator (not run here). Budgets untouched.

## Must-cover

| Test | Exists | Passes at ff610d5 |
|---|---|---|
| `tests/test_side_effect_guard.py::test_side_effect_guard_catches_interpreter_state` | yes | yes (10 cases) |
| `tests/engine/test_import_boundary.py::test_interpreter_state_call_sites_only_in_session_modules` | yes | yes |
| `tests/test_safety_matrix.py::test_cli_actions_declared_per_lane` | yes | yes |
| `tests/engine/test_models.py::test_mapper_walk_in_engine_never_configures` | yes | yes |
| `tests/test_surface_05.py::test_unimplemented_panel_has_no_surface_05` | yes | yes (8 cases; pin) |
| `tests/test_settings_05.py::test_05_settings_defaults_and_env` | yes | yes (14 cases) |

## How to resume

Everything is committed. If a gate is red: read `C:\development\github\sharpit-wt\0.5.0-integration\.superpowers\sdd\0.5.0\logs\F5a-harness-pytest.log`.
