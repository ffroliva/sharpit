# Lane A-postgresql handoff

Status: IN_PROGRESS — Tasks 1–2 complete (resumed by a Claude subagent after Antigravity hit its quota); next Task 3.

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

## Next step

- Task 3: section collectors (`queries.py`, `sections.py`, `tests/engine/postgresql/test_sections.py`).

## Decisions and deviations

- Following coordinator ruling (00:15): branch starts at `d37c6f2` (`lane/0.4.0-F`); no merge/rebase; `lane_gate.py` not run in worktree; leased-Postgres tests skip when `SHARPIT_TEST_POSTGRES_URL` is unset.
- `run_db_read` unwraps `getattr(engine, "sync_engine", engine)` and reuses an `AsyncEngine` instance directly if one is passed, so both `EngineRegistry`'s `sync_engine` entries and direct `create_async_engine(...)` calls work seamlessly.

- Task 2 `query_text` does NOT go through `normalize_sql` (plan Global Constraints): the BootUI-ported red tests require `'******'` / `$$******$$` literal masks and the raw text under `FULL`, while `normalize_sql` rewrites literals to `?`. Literal masking runs in one regex pass (whichever literal starts first wins; unterminated literals run to the end, as `pg_stat_activity` truncates mid-literal), then `masker.mask_text`, then whitespace collapse and the 400-char cut. Literals are masked exactly when the masker masks a secret value (`masker.mask("password", "x")[1]`), i.e. not under `FULL` or with secret masking off; `METADATA_ONLY` returns `******`.
- Task 2 red test names cite BootUI methods that differ from the plan's list (the red bodies are frozen); `rowsDistinguishEmptyAvailableFromFailedAndCopyRows`, `listQueriesReadOnePastTheBoundAndReportTruncation`, `exactlyTheRowLimitIsNotReportedAsTruncated` are covered by `read_one_past` asserts here and by Task 3/4 section tests.
- Task 1 `bounded_read_only` refuses a non-PostgreSQL dialect with `READ_ONLY_REFUSED` rather than the plan's `Read-only reads are not supported for <dialect>`; both fail closed, and the service (Task 4) skips non-PostgreSQL engines before any read.

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
