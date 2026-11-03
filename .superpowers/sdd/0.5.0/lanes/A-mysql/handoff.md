# Lane A-mysql handoff

Implementer: agy-flavio, Gemini 3.8

## Status

IN_PROGRESS (Task 2 sections implemented and tested, moving to commit).

## Tasks

| Task | Commit | What it proved |
|---|---|---|
| 1 red | `0637bf5965d2f0ae18a081749f338829413b771b` (`test:`) | `test_report_golden_parity` failed cleanly on empty skeleton report with AssertionError under tests/ |
| 1 fix | `465813a6b62ae251535f3a3419be79713d5e571a` (`feat:`) | `mysql_report` returns complete `NOT_READ` report matching `tests/fixtures/bootui/2.2.0/mysql/captured.json` |
| 2 red | `9106ba29db4557e7f67d89289d2f171e030440b0` (`test:`) | 6 section/collector tests failed cleanly with AssertionErrors under tests/ |
| 2 fix | pending (`feat:`) | MySQL capability probe, sessions, statements, indexes, tables, lock-waits, replication, settings, metrics, and changes |

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| tests/fastapi/test_mysql_api.py::test_report_golden_parity | 0637bf5965d2f0ae18a081749f338829413b771b | `mysql/captured.json parity: localOnly: missing from payload; ...` |
| tests/engine/collectors/mysql/test_sections.py::test_statement_text_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.statements) == 1`: 0 statements returned |
| tests/engine/collectors/mysql/test_sections.py::test_session_current_statement_masked | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.sessions) == 1`: 0 sessions returned |
| tests/engine/collectors/mysql/test_sections.py::test_row_limits_truncate_and_flag | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert section["rowCount"] == 2`: was 0 |
| tests/engine/collectors/mysql/test_sections.py::test_mariadb_capabilities_differ | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert maria_data.capabilities["isMariaDb"] is True`: was False |
| tests/engine/collectors/mysql/test_sections.py::test_performance_schema_off_is_a_diagnostic | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(data.diagnostics) >= 1`: no diagnostics returned |
| tests/engine/collectors/mysql/test_sections.py::test_changes_between_reads | 9106ba29db4557e7f67d89289d2f171e030440b0 | `assert len(second_changes) == 1`: 0 changes returned |

## Decisions

1. MySQL panel follows the PostgreSQL collector template (`src/sharpit/engine/collectors/mysql/`: `limits.py`, `queries.py`, `querytext.py`, `sections.py`, `service.py`).
2. Read-only verification uses F5b's `run_db_read(read_only=True)`: `bounded()` is never used.
3. Every statement-text field (`digest_text`, `PROCESSLIST_INFO`, `events_statements_current.SQL_TEXT`, lock-wait query columns) is normalized, masked, and truncated at 400 chars.
4. Leased tests (`tests/fastapi/test_mysql_leased.py`) require `SHARPIT_TEST_MYSQL_URL` and skip cleanly when unset.
