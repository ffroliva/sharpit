# Lane A-postgresql handoff

Status: IN_PROGRESS — Tasks 1–3 complete (resumed by a Claude subagent after Antigravity hit its quota); next Task 4.

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

## Next step

- Task 4: `service.py` (report, refresh, comparison) + `tests/engine/postgresql/test_service.py`.

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

## Needs from coordinator

- None yet.

## Red-test replay table

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/test_sqla_read_only.py::test_separate_wall_and_statement_timeouts` | `082a10d89dcbdcdd795759dad9cf6bfb520b30ba` | `assert [5.0] == [15.0]` |
| `tests/engine/test_sqla_read_only.py::test_read_only_order` | `082a10d89dcbdcdd795759dad9cf6bfb520b30ba` | `assert ['SELECT 1'] == ['SET TRANSACTION READ ONLY', 'SET LOCAL statement_timeout = 5000', 'SET LOCAL lock_timeout = 2000', "SELECT current_setting('transaction_read_only')", 'SELECT 1']` |
| `tests/engine/test_sqla_read_only.py::test_autocommit_fails_closed_without_catalog_sql` | `082a10d89dcbdcdd795759dad9cf6bfb520b30ba` | `AssertionError: assert None == 'The read-only transaction could not be established, so sharpit skipped this read'` |
| `tests/engine/test_sqla_read_only.py::test_read_only_setting_off_fails_closed` | `082a10d89dcbdcdd795759dad9cf6bfb520b30ba` | `AssertionError: assert None == 'The read-only transaction could not be established, so sharpit skipped this read'` |
| `tests/engine/test_sqla_read_only.py::test_internal_marker_kept` | `082a10d89dcbdcdd795759dad9cf6bfb520b30ba` | `assert False is True` |
| `tests/engine/postgresql/test_limits.py::test_default_limits_match_properties_contract` | `afbecc2a011076b0f8cc81813607069846719e0d` | `AssertionError: assert {'maxSessions...bles': 0, ...} == {'maxSessions...es': 200, ...}` |
| `tests/engine/postgresql/test_limits.py::test_rejects_non_positive_limits` | `afbecc2a011076b0f8cc81813607069846719e0d` | `AssertionError: assert [] == ['max_session...eplicas', ...]` |
| `tests/engine/postgresql/test_limits.py::test_rejects_integer_max_value_which_cannot_read_one_row_past_the_limit` | `afbecc2a011076b0f8cc81813607069846719e0d` | `assert False is True` |
| `tests/engine/postgresql/test_limits.py::test_reads_from_sharpit_settings_and_env` | `afbecc2a011076b0f8cc81813607069846719e0d` | `AssertionError: assert {'maxSessions...bles': 0, ...} == {'maxSessions...les': 50, ...}` |
| `tests/engine/postgresql/test_querytext.py::test_query_text_masks_single_quoted_escape_and_dollar_quoted_literals` | `afbecc2a011076b0f8cc81813607069846719e0d` | `AssertionError: assert '' == 'SELECT * FRO... = $$******$$'` |
| `tests/engine/postgresql/test_querytext.py::test_query_text_masks_unterminated_string_literals` | `afbecc2a011076b0f8cc81813607069846719e0d` | `assert '' == "SELECT * FRO...en = '******'"` |
| `tests/engine/postgresql/test_querytext.py::test_query_text_preserves_parameter_placeholders_and_identifiers` | `afbecc2a011076b0f8cc81813607069846719e0d` | `assert '' == 'SELECT "user...D status = $2'` |
| `tests/engine/postgresql/test_querytext.py::test_query_text_collapses_whitespace_and_truncates_to_400_chars` | `afbecc2a011076b0f8cc81813607069846719e0d` | `AssertionError: assert '' == 'SELECT 1 FRO...stat_activity'` |
| `tests/engine/postgresql/test_querytext.py::test_query_text_respects_exposure_level` | `afbecc2a011076b0f8cc81813607069846719e0d` | `AssertionError: assert '' == '******'` |
| `tests/engine/postgresql/test_sections.py::test_statement_collector_picks_timing_columns_from_the_extension_not_the_server` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 's.total_time as total_time' in ''` |
| `tests/engine/postgresql/test_sections.py::test_statement_collector_uses_the_catalog_resolved_view_and_refuses_an_unexpected_name` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'from monitoring.pg_stat_statements s' in ''` |
| `tests/engine/postgresql/test_sections.py::test_replication_collector_picks_the_checkpoint_view_that_exists` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'pg_stat_bgwriter' in ''` |
| `tests/engine/postgresql/test_sections.py::test_list_queries_read_one_past_the_bound_and_report_truncation` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_exactly_the_row_limit_is_not_reported_as_truncated` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `assert 0 == 1` |
| `tests/engine/postgresql/test_sections.py::test_missing_pg_stat_statements_extension_is_skipped_with_actionable_hint` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'SKIPPED'` |
| `tests/engine/postgresql/test_sections.py::test_failed_collector_queries_keep_credential_redacted_reason` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'Index usage statistics could not be read' in ''` |
| `tests/engine/postgresql/test_sections.py::test_collectors_populate_data_and_report_partial_subsystems_explicitly` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert ['', '', '', '', '', '', ...] == ['settings', ...'vacuum', ...]` |
| `tests/engine/postgresql/test_sections.py::test_a_failed_query_does_not_poison_later_sections` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_vital_signs_report_the_session_breakdown_as_unknown_when_backends_are_hidden` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'pg_stat_activity hides the state' in ''` |
| `tests/engine/postgresql/test_sections.py::test_session_client_address_follows_the_exposure_policy` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert '<no row>' == '127.0.0.1'` |
| `tests/engine/postgresql/test_sections.py::test_replica_client_address_follows_the_exposure_policy` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert '<no row>' == '10.0.0.7/32'` |
| `tests/engine/postgresql/test_sections.py::test_setting_values_are_withheld_under_metadata_only_but_still_drive_the_rules` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert [] != []` |
| `tests/engine/postgresql/test_sections.py::test_settings_exclude_the_timeouts_overridden_by_sharpit` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `assert 0 == 1` |
| `tests/engine/postgresql/test_sections.py::test_a_standby_does_not_present_an_unread_replica_list_as_an_empty_observation` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert None is not None` |
| `tests/engine/postgresql/test_sections.py::test_a_failed_replica_query_is_unavailable_but_an_empty_successful_query_is_available` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert None is not None` |
| `tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[settings]` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[sessions]` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[statements]` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[indexes]` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[tables]` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[vacuum]` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_every_list_collector_preserves_rows_and_the_budget_reason[replication]` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'FAILED' == 'AVAILABLE'` |
| `tests/engine/postgresql/test_sections.py::test_a_budget_exhausted_before_the_first_row_does_not_produce_an_available_empty_list` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 'read budget ran out while reading Table statistics' in ''` |
| `tests/engine/postgresql/test_sections.py::test_vacuum_due_honours_per_table_reloptions_overrides` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert 0.0 == 10.0` |
| `tests/engine/postgresql/test_sections.py::test_vacuum_threshold_floors_so_the_comparison_matches_postgresql` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `assert 0 == 1049` |
| `tests/engine/postgresql/test_sections.py::test_vacuum_threshold_honours_the_postgresql_18_cap` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `assert 0 == 100000000` |
| `tests/engine/postgresql/test_sections.py::test_rows_distinguish_empty_available_from_failed_and_copy_rows` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert ['one', 'two'] == ['one']` |
| `tests/engine/postgresql/test_sections.py::test_collect_probes_the_role_then_runs_every_section_in_order` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert None == 'app'` |
| `tests/engine/postgresql/test_sections.py::test_an_exhausted_budget_skips_the_remaining_sections` | `e2504c7f15c00305ab54c166ccded0700a2ae900` | `AssertionError: assert [] == ['sessions', ...'replication']` |

