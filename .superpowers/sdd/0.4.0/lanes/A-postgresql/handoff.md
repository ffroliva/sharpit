# Lane A-postgresql handoff

Implementer: agy gemini-4-argon-high + claude-subagent opus (resume)

Status: DONE_WITH_CONCERNS — Tasks 1–7 and fix round 1 complete (resumed by a Claude subagent after Antigravity hit its quota). Concerns: flag-flip fallout in shared catalogue tests and the unverified leased-Postgres run (see Needs from coordinator).

## How to resume

- Worktree: `C:\development\github\sharpit-wt\0.4.0-A-postgresql`
- Branch: `lane/0.4.0-A-postgresql` (base `d37c6f2b00e6acf3f793665ce369c8d359f80ef6`)
- Prefix every `uv` command with `UV_LINK_MODE=copy`.
- Put detached pytest logs outside the worktree: `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\A-postgresql-pytest.log`.
- Do not lease or connect to `localhost:5432`; leased-DB tests skip when `SHARPIT_TEST_POSTGRES_URL` is unset.

## Done (commits)

- Task 0: environment verified (`psycopg 3.3.6` importable).
- Task 1 (`engine/sqla.py` read-only wrapper): red `082a10d89dcbdcdd795759dad9cf6bfb520b30ba`, fix `82888571e0ea055d29a2b8adfb0ae17c43689f7d`.
- Task 2 (query text, row limits): red `afbecc2a011076b0f8cc81813607069846719e0d`; coordinator WIP `f247d7e` (broken: called a non-existent `Masker.mask_value`, all five querytext tests errored with AttributeError); real fix commit `feat: postgresql query text and row limits` (see git log).

- Task 3 (section collectors): red `e2504c7f15c00305ab54c166ccded0700a2ae900`, fix `feat: postgresql catalog section collectors` (see git log).
- Task 4 (report service): red `af231859d2e164fe48214be61e67b4fc1635a1bb`, fix `c3ff9e4` (`feat: postgresql read service`). `test_concurrent_read_is_busy` is not in the red table (its red is pytest's `DID NOT RAISE`, not an assertion).
- Task 5 (routes, MCP, safety, masking): red `6da613bfa2d48b778cf983cabb7a01bf2577a529`, fix `feat: postgresql panel routes and MCP read tool` (see git log). The Python flag `panels04/postgresql.py::IMPLEMENTED` is flipped in Task 5's red (the routes only mount behind it); the UI flag flips in Task 6. `tests/safety/test_a_postgresql_safety.py` and `tests/masking/test_a_postgresql_masking.py` are characterization rows written after the service (green at their first commit, not in the red table).
- Task 6 (Svelte view): red `57b15943b03201e477732893c231446cabde9c45`, fix `feat: postgresql view` (see git log). View file is F's `ui/src/views/PostgreSql.svelte` (F's casing), test `ui/tests/component/postgresql.test.ts`; the view titles itself from `panel.title` so F's `panels04.test.ts` placeholder check still holds. The read button is hidden (not disabled) when read-only, per the lane plan.

## Next step

- Coordinator: leased-Postgres run, catalogue-test updates, UI static rebuild, G0a golden fixture.

## Decisions and deviations

- Following coordinator ruling (00:15): branch starts at `d37c6f2` (`lane/0.4.0-F`); no merge/rebase; `lane_gate.py` not run in worktree; leased-Postgres tests skip when `SHARPIT_TEST_POSTGRES_URL` is unset.
- `run_db_read` unwraps `getattr(engine, "sync_engine", engine)` and reuses an `AsyncEngine` instance directly if one is passed, so both `EngineRegistry`'s `sync_engine` entries and direct `create_async_engine(...)` calls work seamlessly.

