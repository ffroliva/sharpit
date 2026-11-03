# Findings: lane F5a-harness

Red commit `eb5aff6f0031281187328ae04c0a867fdd05dd15` (27 parametrised cases, all `RED (assertion under tests/)` from `scripts/dev/red_check.py`);
fix commit `ff610d5`. Mutations ran in a scratch copy of `ff610d5` (outside the worktree), each reverted after.

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| guard blind to interpreter state and app-source reads (spec §4.4, council H4) | `tests/test_side_effect_guard.py::test_side_effect_guard_catches_interpreter_state` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `verify() did not report <change>` (all 10 cases) | Fixed in ff610d5 |
| no call-site rule for interpreter state (spec §4.4, §9, council M8) | `tests/engine/test_import_boundary.py::test_interpreter_state_call_sites_only_in_session_modules` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert [] == ['sharpit/engine/collectors/probe.py:5 calls tracemalloc.start', ...]` | Fixed in ff610d5 |
| CLI actions a fixed list; `postgresql_read` missing (council H15) | `tests/test_safety_matrix.py::test_cli_actions_declared_per_lane` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert None == 'postgresql'` (`probe_action` not picked up) | Fixed in ff610d5 |
| mapper walk inside a collector (council H6) | `tests/engine/test_models.py::test_mapper_walk_in_engine_never_configures` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert [] == [<registry>]` (skeleton walk) | Fixed in ff610d5 |
| 0.5.0 settings missing (spec §4.5) | `tests/test_settings_05.py::test_05_settings_defaults_and_env` | `eb5aff6f0031281187328ae04c0a867fdd05dd15` | `assert '<name>' in {...fields}` (all 14 cases) | Fixed in ff610d5 |
| unimplemented 0.5.0 panel surface (council M12) | `tests/test_surface_05.py::test_unimplemented_panel_has_no_surface_05` | | passes at the red SHA (all eight flags are off on the base) | pin: `if not p.implemented:` → `if False:` in `engine/panels.py:94` → 8 failed on `assert panel not in panel_ids` |
| config getenv exemption (spec §14) | `tests/test_side_effect_guard.py::test_side_effect_guard_allows_config_getenv_scan` | | passes at the red SHA (skeleton spy) | pin: `SOURCE_READ_EXEMPT = ()` → 1 failed, `assert error is None` |
| reads outside the watched root ignored | `tests/test_side_effect_guard.py::test_side_effect_guard_ignores_reads_outside_the_app` | | passes at the red SHA (skeleton spy) | pin: `_under(...)` check dropped from the spy → 1 failed, `assert error is None` |

## Mutation proofs of the new rules (scratch copy of ff610d5)

| Mutation | Result |
|---|---|
| M1 interpreter-state problems not reported in `SideEffectGuard.verify` | 7 failed: the seven interpreter cases of `test_side_effect_guard_catches_interpreter_state` |
| M2 `app source read` problems not reported | 3 failed: the three open/read_text/tokenize.open cases |
| M3 `SOURCE_READ_EXEMPT = ()` | 1 failed: `test_side_effect_guard_allows_config_getenv_scan` |
| M4 root containment dropped from the spy | 1 failed: `test_side_effect_guard_ignores_reads_outside_the_app` |
| M5 `tracemalloc.start` removed from `INTERPRETER_STATE_CALLS` | 1 failed: `test_interpreter_state_call_sites_only_in_session_modules` |
| M6 `SESSION_MODULES = {"sharpit"}` | 1 failed: same test |
| M7 `load()` ignores `CLI_ACTIONS` | 1 failed: `test_cli_actions_declared_per_lane` |
| M8 `data.py` defines its own `registries` | 1 failed: `test_mapper_walk_in_engine_never_configures` |
| M9 panel listing ignores the flag | 8 failed: every `test_unimplemented_panel_has_no_surface_05` case |
| M10 `tool_definitions` ignores the flag, tools planted in `tools04/mysql.py` | 1 failed: `[mysql]` (failure line not inspected; M9 is the recorded pin mutation) |
