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
| shared sweeps never watch app source (review #1, spec §4.4) | `tests/test_side_effect_guard.py::test_get_sweep_reports_an_app_source_read` | `c5618d946cafe39726b500be5d3f0d3378400e19` | `the GET sweep did not report an app source read` / `assert None is not None` | Fixed in fix round 1 (`watch_sources(EXAMPLES)` in both sweeps) |
| shared sweeps never watch app source (review #1, spec §4.4) | `tests/test_side_effect_guard.py::test_mcp_sweep_reports_an_app_source_read` | `c5618d946cafe39726b500be5d3f0d3378400e19` | `the MCP sweep did not report an app source read` / `assert None is not None` | Fixed in fix round 1 |
| a warm linecache hides a source read (fix round 1: FastAPI's first host request runs `inspect.getsourcelines` on the endpoint) | `tests/test_side_effect_guard.py::test_side_effect_guard_sees_a_read_through_a_warm_linecache` | `a40b319fe222c9da132e420b1f6754b7a4005636` | `a read served by a warm linecache was not reported` | Fixed in fix round 1 (`watch_sources` drops cached lines under the root) |
| CLI must-cover test checks the helper, not the wiring (review #2) | `tests/test_safety_matrix.py::test_cli_action_tools_gated_is_parametrised_from_the_lanes` | | passes at the fix-round head (the wiring was right; nothing proved it) | pin: `CLI_ACTIONS = cli_action_cases(LANES)` → `CLI_ACTIONS = BASE_CLI_ACTIONS` → 1 failed, `assert 'probe_action' in ['clear_exceptions', ..., 'postgresql_read']` |

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

## Mutation proofs, fix round 1 (worktree file mutated, run, restored from a scratch copy)

| Mutation | Result |
|---|---|
| M11 `CLI_ACTIONS = BASE_CLI_ACTIONS` (review mutation C) | 1 failed: `test_cli_action_tools_gated_is_parametrised_from_the_lanes` (`assert 'probe_action' in [...]`). The reviewer's suggested `assert CLI_ACTIONS == cli_action_cases(LANES)` would not bite: no lane declares `CLI_ACTIONS` yet, so both sides equal `BASE_CLI_ACTIONS`; the pin re-runs the module with a planted lane instead |
| M12 both `no_side_effects.watch_sources(EXAMPLES)` lines removed | 2 failed: `test_get_sweep_reports_an_app_source_read`, `test_mcp_sweep_reports_an_app_source_read` (`assert None is not None`) |
| M13 the `linecache` purge removed from `watch_sources` | expected: `test_side_effect_guard_sees_a_read_through_a_warm_linecache` red (it is red at `a40b319`, which has no purge) |

## OPEN: product finding the wired sweeps now report (needs a coordinator ruling)

`GET /sharpit/api/beans` and MCP `get_beans` (plain and sqla, 4 cases) read `examples/fastapi_sample/app.py`:
`fastapi/introspector.py:54` `_resource` calls `inspect.getsourcelines(target)` for each provider's `file:line`
(0.4.0 behaviour, BootUI `resource`). Before the purge it was hidden by FastAPI warming `linecache` for the same file
on the first host request, so the reviewer's "120 passed" was order-dependent. Spec §4.4/§14 exempt only config's
getenv scan. Options: (a) fix `_resource` to use `code.co_firstlineno` / `inspect.getsourcefile` without reading
(out of this lane's May-touch: `src/sharpit/fastapi/introspector.py`); (b) declare a second exemption in
`SOURCE_READ_EXEMPT` (a spec change). Neither taken here: the sweeps stay strict and these 4 cases fail at head.
