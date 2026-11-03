# Findings: lane A-dbadv-1 (0.5.0)

Every red below was checked with `uv run python scripts/dev/red_check.py` before its `test:` commit: `RED (assertion
under tests/)` for each one. Task 3's red commit was amended once before any fix existed (ruff format/E501 on the new
test files only; `red_check` re-run on the amended tree: 34 RED); its SHA below is the amended one.

## Reds

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/test_sqla_inspect.py::test_table_bound_truncates | dbe78b8de480a339d775d40afa8340fed72ffc68 | skeleton `catalog` returned an empty catalog: count/flag assertion | Fixed in 110f166 |
| tests/engine/test_sqla_inspect.py::test_index_bound_per_table | dbe78b8de480a339d775d40afa8340fed72ffc68 | skeleton `catalog` returned an empty catalog: count/flag assertion | Fixed in 110f166 |
| tests/engine/test_sqla_inspect.py::test_column_bound_per_table | dbe78b8de480a339d775d40afa8340fed72ffc68 | skeleton `catalog` returned an empty catalog: count/flag assertion | Fixed in 110f166 |
| tests/engine/test_sqla_inspect.py::test_catalog_inside_read_only_wrapper | dbe78b8de480a339d775d40afa8340fed72ffc68 | skeleton `catalog` returned an empty catalog: count/flag assertion | Fixed in 110f166 |
| tests/engine/test_sqla_inspect.py::test_catalog_timeout_is_a_diagnostic | dbe78b8de480a339d775d40afa8340fed72ffc68 | skeleton `catalog` returned an empty catalog: count/flag assertion | Fixed in 110f166 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_missing_primary_key_is_reported | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_migration_bookkeeping_table_is_not_a_missing_primary_key | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_unread_datasource_is_skipped_rather_than_passed | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_foreign_key_without_leading_index_is_reported | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_foreign_key_access_path_accepts_leading_columns_in_either_order | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_truncated_index_inventory_cannot_prove_an_absent_access_path | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_exact_duplicate_indexes_are_one_pair | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_expression_or_differently_configured_indexes_are_not_duplicates | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_foreign_key_type_mismatch_uses_the_referenced_column | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_identical_declarations_are_not_a_type_mismatch | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_unique_index_on_the_primary_key_columns_is_reported | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_duplicate_foreign_keys_need_identical_pairs_and_actions | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_generated_small_key_is_reported | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_schema.py::test_finding_identity_never_holds_a_value | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: target/identity list assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_engine_echo_is_reported | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_engine_without_echo_passes | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_missing_connect_timeout_is_reported_for_libpq_style_drivers | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_configured_connect_timeout_passes | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_connect_timeout_rule_skips_drivers_with_their_own_default | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_idle_limit_fires_when_nothing_retires_or_pings_the_connection | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_idle_limit_fires_when_the_lifetime_is_not_shorter_than_the_server_limit | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_idle_limit_is_covered_by_a_shorter_lifetime_or_pre_ping | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_postgres_uses_idle_session_timeout_in_milliseconds_and_ignores_it_when_disabled | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_idle_limit_is_skipped_when_the_server_limit_is_unknown | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_pool_rules_ignore_dialects_they_do_not_judge | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_a_pool_larger_than_the_usable_connections_fires_the_capacity_rule_and_not_the_share_rule | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_an_unbounded_overflow_exceeds_any_server_limit | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_a_pool_over_half_the_usable_connections_fires_the_share_heuristic | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_the_pool_share_boundary_uses_exact_integer_arithmetic | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_the_capacity_rules_need_a_readable_server_limit | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_an_unlimited_lifetime_is_reported_when_the_idle_limit_rule_does_not_own_the_datasource | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_an_unlimited_lifetime_is_not_reported_twice_when_the_idle_limit_rule_fires | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_an_unlimited_lifetime_is_undecided_while_ownership_is_unsettled | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_a_limited_lifetime_is_not_reported | f534c99e1acf63a1386fefc51b15994a7860aab0 | skeleton check returned `[('', '', '')]`: identity list / skip-reason assertion | Fixed in f9d6006 |
| tests/fastapi/test_database_advisor_api.py::test_report_golden_parity | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_scan_reports_schema_findings_on_sqlite | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_get_before_a_scan_never_connects | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_dbadv_read_uses_verified_read_only_path | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_autocommit_engine_is_unavailable | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_read_only_blocks_scan | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_concurrent_scan_409 | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_mcp_tools_list_has_only_get | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_cli_scan_and_commands | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_changes_and_rule_detail_routes | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/fastapi/test_database_advisor_api.py::test_query_string_secret_never_read_or_emitted | 31bce506ef98a64b0064d099b332356342799075 | flag on, `build_routes` returned no route: `assert 404 == 200` (or the 403/409/MCP-list assertion) | Fixed in f2e1e23 |
| tests/masking/test_a_database_advisor_masking.py::test_driver_error_dsn_password_masked | 31bce506ef98a64b0064d099b332356342799075 | skeleton `run_scan` returned `{}`: `assert [] == ['FAILED']` | Fixed in f2e1e23 |
| tests/masking/test_a_database_advisor_masking.py::test_statement_text_masked | 31bce506ef98a64b0064d099b332356342799075 | skeleton `run_scan` returned `{}`: `assert [] == ['FAILED']` | Fixed in f2e1e23 |
| tests/safety/test_a_database_advisor_safety.py::test_database_advisor_get_no_side_effects | 31bce506ef98a64b0064d099b332356342799075 | no route: `assert 404 == 200` | Fixed in f2e1e23 |

