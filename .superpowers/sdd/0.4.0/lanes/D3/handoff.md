# D3 Handoff

Implementer: codex gpt-6-luna

Status: DONE_WITH_CONCERNS. Round 1 findings 1–4 are fixed. The threads MCP default-limit task remains parked because
`call_tool` normalization is in `src/sharpit/engine/tool_dispatch.py`, outside D3's hard May-touch list. Alembic has no
captured/provisional 2.2.0 fixture; its field parity is unverified. The coordinator must record this in
`docs/reference/PARITY.md`, outside D3's May-touch list, so this lane did not edit it.

Base SHA: `3ddeaeae1ceeb5b406d2bb3abc919bb2690d30a5`
Code head SHA: `92027673ed5831631a2c02729d5313fec945258a`
Fix commit: `92027673ed5831631a2c02729d5313fec945258a`
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
| `tests/engine/test_pools.py::test_pools_report_parity_for_nullpool_and_unlimited_overflow` | `03d15905aa84e03d515647afb880e131fe4bdbc4` | `maximumPoolSize`, `connectionTimeoutMs`, and `snapshot` null values not listed in `nullable.json` |
| `tests/engine/test_threads.py::test_d3_panels_2_2_0_golden_conformance` | `60ddfccefcb925772235b822eddadcd849b93184` | `threads[].cpuTimeMillis` and `threads[].userTimeMillis` null in payload but non-null in golden |
| `tests/engine/test_threads.py::test_threads_report_emits_user_time_when_resource_supports_it` | `3f9edeaca18cc8adc0f72c08f18ba588e429883a` | `assert None == 1250` |

## Progress and resume

- Pool edge-case and D3 golden conformance regressions were red at the SHAs above and replayed in a detached worktree
  with its `src` first on `PYTHONPATH`.
- `docs/reference/PARITY.md` cannot be edited by D3 per the plan boundary; coordinator update is required for Alembic.
- Done: nullable pools, current-thread CPU and resource user time, golden conformance for all D3 panels with captured
  2.2.0 goldens, and a safety read using a real QueuePool.
- Targeted D3 files plus import boundary and code shape: 213 passed, 3 skipped.
- `tests/test_safety_matrix.py`: 1,025 passed. `tests/test_masking_corpus.py`: 54 passed.
- Static gates: ruff check passed; format check passed (490 files); pyright passed (0 errors).
- Full suite (single background run, `-n 4`): 4,382 passed, 9 skipped, 1 failed. The sole failure was
  `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget`: 62.983 µs
  overhead vs 35 µs budget, with 168.904 µs noise, so the overshoot was within machine noise. A standalone diagnostic
  run of that test passed; no budget was changed.
- Health golden conformance passes with an `UnverifiedParityWarning` because the golden's `setup` list has no item shape.
- Open: threads MCP default 25 remains parked; Alembic 2.2.0 DTO parity is unverified; coordinator PARITY update remains
  required.
- Reviewer finding 5 is declined because the duplicate assertion belongs to a committed immutable red test.
  The ponytail masking overlap is declined because the lane plan explicitly requires the D3 masking test.
