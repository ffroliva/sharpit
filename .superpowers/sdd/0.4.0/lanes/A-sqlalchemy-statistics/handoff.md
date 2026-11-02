# Lane A-sqlalchemy-statistics handoff

Implementer: claude-flavio sonnet + claude-subagent opus (fix round)
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/A-sqlalchemy-statistics.md`
Branch / worktree: `lane/0.4.0-A-sqlalchemy-statistics` in `C:\development\github\sharpit-wt\0.4.0-A-sqlalchemy-statistics`

## Status

- Done: Task 1 (`nullable.json`), Task 2 totals (fix `1b1e47dd`), Task 3 collector (fix `3316b806`), Task 4 routes/MCP/safety/masking (fix `5bb3ae9d`), Task 5 view (fix `21746fe1`), Task 6 live check and evidence.
- Status: DONE_WITH_CONCERNS (two shared tests need coordinator edits, below).
- Review-fix round (red `bf3c9a3e`, fix `44e30a35`, complexity refactor `fe1be95c`): ruff check clean, ruff format --check clean (420 files), pyright 0 errors, vitest 32 files / 262 tests passed, `npm --prefix ui run check` clean. Full suite `-n 4` at `44e30a35`: 3805 passed, 5 skipped, 4 failed, 1 error (log `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-sqlalchemy-statistics-fix-pytest.log`): `test_complexity_only_goes_down` (record() went to complexity 11; fixed in `fe1be95c`, `tests/test_code_shape.py` green after), the two known F-rest items below (safety matrix row, surface-flags fixture), and the two overhead budgets. Budgets are noise here: paired runs of `test_sql_trace_overhead.py` alternated pass/fail for both `fe1be95c` and lane head `2e2cce7` (53-64 µs vs 50, noise 37-45 µs); the capture budget fails with "within the noise" (0.308 ms overhead, 0.369 ms noise). Budgets untouched.
- Open findings: see Needs from coordinator.

## Needs from coordinator (files outside my May-touch list)

1. `tests/test_safety_matrix.py::test_write_route_table_is_complete` fails: the new route `POST /sharpit/api/sqlalchemy-statistics/enable` needs a `WRITES` row (protected file, C5).
2. `tests/test_surface_follows_flags.py::test_every_shared_count_follows_a_flag_flip` errors in its fixture: `tools.TOOLS` is built at import with my flag already True, so the fixture's `merge_lane_tools(tools.TOOLS, ..., lane_tools)` sees `get_sqlalchemy_statistics` twice and raises `ValueError: lane tool name(s) collide`. Any lane that flips its flag will hit this; the fixture should merge only the planted tool.
3. `test_capture_overhead.py::test_request_overhead_budget` and `test_sql_trace_overhead.py::test_statement_overhead_budget` failed in the loaded full run. Not caused by this lane: base `a766132` source gives 0.276 ms against the 0.200 ms capture budget in the same environment (one rerun passed); the SQL Trace budget passed in isolation. Budgets not raised.
4. The UI test is `ui/tests/component/sqlalchemyStatistics.test.ts` (repo convention and vitest include pattern), not beside the view.
5. `src/sharpit/ui/static/` is not rebuilt (lanes never run `npm run build`).

## How to resume

All work is committed. Rerun `UV_LINK_MODE=copy uv run pytest -q -n 4` (log outside the worktree), and in `ui/`: `npm run check`, `npx vitest run`.

## Review fixes (review.md, ponytail-review.md, code-review xhigh)

| # | Finding | Test | Red commit | Disposition |
|---|---|---|---|---|
| 1 | `max_sql` stored unmasked; a double-quoted `sk_live_` leaked with capture_parameters | `test_max_sql_masks_a_double_quoted_secret_with_parameter_capture` | `bf3c9a3e` | Fixed in `44e30a35`: `masker.mask_text(normalized.sql)` on each new max |
| 2 | N+1 link used the endpoint name; HTTP Exchanges filters on path | `test_n_plus_one_carries_the_request_path`, `test_n_plus_one_link_finds_the_request_in_http_exchanges`, vitest routePath | `bf3c9a3e` | Fixed in `44e30a35`: entry carries `routePath`, the view links with it; `route` stays the endpoint |
| 3 | GET re-normalised stored (truncated, raw) rows | `test_long_statements_with_varying_literals_are_one_shape`, `test_get_does_not_normalize` | `bf3c9a3e` | Fixed in `44e30a35`: each ring row keeps the recorder's `Normalized` under internal key `shape` (dropped by `entry_dto`); N+1 groups by its fingerprint and masks the output SQL |
| 4 | `route_of` scanned the exchange buffer per group | `test_route_lookup_does_not_scan_per_group` | `bf3c9a3e` | Fixed in `44e30a35`: one `{id: row}` index per report |
| 5 | Disabled sql-trace panel reported as SQL tracing disabled | `test_unavailable_when_sql_trace_panel_disabled` | `bf3c9a3e` | Fixed in `44e30a35`: `panels.disabled_reason("sql-trace")` first |
| 6 | Paused recording not reported | `test_paused_recording_is_a_warning`, `test_paused_recording_stays_available`, vitest warning | `bf3c9a3e` | Fixed in `44e30a35`: `statistics.warnings` = `[RECORDING_PAUSED]`; `available` stays true |
| 7 | maxTime/maxSql counted DML and survived clear | `test_max_time_counts_selects_only`, `test_max_sql_is_a_select`, `test_clear_resets_max_time`, `test_clear_resets_max_sql`, `test_max_after_clear_is_the_next_select` | `bf3c9a3e` | Fixed in `44e30a35`: SELECT-only, reset by `clear()`; counts still survive clear (`test_counts_survive_clear`) |
| 8 | duplicate `_statements`; collector imported engine.tools; decoration vitest; NULL_REASON drift | `test_null_reason_matches_nullable_json`, vitest tooltip | `bf3c9a3e` | Fixed in `44e30a35`: `_total` reused; `sql_trace_unavailable_reason`/`sqlite3_traced` moved to `engine/sqla.py` (tools imports it); decoration vitest removed; one reason text in Python, UI and nullable.json |

## Open minors (skipped on purpose)

- Live refresh of the view via the change stream (it loads once).
- Activity's N+1 threshold (`activity_n_plus_one_threshold`) and this panel's (`sql_trace_n_plus_one_threshold`) are separate settings; unifying them is a later call.
- In-flight requests: an N+1 for a request whose exchange row is not yet written shows `unknown route`.

## Decisions

- Extra keys (`statementCount`, `nPlusOne`, `nPlusOneWindow`) live inside `statistics`.
- N+1 `route` is the exchange `endpoint` (module:qualname) when set, else its path; `routePath` is the request path (the HTTP Exchanges link); an unknown exchange gives null `method`/`route`/`routePath` and a `routeReason`.
- `max_sql` is the slowest SELECT since the last clear, normalised then masked, truncated to `max_sql_length`, never raw text.
- `sql_trace_unavailable_reason` lives in `engine/sqla.py`; the collector no longer imports `engine.tools`.
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
| `tests/masking/test_a_sqlalchemy_statistics_masking.py::test_stripe_key_in_slow_query_never_appears` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 'executionsPerRequest' in 'Not Found body'` |
| `tests/engine/capture/test_sqltrace_totals.py::test_max_sql_masks_a_double_quoted_secret_with_parameter_capture` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 'sk_live_4eC...arjtT1zdp7dc' not in 'select * fr...rjtT1zdp7dc"'` |
| `tests/engine/capture/test_sqltrace_totals.py::test_max_time_counts_selects_only` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 50 == 5` |
| `tests/engine/capture/test_sqltrace_totals.py::test_max_sql_is_a_select` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 'update t set a = ?' == 'select a from t where id = ?'` |
| `tests/engine/capture/test_sqltrace_totals.py::test_clear_resets_max_time` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 9 == 0` |
| `tests/engine/capture/test_sqltrace_totals.py::test_clear_resets_max_sql` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 'select ?' is None` |
| `tests/engine/capture/test_sqltrace_totals.py::test_max_after_clear_is_the_next_select` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 9 == 3` |
| `tests/engine/test_sqlastats.py::test_n_plus_one_carries_the_request_path` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert None == '/pets'` |
| `tests/engine/test_sqlastats.py::test_long_statements_with_varying_literals_are_one_shape` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 0 == 1` |
| `tests/engine/test_sqlastats.py::test_get_does_not_normalize` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert ['select * fr...owner_id = ?'] == []` |
| `tests/engine/test_sqlastats.py::test_route_lookup_does_not_scan_per_group` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert ['r1'] == []` |
| `tests/engine/test_sqlastats.py::test_unavailable_when_sql_trace_panel_disabled` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 'SQL tracing ...ENABLED=false' == 'Panel is dis...ENABLED=false'` |
| `tests/engine/test_sqlastats.py::test_paused_recording_is_a_warning` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert None == ['']` |
| `tests/engine/test_sqlastats.py::test_null_reason_matches_nullable_json` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert {'SQLAlchemy ...tions panel)'} == {'SQLAlchemy ...y operations'}` |
| `tests/fastapi/test_sqlalchemy_statistics_api.py::test_n_plus_one_link_finds_the_request_in_http_exchanges` | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `assert 0 >= 1` |

## Superseded reds

| Test id | Historical SHA | Why superseded |
|---|---|---|
| `tests/engine/capture/test_sqltrace_totals.py::test_totals_survive_clear` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | review #7: `clear()` now resets max time/SQL; replaced by `test_counts_survive_clear`, `test_clear_resets_max_time`, `test_clear_resets_max_sql` (removed in `44e30a35`) |
| `tests/engine/test_sqlastats.py::test_n_plus_one_is_capped` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | review #3: fed hand-built rows without the stored fingerprint; replaced by `test_n_plus_one_is_capped_from_the_recorder` (removed in `44e30a35`) |
| `tests/safety/test_a_sqlalchemy_statistics_safety.py::test_get_no_side_effects` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | superseded: the module-level `sa` skip became a non-skipping binding so the safety matrix can load the rows (red was `assert 404 == 200`) |

## UI reds (manual replay)

| UI test (vitest, manual replay) | Commit | Assertion |
|---|---|---|
| `ui/tests/component/sqlalchemyStatistics.test.ts` (3 tests) | `4ee6f59a9d2aa7ea9e54bfdbe7377a2a5d003074` | `expected placeholder text to contain 'not measured'` |
| `ui/tests/component/sqlalchemyStatistics.test.ts` > the N+1 link filters HTTP Exchanges by the request path | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `expected '#/http-exchanges?q=app%3Alist_pets' to be '#/http-exchanges?q=%2Fpets'` |
| `ui/tests/component/sqlalchemyStatistics.test.ts` > the not-measured tooltip is the nullable.json reason | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `expected '...entity operations' to be '...entity operations (transactions live in the transactions panel)'` |
| `ui/tests/component/sqlalchemyStatistics.test.ts` > a paused-recording warning is shown | `bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77` | `expected '...' to contain 'SQL Trace recording is paused: ...'` |

Removed vitests (in `44e30a35`): "the N+1 table links the route to HTTP Exchanges" (pinned the qualname href, review #2; superseded by the routePath test) and "enableAvailable false shows no enable button" (decoration: the view never renders such a button).

## Evidence

`findings.md`, `field-map.md`, `checklist.md`, `docs.md` in this folder.