- Task 2 `query_text` does NOT go through `normalize_sql` (plan Global Constraints): the BootUI-ported red tests require `'******'` / `$$******$$` literal masks and the raw text under `FULL`, while `normalize_sql` rewrites literals to `?`. Literal masking runs in one regex pass (whichever literal starts first wins; unterminated literals run to the end, as `pg_stat_activity` truncates mid-literal), then `masker.mask_text`, then whitespace collapse and the 400-char cut. Literals are masked exactly when the masker masks a secret value (`masker.mask("password", "x")[1]`), i.e. not under `FULL` or with secret masking off; `METADATA_ONLY` returns `******`.
- Task 2 red test names cite BootUI methods that differ from the plan's list (the red bodies are frozen); `rowsDistinguishEmptyAvailableFromFailedAndCopyRows`, `listQueriesReadOnePastTheBoundAndReportTruncation`, `exactlyTheRowLimitIsNotReportedAsTruncated` are covered by `read_one_past` asserts here and by Task 3/4 section tests.
- Task 1 `bounded_read_only` refuses a non-PostgreSQL dialect with `READ_ONLY_REFUSED` rather than the plan's `Read-only reads are not supported for <dialect>`; both fail closed, and the service (Task 4) skips non-PostgreSQL engines before any read.
- Task 3 DTO keys follow BootUI 2.2.0 `core/dto/Postgres*.java` records exactly (the earlier `field-map.md` draft listed invented keys; rewritten in Task 5). Section order is BootUI's `COLLECTORS` order (settings first: vacuum and replication read its raw values); `SECTION_IDS` keeps `PostgresSectionIds` order.
- Task 3 SQL is BootUI's, with one change: `state like 'idle in transaction%'` becomes `state in ('idle in transaction', 'idle in transaction (aborted)')` because `exec_driver_sql` hands the text to psycopg, which reads `%` as a placeholder (`test_no_query_text_contains_a_percent_sign`). List queries get `limit <max+1>` appended as an integer literal (no bind parameter, no SQLAlchemy import in the collector: `sqla.py` stays the only gatekeeper).
- Task 3 shortcut: BootUI clamps each statement's `setQueryTimeout` to the remaining budget; sharpit pins `statement_timeout` once (5 s) and checks the budget between queries and rows, so a read can overrun the 15 s budget by at most one statement (≤ 5 s); `run_db_read(wall_timeout=15)` still bounds the caller.
- Task 3 reasons go through `masker.mask_text` (house pattern `mask_text(msg) or <label>`), BootUI's `CredentialRedaction` analogue; under `METADATA_ONLY` a failed section says only `<label> could not be read: <ExceptionType>`.
- Task 4: an empty engine registry reports `DISABLED` with BootUI's "No PostgreSQL datasource was found…" (plan Review Focus 5), not BootUI's "No DataSource beans were found to inspect." (no bean concept). BootUI's manual-commit skip maps to `bounded_read_only`'s refusal: the database is `ERROR` with `message = READ_ONLY_REFUSED` and one `ERROR` diagnostic. `serverVersion` comes from the dialect's `server_version_info` read inside the transaction; `message` (BootUI's pin/restore caveat) is always `null` because sharpit never runs a half-pinned read. The NOT_READ text keeps BootUI's CLI hint with `bootui`→`sharpit` (`sharpit db postgres read`).
- Task 5: `engine/tools04/postgresql.py` is F's per-panel stub, filled here (F's table: "for its owning lane to fill"). `postgresql_read` is an action (CLI-only, refused read-only) and answers BootUI's `McpScanSummaries.postgresql` summary; `get_postgresql_report` is the MCP read. CLI paths from BootUI `CliCommandPaths`: `db postgres read`, `db postgres report`. A disabled panel answers the shared 403 (contract §5), so the test is `test_disabled_panel_is_403`.
- Task 5: `test_golden_parity` skips until G0a's `captured.json` (or a coordinator-requested `provisional.json`) exists under `tests/fixtures/bootui/2.2.0/postgresql/`; this lane wrote only `nullable.json`.
- `tests/engine/postgresql/__init__.py` added: without it `tests/engine/postgresql/test_service.py` collides with `tests/engine/vulns/test_service.py` ("import file mismatch" in rootdir import mode); node ids are unchanged.

## Gates (lane head `90ef7be58c18128dcb8c0df7cddd57d7c37fdd8d` + evidence commit)

