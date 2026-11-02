# D3 Findings

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Pool DTO must report nullable read-only and honest auto-commit values | `tests/engine/test_pools.py::test_pool_dto_emits_null_read_only_and_honest_auto_commit` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert False is None` at `tests/engine/test_pools.py:142` | Fixed in `e11e98071b5c1802e00813d24d27f24da0298b13` |
| Pools report and DTO must use the 2.2.0 library and implementation fields | `tests/engine/test_pools.py::test_pools_report_emits_pool_library_present_and_implementation` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in {'hikariPresent': True, ...}` at `tests/engine/test_pools.py:150` | Fixed in `e11e98071b5c1802e00813d24d27f24da0298b13` |
| Pool DTO shape must match the 2.2.0 keys | `tests/engine/test_pools.py::test_shape_keys_match_bootui` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert ('hikariPresent', 'total', 'pools') == ('poolLibraryPresent', 'total', 'pools')` | Fixed in `e11e98071b5c1802e00813d24d27f24da0298b13` |
| Non-AUTOCOMMIT engines must not fabricate `autoCommit: false` | `tests/engine/test_pools.py::test_autocommit_from_isolation_level` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert [False, True] == [None, True]` at `tests/engine/test_pools.py:135` | Fixed in `e11e98071b5c1802e00813d24d27f24da0298b13` |
| MCP pool report must expose the renamed report field | `tests/fastapi/test_pools_api.py::test_get_database_connection_pools_mcp` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in content` at `tests/fastapi/test_pools_api.py:49` | Fixed in `e11e98071b5c1802e00813d24d27f24da0298b13` |
| Pool report must expose the renamed presence field when SQLAlchemy is unavailable | `tests/fastapi/test_sqla_absent.py::test_pools_report_without_sqlalchemy_emits_pool_library_present_false` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in {'hikariPresent': False, ...}` at `tests/fastapi/test_sqla_absent.py:35` | Fixed in `e11e98071b5c1802e00813d24d27f24da0298b13` |
| Legacy D3 panel routes must not be registered as a `panels04` safety lane | `tests/safety/test_d3_safety.py::test_d3_legacy_panel_is_not_added_as_a_panels04_lane` | `7e298febc2fc6acb7053617696bce33d66fb669c` | `assert load().invalid == ()`; the matrix reported that `database-connection-pools` is not in `panels04.MODULE_PANEL_IDS` at `tests/safety/test_d3_safety.py:24` | Fixed in `06a8bcdb4eb916f25f960756d8064f2235c576ad` |

## Boundary finding

`get_threads` applies the default in `sharpit.engine.tool_dispatch.call_tool`, because that function normalizes an omitted
limit to `gate.max_results` before the handler in `src/sharpit/engine/tools.py` runs. The D3 May-touch list allows
`src/sharpit/engine/tools.py` but excludes `src/sharpit/engine/tool_dispatch.py`. No out-of-bound edit or red test was
made. The MCP default-limit task is parked pending a plan amendment that permits the dispatcher file.

The pools panel is a legacy panel, not a `panels04` lane panel. The safety loader rejects it if exported as `PANEL` in
the D3 safety file; its routes are already in `tests/test_safety_matrix.py::ROWS`. The D3 safety file therefore keeps
its direct no-side-effects check and omits the row exports per `tests/safety/README.md`.

## Golden limitation

The permitted D3 fixture for Alembic has no `captured.json` or `provisional.json`. Council O2/R9 reserves those for G0a,
so this lane did not invent a capture. Pool parity is checked against the existing `pools.captured.json` and the D3
`nullable.json`.
