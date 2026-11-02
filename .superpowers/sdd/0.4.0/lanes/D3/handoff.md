# D3 Handoff

Implementer: codex gpt-6-luna

Status: DONE_WITH_CONCERNS. Pool DTO alignment is implemented and targeted tests pass. The threads MCP default-limit task
is parked because `call_tool` normalization is in `src/sharpit/engine/tool_dispatch.py`, which is outside D3's hard
May-touch list. No out-of-bound files were edited. Alembic has no captured/provisional 2.2.0 fixture; no fixture was
invented because O2/R9 assigns capture ownership to G0a.

Base SHA: `3ddeaeae1ceeb5b406d2bb3abc919bb2690d30a5`
Head SHA: `e11e98071b5c1802e00813d24d27f24da0298b13` (pool implementation; evidence commit pending)
Fix commit: `e11e98071b5c1802e00813d24d27f24da0298b13`

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/test_pools.py::test_pool_dto_emits_null_read_only_and_honest_auto_commit` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert False is None` (`tests/engine/test_pools.py:142`) |
| `tests/engine/test_pools.py::test_pools_report_emits_pool_library_present_and_implementation` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in {'hikariPresent': True, ...}` |
| `tests/engine/test_pools.py::test_shape_keys_match_bootui` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert ('hikariPresent', 'total', 'pools') == ('poolLibraryPresent', 'total', 'pools')` |
| `tests/engine/test_pools.py::test_autocommit_from_isolation_level` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert [False, True] == [None, True]` (`tests/engine/test_pools.py:135`) |
| `tests/fastapi/test_pools_api.py::test_get_database_connection_pools_mcp` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in content` (`tests/fastapi/test_pools_api.py:49`) |
| `tests/fastapi/test_sqla_absent.py::test_pools_report_without_sqlalchemy_emits_pool_library_present_false` | `b39e90fbf4cd1d759caa47ab65e03a3527357499` | `assert 'poolLibraryPresent' in {'hikariPresent': False, ...}` (`tests/fastapi/test_sqla_absent.py:35`) |

## Progress and resume

- Done: Task 1 pool fields, nullable reasons, API assertions, safety/masking coverage.
- Next: run the one required full suite in the background; run `ruff check`, `ruff format --check`, and `pyright`; update
  gate results and the final head SHA after the evidence commit.
- Last green command: `UV_LINK_MODE=copy uv run pytest -q tests/engine/test_alembic.py tests/engine/test_health.py tests/engine/test_threads.py tests/engine/test_tools.py tests/engine/test_pools.py tests/fastapi/test_pools_api.py tests/fastapi/test_sqla_absent.py tests/safety/test_d3_safety.py tests/masking/test_d3_masking.py tests/engine/test_import_boundary.py tests/test_code_shape.py` — 208 passed, 3 skipped.
- Open findings: threads default 25 parked at the May-touch boundary; no Alembic golden fixture; no D3 golden checks yet
  for health and threads.
- Red replay: all six Task 1 tests failed at `b39e90fbf4cd1d759caa47ab65e03a3527357499` with assertions in `tests/`
  using `PYTHONPATH=C:\development\github\sharpit-wt\D3-red-pools\src`.