## Pins (passed on first run; mutation-proven in place, each mutation reverted with `git checkout`)

| Test | Historical SHA | Mutation | Failure under the mutation |
|---|---|---|---|
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_password_never_read | f534c99e1acf63a1386fefc51b15994a7860aab0 | `engine_facts` also reads `url.password` | `AssertionError: assert ['password'] == []` |
| tests/engine/collectors/database_advisor/test_rules_driver_pool.py::test_query_string_values_are_never_kept | f534c99e1acf63a1386fefc51b15994a7860aab0 | `engine_facts` keeps `key=value` for every query item | `assert 'qs-' not in "('postgresq...3'}), False)"` |
| tests/fastapi/test_database_advisor_api.py::test_inactive_database_advisor_paths_404 | 31bce506ef98a64b0064d099b332356342799075 | `install.py`: the inactive branch (`if not activation.enabled`) never taken | `assert [200, 200, 400] == [404, 404, 404]` |
| tests/fastapi/test_database_advisor_api.py::test_disabled_panel_is_403 | 31bce506ef98a64b0064d099b332356342799075 | `guard.py`: the disabled-panel denial removed | `assert [200, 200] == [403, 403]` |
| tests/test_database_advisor_docs_table.py::test_docs_table_matches_registry | 31bce506ef98a64b0064d099b332356342799075 | registry drops the last driver/pool rule | `assert ['DB-DRIVER-0...OOL-004', ...] == [...]` |
| tests/test_database_advisor_docs_table.py::test_dropped_checks_give_a_reason | 31bce506ef98a64b0064d099b332356342799075 | DB-DRIVER-004's reason blanked in the doc | `assert ['DB-DRIVER-004'] == []` |
| tests/test_database_advisor_docs_table.py::test_docs_titles_match_registry_names | 31bce506ef98a64b0064d099b332356342799075 | DB-SCHEMA-001 renamed in the registry | `assert {...} == {...}` (title differs) |

`tests/fastapi/test_database_advisor_api.py::test_post_scan_golden_parity` skips with `post-scan golden absent (G0)`
(unverified until G0). `tests/fastapi/test_database_advisor_leased.py` skips without `SHARPIT_TEST_POSTGRES_URL` /
`SHARPIT_TEST_MYSQL_URL` (leased; coordinator).

## UI reds (vitest)

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| ui/tests/component/DatabaseAdvisor.test.ts::before the first scan | 3a282ef2634899caf716dfebabf3a01bd073db53 | placeholder view: `expected '...not built yet.' to contain 'Not scanned yet'` | Fixed in 2c5e546 |
| ui/tests/component/DatabaseAdvisor.test.ts::Run Database checks posts | 3a282ef2634899caf716dfebabf3a01bd073db53 | placeholder view: `to contain 'Not scanned yet'` | Fixed in 2c5e546 |
| ui/tests/component/DatabaseAdvisor.test.ts::lists warning diagnostics | 3a282ef2634899caf716dfebabf3a01bd073db53 | placeholder view: `to contain 'A scan bound was reached'` | Fixed in 2c5e546 |
| ui/tests/component/DatabaseAdvisor.test.ts::View violations | 3a282ef2634899caf716dfebabf3a01bd073db53 | placeholder view: `to contain 'DB-SCHEMA-001'` | Fixed in 2c5e546 |

## Every new rule removed → failing test

Each rule's red ran against a skeleton that had no rule at all (`[('', '', '')]` or an empty catalog), so removing a
rule's body returns it to that red: the table above is the record. The allow-list (`URL_KEYS`) and the password
property are pinned by the two mutation rows above.