- `uv run ruff check`: All checks passed. `uv run ruff format --check`: 423 files already formatted. `uv run pyright`: 0 errors.
- `uv run pytest -q -n 4` (log `0.4.0-integration/.superpowers/sdd/0.4.0/logs/A-postgresql-pytest.log`): 3648 passed, 11 skipped, 11 failed.
  - 9 failures are the flag-flip catalogue pins listed under "Needs from coordinator".
  - `tests/fastapi/test_capture_overhead.py::test_request_overhead_budget` also fails on the untouched base `d37c6f2` on this machine (0.253 / 0.270 / 0.237 ms vs 0.200 ms budget, three runs in a temporary worktree): not this lane.
  - `tests/fastapi/test_sql_trace_overhead.py::test_statement_overhead_budget` fails only under `-n 4` load; passes in isolation three times out of three.
- Vitest `npx vitest run` (ui): 32 files, 262 tests passed; `npm run check` (tsc) clean.
- Leased Postgres: not run in the lane (no lease); leased tests skip without `SHARPIT_TEST_POSTGRES_URL`.

## Fix round 1 (coordinator, review.md + ponytail-review.md @ ce3a98e)

Finding → test → red SHA: `findings.md` §Fix round 1. Decisions:
- 1: query text now also masks numeric literals (`******`) and drops comment bodies; E-strings honour backslashes; a plain literal holding an ambiguous `'` (standard_conforming_strings off) is masked to the end of the line. Ruling logged: stricter than BootUI. A lone digit right after a keyword (`SELECT 1`, `LIMIT 5`) is kept: the frozen red `test_query_text_collapses_whitespace_and_truncates_to_400_chars` expects `SELECT 1 FROM pg_stat_activity` verbatim.
- 2: `postgresql_read` (CLI) runs on the app's loop (`run_coroutine_threadsafe`) when it is running; otherwise an async PostgreSQL engine gets a `DISABLED` summary ("Reads of async engines run from the panel only…"); sync engines keep a fresh loop.
- 3: wall timeout = remaining budget + statement timeout + 1 s; a wall timeout keeps the sections already read (database `PARTIAL`, `message` = budget ran out, unread sections `SKIPPED`).
- 4: index/table sizes are computed in an outer query over the LIMITed inner query; the inner order uses `pg_class.relpages` (no lock), so "largest relations" are the largest by heap pages, re-sorted by exact total size.
- 5: deviation from the brief's wording: the timeouts are not re-read with `current_setting('statement_timeout')`, because the frozen red `test_read_only_order` pins the exact statement list (no extra statement before the catalog read). The refused case is the same condition detected without SQL: a DBAPI connection in autocommit (`conn.connection.dbapi_connection.autocommit`) is refused with READ_ONLY_REFUSED, since every `SET LOCAL` then ran in its own transaction.
- 6: setup driver errors propagate as themselves (masked by the service like any engine error); READ_ONLY_REFUSED only for the failed read-only check.
- 7: `LOCK_TIMEOUT` reaches `bounded_read_only` through a new `run_db_read(lock_timeout=)` keyword; `read_list` uses `read_one_past`. Kept on purpose: `sqla.is_internal` and `RowLimits.to_dto`, because the frozen red tests `test_internal_marker_kept` and `test_default_limits_match_properties_contract` call them (editing those bodies would break the gate's red replay).
- 8: without SQLAlchemy 2 the report (GET and POST) is `DISABLED` with `message = sqla.unavailable_reason()`. No `unavailableReason` key was added: the frozen red `test_report_keys_match_the_bootui_records` pins the report's keys. Coordinator: add `reasons["postgresql"] = sqla.unavailable_reason()` in `fastapi/adapter.py::available_reasons` (outside this lane's list).
- 9: `test_async_engine_read_only` uses `asyncio.SelectorEventLoop` on win32; the leased command uses 127.0.0.1.
- 10: new red `test_query_text_masks_strings_and_dollar_quotes_in_one_pass` at `0fb2462` with the WIP two-pass ordering as the stub.
- Fix-round gates at `1f7b101`: ruff check/format clean, pyright 0, pytest -n 4 3661 passed / 11 skipped / 10 failed (the 9 flag-flip catalogue pins + `test_request_overhead_budget`, which fails on base `d37c6f2` too); vitest 263/263, tsc clean.
- UI: rows of every section, the limitations, and the POST's own answer (no second GET).
- Two red commits were redone before anything recorded them (`de7e624` lost the backslashes of its test string; the first `856d23d` sliced the wrong part of the SQL); only the recorded SHAs above count.

