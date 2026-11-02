# Lane A-postgresql findings and red-test log

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

## Review / implementation findings

| Finding | Test | Status |
|---|---|---|
| WIP `f247d7e` `query_text` called non-existent `Masker.mask_value` (AttributeError on every call) | `tests/engine/postgresql/test_querytext.py::*` (red at `afbecc2`, errored at `f247d7e`) | fixed in Task 2 fix commit |
| WIP dollar-quote regex ran before the string regex, so a `$tag$` inside a string literal could swallow text across literal boundaries | `tests/engine/postgresql/test_querytext.py::test_query_text_masks_single_quoted_escape_and_dollar_quoted_literals` | fixed: single-pass alternation; regression `tests/engine/postgresql/test_querytext.py::test_query_text_a_dollar_inside_a_string_is_not_a_dollar_quote` added after the fix (not replayed at a red SHA) |
| `field-map.md` draft (Antigravity) listed DTO keys that do not exist in BootUI 2.2.0 (`readAt`, `durationMillis`, `sourceCount`, `PostgresSectionDto.available`, ...) | rewritten from `core/dto/Postgres*.java` in Task 5; `tests/fastapi/test_postgresql_api.py` key checks | fixed in Task 5 |

## Fix round 1 (review.md / ponytail-review.md @ ce3a98e)

| Finding | Test | Red commit | Red assertion |
|---|---|---|---|
| 10 dollar-quote ordering never seen red | `tests/engine/postgresql/test_querytext.py::test_query_text_masks_strings_and_dollar_quotes_in_one_pass` | `0fb2462ad60323b6aaa13c1b2f964d1b7e9a129f` | `assert "SELECT '******'" == "SELECT '****... = $$******$$"` |
| 1 numbers/comments/backslash unmasked | `tests/engine/postgresql/test_querytext.py::test_query_text_masks_numeric_literals` | `e6696c338ae38669186ff5e8d248f2a54de2509e` | `AssertionError: assert 'select * fro...1111111111111' == 'select * fro... pan = ******'` |
| 1 numbers/comments/backslash unmasked | `tests/engine/postgresql/test_querytext.py::test_query_text_drops_comment_bodies` | `e6696c338ae38669186ff5e8d248f2a54de2509e` | `AssertionError: assert 'select 1 /* ... note where x' == 'select 1 from t where x'` |
| 1 numbers/comments/backslash unmasked | `tests/engine/postgresql/test_querytext.py::test_query_text_masks_a_backslash_escaped_quote_conservatively` | `e6696c338ae38669186ff5e8d248f2a54de2509e` | `assert 'secret' not in "select '***...cret'******'"` |
| 4 relation sizes on every relation | `tests/engine/postgresql/test_sections.py::test_relation_sizes_are_read_only_for_the_limited_rows[INDEXES_SQL]` | `aca4ddf5a5ee67df499b8c2ae64e2fb3894dd81b` | `AssertionError: assert -1 > -1` |
| 4 relation sizes on every relation | `tests/engine/postgresql/test_sections.py::test_relation_sizes_are_read_only_for_the_limited_rows[TABLES_SQL]` | `aca4ddf5a5ee67df499b8c2ae64e2fb3894dd81b` | `AssertionError: assert -1 > -1` |
| 4 relation sizes on every relation | `tests/engine/postgresql/test_sections.py::test_list_query_limit_is_applied_inside_the_sized_subquery` | `aca4ddf5a5ee67df499b8c2ae64e2fb3894dd81b` | `AssertionError: assert 1 == 2` |
| 5 timeouts not in effect under AUTOCOMMIT | `tests/engine/test_sqla_read_only.py::test_autocommit_on_a_read_only_server_fails_closed` | `db41c75b581e00056d9cd31ec0d9720b8fb0afd1` | `AssertionError: assert None == 'The read-only transaction could not be established, so sharpit skipped this read'` |
| 6 setup errors reported as READ_ONLY_REFUSED | `tests/engine/postgresql/test_service.py::test_a_connection_error_during_setup_reports_the_masked_driver_message` | `d08944eb4139b1e8b0915fb10c8cd7257cd9cd98` | `AssertionError: assert 'server closed the connection unexpectedly' in 'The read-only transaction could not be established, so sharpit skipped this rea` |
| 3 wall timeout equals budget, partial read lost | `tests/engine/postgresql/test_service.py::test_a_wall_timeout_keeps_the_sections_already_read` | `d64b4b45b5f96907014185f9b57b01ae2850b217` | `AssertionError: assert 'ERROR' == 'PARTIAL'` |
| 2 CLI drives an async pool on a second loop | `tests/fastapi/test_postgresql_api.py::test_cli_read_refuses_an_async_engine_outside_the_app_loop` | `98130999f26d8edb2b6f84731e6e6b8565184633` | `AssertionError: assert 'ERROR' == 'DISABLED'` |
| 8 no unavailable reason without SQLAlchemy 2 | `tests/engine/postgresql/test_service.py::test_without_sqlalchemy_2_the_panel_reports_why` | `342f13eb366fa0b56e427a3d15416ede66caede7` | `AssertionError: assert ('NOT_READ', ...stics views.') == ('DISABLED', ...2.0 or later')` |
| UI rows/limitations/POST answer | `Vitest: ui/tests/component/postgresql.test.ts::renders the section rows and limitations from the POST answer without a second GET` | `d786b517ca6f94176c2f268860c9e40b8fa547a1` | `AssertionError: expected 'postgresql Read PostgreSQL NOT_READ ·…' to contain 'orders_archive'` |
