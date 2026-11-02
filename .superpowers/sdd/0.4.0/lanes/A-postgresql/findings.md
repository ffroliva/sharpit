# Lane A-postgresql findings and red-test log

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

## Review / implementation findings

| Finding | Test | Status |
|---|---|---|
| WIP `f247d7e` `query_text` called non-existent `Masker.mask_value` (AttributeError on every call) | `tests/engine/postgresql/test_querytext.py::*` (red at `afbecc2`, errored at `f247d7e`) | fixed in Task 2 fix commit |
| WIP dollar-quote regex ran before the string regex, so a `$tag$` inside a string literal could swallow text across literal boundaries | `tests/engine/postgresql/test_querytext.py::test_query_text_masks_single_quoted_escape_and_dollar_quoted_literals` | fixed: single-pass alternation |
