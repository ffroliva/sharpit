# Lane A-mysql handoff

Implementer: agy-flavio, Gemini 3.8

## Status

IN_PROGRESS (Task 1: contract first).

## Tasks

| Task | Commit | What it proved |
|---|---|---|

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|

## Decisions

1. MySQL panel follows the PostgreSQL collector template (`src/sharpit/engine/collectors/mysql/`: `limits.py`, `queries.py`, `querytext.py`, `sections.py`, `service.py`).
2. Read-only verification uses F5b's `run_db_read(read_only=True)`: `bounded()` is never used.
3. Every statement-text field (`digest_text`, `PROCESSLIST_INFO`, `events_statements_current.SQL_TEXT`, lock-wait query columns) is normalized, masked, and truncated at 400 chars.
4. Leased tests (`tests/fastapi/test_mysql_leased.py`) require `SHARPIT_TEST_MYSQL_URL` and skip cleanly when unset.
