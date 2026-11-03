# Lane A-mysql findings

Implementer: agy-flavio, Gemini 3.8

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/fastapi/test_mysql_api.py::test_report_golden_parity | 0637bf5965d2f0ae18a081749f338829413b771b | `mysql/captured.json parity: localOnly: missing from payload; ...` | Fixed in 465813a6b62ae251535f3a3419be79713d5e571a |
| tests/engine/collectors/mysql/test_sections.py::test_statement_text_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.statements) == 1`: 0 statements returned | Fixed in eb696f8f522d15940e6d0bb7c082456470c29a09 |
| tests/engine/collectors/mysql/test_sections.py::test_session_current_statement_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.sessions) == 1`: 0 sessions returned | Fixed in eb696f8f522d15940e6d0bb7c082456470c29a09 |
| tests/engine/collectors/mysql/test_sections.py::test_row_limits_truncate_and_flag | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert section["rowCount"] == 2`: was 0 | Fixed in eb696f8f522d15940e6d0bb7c082456470c29a09 |
| tests/engine/collectors/mysql/test_sections.py::test_mariadb_capabilities_differ | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert maria_data.capabilities["isMariaDb"] is True`: was False | Fixed in eb696f8f522d15940e6d0bb7c082456470c29a09 |
| tests/engine/collectors/mysql/test_sections.py::test_performance_schema_off_is_a_diagnostic | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.diagnostics) >= 1`: no diagnostics returned | Fixed in eb696f8f522d15940e6d0bb7c082456470c29a09 |
| tests/engine/collectors/mysql/test_sections.py::test_changes_between_reads | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(second_changes) == 1`: 0 changes returned | Fixed in eb696f8f522d15940e6d0bb7c082456470c29a09 |
| tests/fastapi/test_mysql_api.py::test_mysql_read_uses_verified_read_only_path | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |
| tests/fastapi/test_mysql_api.py::test_autocommit_engine_is_unavailable | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |
| tests/fastapi/test_mysql_api.py::test_unknown_driver_unavailable | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |
| tests/fastapi/test_mysql_api.py::test_read_only_blocks_read | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |
| tests/fastapi/test_mysql_api.py::test_inactive_mysql_paths_404 | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |
| tests/fastapi/test_mysql_api.py::test_mcp_tools_list_has_only_get | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert [] == ['get_mysql_report', 'mysql_read']` | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |
| tests/masking/test_a_mysql_masking.py::test_driver_error_dsn_password_masked | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 'could not connect to mysql' in shown` | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |
| tests/safety/test_a_mysql_safety.py::test_mysql_get_no_side_effects | fcecb89547d7c66dc8b0933580e608070b471cb7 | `assert 404 == 200` (route not mounted) | Fixed in 06806ab8ee43ec751cebe9a0ca8c5d26394beff5 |

## UI reds (vitest)

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| ui/tests/component/MySql.test.ts > NOT_READ shows the message and the read button, and nothing reads on open | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected 'mysqlThis panel\'s view is not built …' to contain 'No MySQL read has run. Run MySQL read…'` | Fixed in e9f89645467c6f7d72a991b8724705ac935d0220 |
| ui/tests/component/MySql.test.ts > a read renders each section with its status, reason and hint | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected undefined to be defined` | Fixed in e9f89645467c6f7d72a991b8724705ac935d0220 |
| ui/tests/component/MySql.test.ts > changes render only when the read carries them (the second read) | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected 'mysqlThis panel\'s view is not built …' to contain 'Top normalized statements'` | Fixed in e9f89645467c6f7d72a991b8724705ac935d0220 |
| ui/tests/component/MySql.test.ts > read-only hides the read button and says why | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected 'mysqlThis panel\'s view is not built …' to contain 'No MySQL read has run. Run MySQL read…'` | Fixed in e9f89645467c6f7d72a991b8724705ac935d0220 |
| ui/tests/component/MySql.test.ts > renders the section rows and limitations from the POST answer without a second GET | e40506d3b8d5e6ad92ad5f9166c83b6b5e58e1e3 | `expected undefined to be defined` | Fixed in e9f89645467c6f7d72a991b8724705ac935d0220 |

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|

## Rule mutations (each new rule removed in place, the named test run, the file restored with git checkout)

| Rule | File | Mutation | Failing test |
|---|---|---|---|
