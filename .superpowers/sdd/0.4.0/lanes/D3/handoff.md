# D3 Handoff

Implementer: codex gpt-6-luna

Status: DONE_WITH_CONCERNS. Pool DTO alignment is implemented and targeted tests pass. The threads MCP default-limit task
is parked because `call_tool` normalization is in `src/sharpit/engine/tool_dispatch.py`, which is outside D3's hard
May-touch list. No out-of-bound files were edited. Alembic has no captured/provisional 2.2.0 fixture; no fixture was
invented because O2/R9 assigns capture ownership to G0a.

Base SHA: `3ddeaeae1ceeb5b406d2bb3abc919bb2690d30a5`
Code head SHA: `e11e98071b5c1802e00813d24d27f24da0298b13`
Fix commit: `e11e98071b5c1802e00813d24d27f24da0298b13`
Safety matrix fix: `06a8bcdb4eb916f25f960756d8064f2235c576ad`

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/test_pools.py::test_pool_dto_emits_null_read_only_and_honest_auto_commit` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert False is None` (`tests/engine/test_pools.py:142`) |
| `tests/engine/test_pools.py::test_pools_report_emits_pool_library_present_and_implementation` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in {'hikariPresent': True, ...}` |
| `tests/engine/test_pools.py::test_shape_keys_match_bootui` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert ('hikariPresent', 'total', 'pools') == ('poolLibraryPresent', 'total', 'pools')` |
| `tests/engine/test_pools.py::test_autocommit_from_isolation_level` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert [False, True] == [None, True]` (`tests/engine/test_pools.py:135`) |
| `tests/fastapi/test_pools_api.py::test_get_database_connection_pools_mcp` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in content` (`tests/fastapi/test_pools_api.py:49`) |
| `tests/fastapi/test_sqla_absent.py::test_pools_report_without_sqlalchemy_emits_pool_library_present_false` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in {'hikariPresent': False, ...}` (`tests/fastapi/test_sqla_absent.py:35`) |
| `tests/safety/test_d3_safety.py::test_d3_legacy_panel_is_not_added_as_a_panels04_lane` | `7e298febc2fc6acb7053617696bce33d66fb669c` | `assert load().invalid == ()`; expected empty invalid list |

## Progress and resume

- Done: Task 1 pool fields, nullable reasons, API assertions, safety/masking coverage.
- Next: coordinator review and merge gate; keep the threads MCP default-limit task parked until the May-touch list is amended.
- Last green command: `UV_LINK_MODE=copy uv run pytest -q tests/engine/test_pools.py tests/fastapi/test_pools_api.py tests/fastapi/test_sqla_absent.py tests/safety/test_d3_safety.py tests/masking/test_d3_masking.py tests/engine/test_alembic.py tests/engine/test_health.py tests/engine/test_threads.py tests/engine/test_tools.py tests/test_safety_matrix.py::test_write_route_table_is_complete tests/test_safety_matrix.py::test_get_route_table_is_complete tests/test_safety_lane_sweeps.py::test_matrix_feeds_lane_rows_into_its_sweeps tests/engine/test_import_boundary.py tests/test_code_shape.py` — 212 passed, 3 skipped.
- Static gates: `ruff check` passed; `ruff format --check` passed (490 files); `pyright` passed (0 errors).
- Full suite: `uv run pytest -q -n auto` — 4,375 passed, 9 skipped, 3 failed. The failures were safety-matrix checks caused
  by exporting the legacy pool panel as a `panels04` lane. They were reproduced red and fixed in
  `06a8bcdb4eb916f25f960756d8064f2235c576ad`; the full suite will not be rerun per the one-run instruction.
- Open findings: threads default 25 parked at the May-touch boundary; no Alembic golden fixture; no D3 golden checks yet
  for health and threads.
- Red replay: six pool tests failed at `b39e90fbf4cd1d759caa47ab65e03a3527357499`; the safety-matrix regression failed
  at `7e298febc2fc6acb7053617696bce33d66fb669c`. Both detached replays put their worktree `src` first on `PYTHONPATH`.