## Final round (coordinator, after approval)

- Red `bc21af8195f7dc40d733ad8a1db2d1a6d49a2c57`, fix `155c31b`: after an ambiguous `'` the rest of the query text is masked (not just the line); PostgreSQL 16 numeric forms (`0xDEAD`, `0o17`, `0b101`, `4111_1111`) are masked whole; nested block comments are dropped whole (a depth-counting scan, since a regex cannot nest).
- `test_query_text_masks_a_backslash_escaped_quote_conservatively` (red `e6696c3`, end-of-line rule) is superseded and removed; its row is under `Historical SHA`.
- Checks: targeted tests (postgresql engine, API, safety, masking: 94 passed, 2 skipped; all 81 `Red SHA` tests pass at head), ruff check/format clean, pyright 0 errors.

## Leased-run fix (coordinator, gate/leased-pg.log on PostgreSQL 16)

- Red `f2200178bc8e3f285abbfb1277a15187482b1729`, fix `e1413c8`: `pg_stat_statements` created but not in `shared_preload_libraries` raises SQLSTATE 55000 on every read of the view. The statements section is now `SKIPPED` with "pg_stat_statements is installed but not loaded: add it to shared_preload_libraries." and BootUI's install hint; the savepoint rolls back and every later section runs. BootUI 2.2.0 has no special case here (it would report FAILED); this is a sharpit addition. The SQLSTATE is read from the driver error (`sqlstate` / `pgcode`, or SQLAlchemy's `orig`).
- Not installed at all: `SKIPPED` with "The pg_stat_statements extension is not installed on this server." (`test_an_extension_not_installed_is_skipped_with_a_reason_in_a_full_read`, green at its first commit, so not in the red table).

## Needs from coordinator

