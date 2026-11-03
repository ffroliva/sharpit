# Lane A-mysql findings

Implementer: agy-flavio, Gemini 3.8

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/fastapi/test_mysql_api.py::test_report_golden_parity | 0637bf5965d2f0ae18a081749f338829413b771b | `mysql/captured.json parity: localOnly: missing from payload; ...` | Fixed in 465813a6b62ae251535f3a3419be79713d5e571a |
| tests/engine/collectors/mysql/test_sections.py::test_statement_text_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.statements) == 1`: 0 statements returned | Fixed in next commit |
| tests/engine/collectors/mysql/test_sections.py::test_session_current_statement_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.sessions) == 1`: 0 sessions returned | Fixed in next commit |
| tests/engine/collectors/mysql/test_sections.py::test_row_limits_truncate_and_flag | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert section["rowCount"] == 2`: was 0 | Fixed in next commit |
| tests/engine/collectors/mysql/test_sections.py::test_mariadb_capabilities_differ | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert maria_data.capabilities["isMariaDb"] is True`: was False | Fixed in next commit |
| tests/engine/collectors/mysql/test_sections.py::test_performance_schema_off_is_a_diagnostic | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.diagnostics) >= 1`: no diagnostics returned | Fixed in next commit |
| tests/engine/collectors/mysql/test_sections.py::test_changes_between_reads | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(second_changes) == 1`: 0 changes returned | Fixed in next commit |

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|

## Rule mutations (each new rule removed in place, the named test run, the file restored with git checkout)

| Rule | File | Mutation | Failing test |
|---|---|---|---|
