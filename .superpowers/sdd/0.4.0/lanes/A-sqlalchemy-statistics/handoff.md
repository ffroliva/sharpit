# Lane A-sqlalchemy-statistics handoff

Implementer: claude-sonnet-5-5 (lane A-sqlalchemy-statistics)
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/A-sqlalchemy-statistics.md`
Branch / worktree: `lane/0.4.0-A-sqlalchemy-statistics` in `C:\development\github\sharpit-wt\0.4.0-A-sqlalchemy-statistics`

## Status

- Done: Task 1 (`nullable.json`), Task 2 totals (fix `1b1e47dd`), Task 3 collector (fix `3316b806`), Task 4 routes/MCP/safety/masking (fix `5bb3ae9d`), Task 5 view (fix `21746fe1`), Task 6 live check and evidence.
- Status: DONE_WITH_CONCERNS (two shared tests need coordinator edits, below).
- Last green command: ruff check, ruff format --check and pyright clean. Full suite `-n 4`: 3791 passed, 5 skipped, 3 failed, 1 error (log `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\A-sqlalchemy-statistics-pytest.log`); vitest 15 files passed; `npm run check` clean.
- Open findings: see Needs from coordinator.

## Needs from coordinator (files outside my May-touch list)

1. `tests/test_safety_matrix.py::test_write_route_table_is_complete` fails: the new route `POST /sharpit/api/sqlalchemy-statistics/enable` needs a `WRITES` row (protected file, C5).
2. `tests/test_surface_follows_flags.py::test_every_shared_count_follows_a_flag_flip` errors in its fixture: `tools.TOOLS` is built at import with my flag already True, so the fixture's `merge_lane_tools(tools.TOOLS, ..., lane_tools)` sees `get_sqlalchemy_statistics` twice and raises `ValueError: lane tool name(s) collide`. Any lane that flips its flag will hit this; the fixture should merge only the planted tool.
3. `test_capture_overhead.py::test_request_overhead_budget` and `test_sql_trace_overhead.py::test_statement_overhead_budget` failed in the loaded full run. Not caused by this lane: base `a766132` source gives 0.276 ms against the 0.200 ms capture budget in the same environment (one rerun passed); the SQL Trace budget passed in isolation. Budgets not raised.
4. The UI test is `ui/tests/component/sqlalchemyStatistics.test.ts` (repo convention and vitest include pattern), not beside the view.
5. `src/sharpit/ui/static/` is not rebuilt (lanes never run `npm run build`).

## How to resume

All work is committed. Rerun `UV_LINK_MODE=copy uv run pytest -q -n 4` (log outside the worktree), and in `ui/`: `npm run check`, `npx vitest run`.

## Decisions

- Extra keys (`statementCount`, `nPlusOne`, `nPlusOneWindow`) live inside `statistics`.
- N+1 `route` is the exchange `endpoint` (module:qualname) when set, else its path; unknown exchange gives null `method`/`route` and a `routeReason`.
- `max_sql` is the normalised statement, truncated to `max_sql_length`, never raw text.
- The collector imports `sql_trace_unavailable_reason` lazily (engine.tools imports the lane tool modules at import).
- `enable` returns the same report and changes nothing; `enableAvailable` is false.
- No golden parity test: no golden fixture exists for this panel.
- `test_n_plus_one_route_from_a_real_request` had a wrong suffix assertion in its red commit; fixed, and kept out of the red table.
- Guards that already passed against the stubs (not reds): `test_totals_max_sql_never_holds_a_literal_with_parameter_capture`, `test_below_threshold_is_not_n_plus_one`, `test_only_selects_count_towards_n_plus_one`, `test_max_time_query_is_normalised`.

## Live check

In-process TestClient on `examples.fastapi_sqla` (tables pre-created, app seeded): `GET /owners/n-plus-one` 200; `GET /sharpit/api/sqlalchemy-statistics` 200: `queryExecutionCount` 9, `statementCount` 15, one `nPlusOne` entry (GET, `examples.fastapi_sqla.app:create_app.<locals>.owners_n_plus_one`, `SELECT id, owner_id, name, species FROM pets WHERE owner_id = ?`, 6 executions, 1 request, threshold 5).

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/capture/test_sqltrace_totals.py::test_totals_count_every_statement` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 3` |
| `tests/engine/capture/test_sqltrace_totals.py::test_totals_selects_only_select_category` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 2` |
| `tests/engine/capture/test_sqltrace_totals.py::test_totals_max_keeps_slowest` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 40` |
| `tests/engine/capture/test_sqltrace_totals.py::test_totals_max_sql_is_none_before_any_statement` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert '' is None` |
| `tests/engine/capture/test_sqltrace_totals.py::test_totals_survive_clear` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 1` |
| `tests/engine/capture/test_sqltrace_totals.py::test_totals_survive_eviction` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 12` |
| `tests/engine/capture/test_sqltrace_totals.py::test_paused_recorder_adds_nothing` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 0` |
| `tests/engine/test_sqlastats.py::test_maps_totals_onto_dto` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 == 2` |
| `tests/engine/test_sqlastats.py::test_unmeasurable_counters_are_null` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert [NULL_KEYS not None] == []` |
| `tests/engine/test_sqlastats.py::test_cache_is_off_and_counts_zero` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert [CACHE_COUNT_KEYS not 0] == []` |
| `tests/engine/test_sqlastats.py::test_unavailable_without_recorder` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 is False` |
| `tests/engine/test_sqlastats.py::test_unavailable_when_tracing_off` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 is False` |
| `tests/engine/test_sqlastats.py::test_unavailable_mirrors_sqlalchemy_absent` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 == 'SQLAlchemy not imported'` |
| `tests/engine/test_sqlastats.py::test_n_plus_one_per_route` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert 0 == 1` |
| `tests/engine/test_sqlastats.py::test_n_plus_one_merges_requests_of_a_route` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert 0 == 1` |
| `tests/engine/test_sqlastats.py::test_n_plus_one_is_capped` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert 1 == 20` |
| `tests/engine/test_sqlastats.py::test_n_plus_one_never_holds_a_literal_with_parameter_capture` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert 0 == 1` |
| `tests/engine/test_sqlastats.py::test_counts_are_lifetime_n_plus_one_is_window` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 == 500` |
| `tests/engine/test_sqlastats.py::test_uncorrelated_statements_not_in_n_plus_one` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 == 9` |
| `tests/engine/test_sqlastats.py::test_route_unknown_when_exchange_gone` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert 0 == 1` |
| `tests/engine/test_sqlastats.py::test_route_unknown_when_exchanges_disabled` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert 0 == 1` |
| `tests/fastapi/test_sqlalchemy_statistics_api.py::test_get_delegates` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 404 == 200` |
| `tests/fastapi/test_sqlalchemy_statistics_api.py::test_unavailable_mirrors_sql_trace_reason` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 404 == 200` |
| `tests/fastapi/test_sqlalchemy_statistics_api.py::test_enable_returns_report_unchanged` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 404 == 200` |
| `tests/fastapi/test_sqlalchemy_statistics_api.py::test_enable_read_only_403` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 404 == 403` |
| `tests/fastapi/test_sqlalchemy_statistics_api.py::test_mcp_read_tool_only` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 'get_sqlalchemy_statistics' in [...]` |
| `tests/safety/test_a_sqlalchemy_statistics_safety.py::test_get_no_side_effects` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 404 == 200` |
| `tests/masking/test_a_sqlalchemy_statistics_masking.py::test_stripe_key_in_slow_query_never_appears` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 'executionsPerRequest' in 'Not Found body'` |

## UI reds (manual replay)

| UI test (vitest, manual replay) | Commit | Assertion |
|---|---|---|
| `ui/tests/component/sqlalchemyStatistics.test.ts` (3 tests) | `4ee6f59a9d2aa7ea9e54bfdbe7377a2a5d003074` | `expected placeholder text to contain 'not measured'` |

## Evidence

`findings.md`, `field-map.md`, `checklist.md`, `docs.md` in this folder.
