# Lane A-mysql handoff

Implementer: agy-flavio, Gemini 3.8

## Status

IN_PROGRESS (Task 1 done, moving to Task 2).

## Tasks

| Task | Commit | What it proved |
|---|---|---|
| 1 red | `0637bf5965d2f0ae18a081749f338829413b771b` (`test:`) | `test_report_golden_parity` failed cleanly on empty skeleton report with AssertionError under tests/ |
| 1 fix | pending (`feat:`) | `mysql_report` returns complete `NOT_READ` report matching `tests/fixtures/bootui/2.2.0/mysql/captured.json` |

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| tests/fastapi/test_mysql_api.py::test_report_golden_parity | 0637bf5965d2f0ae18a081749f338829413b771b | `mysql/captured.json parity: localOnly: missing from payload; ...` |

## Decisions

1. MySQL panel follows the PostgreSQL collector template (`src/sharpit/engine/collectors/mysql/`: `limits.py`, `queries.py`, `querytext.py`, `sections.py`, `service.py`).
2. Read-only verification uses F5b's `run_db_read(read_only=True)`: `bounded()` is never used.
3. Every statement-text field (`digest_text`, `PROCESSLIST_INFO`, `events_statements_current.SQL_TEXT`, lock-wait query columns) is normalized, masked, and truncated at 400 chars.
4. Leased tests (`tests/fastapi/test_mysql_leased.py`) require `SHARPIT_TEST_MYSQL_URL` and skip cleanly when unset.