- **Flag flip fallout (outside this lane's May-touch; each fails only because it pins the pre-postgresql catalogue/route list — add the postgresql row):**
  - `tests/engine/test_mcp.py::test_tools_list_has_no_action_tool` (MCP list gains `get_postgresql_report`)
  - `tests/engine/test_tools.py::test_catalogue_names_panels_actions_and_schemas` (+`postgresql_read`, `get_postgresql_report`)
  - `tests/fastapi/test_install.py::test_panels_platform_fastapi_and_ids`, `::test_mvp_panels_stay_available` (+`postgresql` panel: 17 vs 16)
  - `tests/fastapi/test_mcp_api.py::test_mcp_server_status_shape` (19 vs 18 tools)
  - `tests/fastapi/test_cli_api.py::test_cli_status_shape_matches_contract` (26 vs 24 tools)
  - `tests/test_foundation_suite_equivalence.py::test_foundation_suite_equivalence` (route list now starts with `/api/postgresql`, `/api/postgresql/read`)
  - `tests/test_safety_matrix.py::test_write_route_table_is_complete` (+`POST /sharpit/api/postgresql/read`), `::test_get_route_table_is_complete` (+`GET /sharpit/api/postgresql`) — C5 file, not editable by this lane.
  - F's `tests/fastapi/test_capture_hooks.py` / `tests/test_foundation_review_fixes.py`: no failure observed from the flip.
- UI: `npm run build` was not run (COMMON forbids it); `src/sharpit/ui/static` must be rebuilt by the coordinator for the CI UI-drift job.
- G0a: `tests/fixtures/bootui/2.2.0/postgresql/captured.json` (or a `provisional.json`) so `test_golden_parity` runs instead of skipping.
- Leased-Postgres run (this lane never connected to a database): `SHARPIT_TEST_POSTGRES_URL=postgresql+psycopg://<user>:<pw>@127.0.0.1:5432/<db> uv run pytest -v tests/engine/test_sqla_read_only.py tests/engine/postgresql/test_sections.py -k "rejects_write or autocommit_engine or async_engine or real_server"`.

## Red-test replay table

| Test id | Red SHA | Assertion message |
|---|---|---|
| tests/engine/test_sqla_read_only.py::test_separate_wall_and_statement_timeouts | 082a10d89dcbdcdd795759dad9cf6bfb520b30ba | assert [5.0] == [15.0] |
| tests/engine/test_sqla_read_only.py::test_read_only_order | 082a10d89dcbdcdd795759dad9cf6bfb520b30ba | assert ['SELECT 1'] == ['SET TRANSACTION READ ONLY', 'SET LOCAL statement_timeout = 5000', 'SET LOCAL lock_timeout = 2000', "SELECT current_setting('transaction_read_only')", 'SELECT 1'] |
| tests/engine/test_sqla_read_only.py::test_autocommit_fails_closed_without_catalog_sql | 082a10d89dcbdcdd795759dad9cf6bfb520b30ba | AssertionError: assert None == 'The read-only transaction could not be established, so sharpit skipped this read' |
| tests/engine/test_sqla_read_only.py::test_read_only_setting_off_fails_closed | 082a10d89dcbdcdd795759dad9cf6bfb520b30ba | AssertionError: assert None == 'The read-only transaction could not be established, so sharpit skipped this read' |
| tests/engine/test_sqla_read_only.py::test_internal_marker_kept | 082a10d89dcbdcdd795759dad9cf6bfb520b30ba | assert False is True |
| tests/engine/postgresql/test_limits.py::test_default_limits_match_properties_contract | afbecc2a011076b0f8cc81813607069846719e0d | AssertionError: assert {'maxSessions...bles': 0, ...} == {'maxSessions...es': 200, ...} |
| tests/engine/postgresql/test_limits.py::test_rejects_non_positive_limits | afbecc2a011076b0f8cc81813607069846719e0d | AssertionError: assert [] == ['max_session...eplicas', ...] |
| tests/engine/postgresql/test_limits.py::test_rejects_integer_max_value_which_cannot_read_one_row_past_the_limit | afbecc2a011076b0f8cc81813607069846719e0d | assert False is True |
| tests/engine/postgresql/test_limits.py::test_reads_from_sharpit_settings_and_env | afbecc2a011076b0f8cc81813607069846719e0d | AssertionError: assert {'maxSessions...bles': 0, ...} == {'maxSessions...les': 50, ...} |
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_single_quoted_escape_and_dollar_quoted_literals | afbecc2a011076b0f8cc81813607069846719e0d | AssertionError: assert '' == 'SELECT * FRO... = $$******$$' |
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_unterminated_string_literals | afbecc2a011076b0f8cc81813607069846719e0d | assert '' == "SELECT * FRO...en = '******'" |
| tests/engine/postgresql/test_querytext.py::test_query_text_preserves_parameter_placeholders_and_identifiers | afbecc2a011076b0f8cc81813607069846719e0d | assert '' == 'SELECT "user...D status = $2' |
| tests/engine/postgresql/test_querytext.py::test_query_text_collapses_whitespace_and_truncates_to_400_chars | afbecc2a011076b0f8cc81813607069846719e0d | AssertionError: assert '' == 'SELECT 1 FRO...stat_activity' |
| tests/engine/postgresql/test_querytext.py::test_query_text_respects_exposure_level | afbecc2a011076b0f8cc81813607069846719e0d | AssertionError: assert '' == '******' |
| tests/engine/postgresql/test_sections.py::test_statement_collector_picks_timing_columns_from_the_extension_not_the_server | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 's.total_time as total_time' in '' |
| tests/engine/postgresql/test_sections.py::test_statement_collector_uses_the_catalog_resolved_view_and_refuses_an_unexpected_name | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'from monitoring.pg_stat_statements s' in '' |
| tests/engine/postgresql/test_sections.py::test_replication_collector_picks_the_checkpoint_view_that_exists | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'pg_stat_bgwriter' in '' |
| tests/engine/postgresql/test_sections.py::test_list_queries_read_one_past_the_bound_and_report_truncation | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_exactly_the_row_limit_is_not_reported_as_truncated | e2504c7f15c00305ab54c166ccded0700a2ae900 | assert 0 == 1 |
| tests/engine/postgresql/test_sections.py::test_missing_pg_stat_statements_extension_is_skipped_with_actionable_hint | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'SKIPPED' |
| tests/engine/postgresql/test_sections.py::test_failed_collector_queries_keep_credential_redacted_reason | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'Index usage statistics could not be read' in '' |
| tests/engine/postgresql/test_sections.py::test_collectors_populate_data_and_report_partial_subsystems_explicitly | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert ['', '', '', '', '', '', ...] == ['settings', ...'vacuum', ...] |
| tests/engine/postgresql/test_sections.py::test_a_failed_query_does_not_poison_later_sections | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_vital_signs_report_the_session_breakdown_as_unknown_when_backends_are_hidden | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'pg_stat_activity hides the state' in '' |
| tests/engine/postgresql/test_sections.py::test_session_client_address_follows_the_exposure_policy | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert '<no row>' == '127.0.0.1' |
| tests/engine/postgresql/test_sections.py::test_replica_client_address_follows_the_exposure_policy | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert '<no row>' == '10.0.0.7/32' |
| tests/engine/postgresql/test_sections.py::test_setting_values_are_withheld_under_metadata_only_but_still_drive_the_rules | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert [] != [] |
| tests/engine/postgresql/test_sections.py::test_settings_exclude_the_timeouts_overridden_by_sharpit | e2504c7f15c00305ab54c166ccded0700a2ae900 | assert 0 == 1 |
| tests/engine/postgresql/test_sections.py::test_a_standby_does_not_present_an_unread_replica_list_as_an_empty_observation | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert None is not None |
| tests/engine/postgresql/test_sections.py::test_a_failed_replica_query_is_unavailable_but_an_empty_successful_query_is_available | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert None is not None |
| tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[settings] | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[sessions] | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[statements] | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[indexes] | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[tables] | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[vacuum] | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[replication] | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'FAILED' == 'AVAILABLE' |
| tests/engine/postgresql/test_sections.py::test_a_budget_exhausted_before_the_first_row_does_not_produce_an_available_empty_list | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 'read budget ran out while reading Table statistics' in '' |
| tests/engine/postgresql/test_sections.py::test_vacuum_due_honours_per_table_reloptions_overrides | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert 0.0 == 10.0 |
| tests/engine/postgresql/test_sections.py::test_vacuum_threshold_floors_so_the_comparison_matches_postgresql | e2504c7f15c00305ab54c166ccded0700a2ae900 | assert 0 == 1049 |
| tests/engine/postgresql/test_sections.py::test_vacuum_threshold_honours_the_postgresql_18_cap | e2504c7f15c00305ab54c166ccded0700a2ae900 | assert 0 == 100000000 |
| tests/engine/postgresql/test_sections.py::test_rows_distinguish_empty_available_from_failed_and_copy_rows | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert ['one', 'two'] == ['one'] |
| tests/engine/postgresql/test_sections.py::test_collect_probes_the_role_then_runs_every_section_in_order | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert None == 'app' |
| tests/engine/postgresql/test_sections.py::test_an_exhausted_budget_skips_the_remaining_sections | e2504c7f15c00305ab54c166ccded0700a2ae900 | AssertionError: assert [] == ['sessions', ...'replication'] |
| tests/engine/postgresql/test_service.py::test_initial_report_touches_neither_discovery_nor_database | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'NOT_READ' |
| tests/engine/postgresql/test_service.py::test_report_keys_match_the_bootui_records | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert ['status', 'm...nostics', ...] == ['localOnly',...sesRead', ...] |
| tests/engine/postgresql/test_service.py::test_a_complete_read_is_read | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'READ' |
| tests/engine/postgresql/test_service.py::test_no_engine_is_disabled | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'DISABLED' |
| tests/engine/postgresql/test_service.py::test_non_postgres_engine_is_skipped | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'DISABLED' |
| tests/engine/postgresql/test_service.py::test_datasource_that_refuses_connections_produces_error_and_diagnostic | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'ERROR' |
| tests/engine/postgresql/test_service.py::test_an_autocommit_connection_is_skipped_before_any_catalog_sql | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'ERROR' |
| tests/engine/postgresql/test_service.py::test_configured_row_limits_reach_every_collector | af231859d2e164fe48214be61e67b4fc1635a1bb | assert [] == [4, 5, 6, 7, 8, 9, ...] |
| tests/engine/postgresql/test_service.py::test_statement_text_goes_through_exposure_policy | af231859d2e164fe48214be61e67b4fc1635a1bb | assert [] == ["select * fr...d = '******'"] |
| tests/engine/postgresql/test_service.py::test_a_role_that_cannot_read_other_backends_degrades_the_session_list_instead_of_looking_quiet | af231859d2e164fe48214be61e67b4fc1635a1bb | assert True is False |
| tests/engine/postgresql/test_service.py::test_an_absent_statement_extension_is_reported_as_a_skipped_section_rather_than_an_empty_one | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'SKIPPED' |
| tests/engine/postgresql/test_service.py::test_an_exhausted_read_budget_is_reported_instead_of_looking_like_a_clean_read | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert '' == 'PARTIAL' |
| tests/engine/postgresql/test_service.py::test_in_memory_previous_read_delta_appears_only_from_second_read_and_is_not_persisted | af231859d2e164fe48214be61e67b4fc1635a1bb | assert [None] == [] |
| tests/engine/postgresql/test_service.py::test_a_partial_read_keeps_the_baseline_of_the_sections_it_could_not_read | af231859d2e164fe48214be61e67b4fc1635a1bb | assert [None] == [] |
| tests/engine/postgresql/test_service.py::test_get_returns_the_last_read_report_after_a_read | af231859d2e164fe48214be61e67b4fc1635a1bb | AssertionError: assert {'status': ''...ics': [], ...} == {'status': ''...Read': 0, ...} |
| tests/fastapi/test_postgresql_api.py::test_get_returns_the_not_read_report_before_any_read | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | assert 404 == 200 |
| tests/fastapi/test_postgresql_api.py::test_read_performs_the_read_and_returns_a_report | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | assert 404 == 200 |
| tests/fastapi/test_postgresql_api.py::test_get_no_side_effects | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | assert 404 == 200 |
| tests/fastapi/test_postgresql_api.py::test_read_only_403[options0] | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | AssertionError: assert 404 == 200 |
| tests/fastapi/test_postgresql_api.py::test_read_only_403[options1] | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | AssertionError: assert 404 == 200 |
| tests/fastapi/test_postgresql_api.py::test_concurrent_read_409 | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | assert 404 == 409 |
| tests/fastapi/test_postgresql_api.py::test_mcp_read_tool_only | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | AssertionError: assert [] == ['get_postgre...tgresql_read'] |
| tests/fastapi/test_postgresql_api.py::test_cli_read_returns_a_summary_without_rows | 6da613bfa2d48b778cf983cabb7a01bf2577a529 | assert 404 == 200 |
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_strings_and_dollar_quotes_in_one_pass | 0fb2462ad60323b6aaa13c1b2f964d1b7e9a129f | assert "SELECT '******'" == "SELECT '****... = $$******$$" |
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_numeric_literals | e6696c338ae38669186ff5e8d248f2a54de2509e | AssertionError: assert 'select * fro...1111111111111' == 'select * fro... pan = ******' |
| tests/engine/postgresql/test_querytext.py::test_query_text_drops_comment_bodies | e6696c338ae38669186ff5e8d248f2a54de2509e | AssertionError: assert 'select 1 /* ... note where x' == 'select 1 from t where x' |
| tests/engine/postgresql/test_sections.py::test_relation_sizes_are_read_only_for_the_limited_rows[INDEXES_SQL] | aca4ddf5a5ee67df499b8c2ae64e2fb3894dd81b | AssertionError: assert -1 > -1 |
| tests/engine/postgresql/test_sections.py::test_relation_sizes_are_read_only_for_the_limited_rows[TABLES_SQL] | aca4ddf5a5ee67df499b8c2ae64e2fb3894dd81b | AssertionError: assert -1 > -1 |
| tests/engine/postgresql/test_sections.py::test_list_query_limit_is_applied_inside_the_sized_subquery | aca4ddf5a5ee67df499b8c2ae64e2fb3894dd81b | AssertionError: assert 1 == 2 |
| tests/engine/test_sqla_read_only.py::test_autocommit_on_a_read_only_server_fails_closed | db41c75b581e00056d9cd31ec0d9720b8fb0afd1 | AssertionError: assert None == 'The read-only transaction could not be established, so sharpit skipped this read' |
| tests/engine/postgresql/test_service.py::test_a_connection_error_during_setup_reports_the_masked_driver_message | d08944eb4139b1e8b0915fb10c8cd7257cd9cd98 | AssertionError: assert 'server closed the connection unexpectedly' in 'The read-only transaction could not be established, so sharpit skipped this rea |
| tests/engine/postgresql/test_service.py::test_a_wall_timeout_keeps_the_sections_already_read | d64b4b45b5f96907014185f9b57b01ae2850b217 | AssertionError: assert 'ERROR' == 'PARTIAL' |
| tests/fastapi/test_postgresql_api.py::test_cli_read_refuses_an_async_engine_outside_the_app_loop | 98130999f26d8edb2b6f84731e6e6b8565184633 | AssertionError: assert 'ERROR' == 'DISABLED' |
| tests/engine/postgresql/test_service.py::test_without_sqlalchemy_2_the_panel_reports_why | 342f13eb366fa0b56e427a3d15416ede66caede7 | AssertionError: assert ('NOT_READ', ...stics views.') == ('DISABLED', ...2.0 or later') |
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_an_ambiguous_backslash_quote_to_the_end_of_the_text | bc21af8195f7dc40d733ad8a1db2d1a6d49a2c57 | assert "select '****... pin = secret" == "select '******'" |
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_postgresql_16_numeric_forms_whole | bc21af8195f7dc40d733ad8a1db2d1a6d49a2c57 | AssertionError: assert 'select a fro...= ******_1111' == 'select a fro...nd p = ******' |
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_nested_comments_whole | bc21af8195f7dc40d733ad8a1db2d1a6d49a2c57 | AssertionError: assert 'select a secret */ from t' == 'select a from t' |
| tests/engine/postgresql/test_sections.py::test_an_extension_created_but_not_preloaded_is_skipped_and_later_sections_still_run | f2200178bc8e3f285abbfb1277a15187482b1729 | AssertionError: assert 'FAILED' == 'SKIPPED' |

## Superseded red tests

| Test id | Historical SHA | Assertion message |
|---|---|---|
| tests/engine/postgresql/test_querytext.py::test_query_text_masks_a_backslash_escaped_quote_conservatively | e6696c338ae38669186ff5e8d248f2a54de2509e | assert 'secret' not in "select '***...cret'******'" |

Superseded by `tests/engine/postgresql/test_querytext.py::test_query_text_masks_an_ambiguous_backslash_quote_to_the_end_of_the_text` (final round: mask to the end of the text, not the line); the old test function was removed.

## UI (vitest) red tests

| Test | Commit | Assertion message |
|---|---|---|
| Vitest: ui/tests/component/postgresql.test.ts::NOT_READ shows the message and the read button, and nothing reads on open | 57b15943b03201e477732893c231446cabde9c45 | AssertionError: expected 'postgresqlThis panel's view is not b…' to contain 'The database has not been read yet. R…' |
| Vitest: ui/tests/component/postgresql.test.ts::a read renders each section with its status, reason and hint | 57b15943b03201e477732893c231446cabde9c45 | AssertionError: expected undefined to be defined |
| Vitest: ui/tests/component/postgresql.test.ts::changes render only when the read carries them (the second read) | 57b15943b03201e477732893c231446cabde9c45 | AssertionError: expected 'postgresqlThis panel's view is not b…' to contain 'Statement ranking' |
| Vitest: ui/tests/component/postgresql.test.ts::read-only hides the read button and says why | 57b15943b03201e477732893c231446cabde9c45 | AssertionError: expected 'postgresqlThis panel's view is not b…' to contain 'The database has not been read yet. R…' |
| Vitest: ui/tests/component/postgresql.test.ts::renders the section rows and limitations from the POST answer without a second GET | d786b517ca6f94176c2f268860c9e40b8fa547a1 | AssertionError: expected 'postgresql Read PostgreSQL NOT_READ ·…' to contain 'orders_archive' |

