# T-swallowed-2 findings

## Reds

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| A broad handler that hands the caught exception to a helper (`self._report(e)`) was reported as a swallow (false positive) | tests/engine/testsession/test_swallowed.py::test_helper_that_logs_is_not_a_swallow | 0dc5568ac00edbee3794dc1ffe68d157101a909b | `AssertionError: assert True is False` (handler_swallows on the `except Exception as e:` line) | Fixed in 93c22a3b4a72703f1758b20a7c8e3032a4666aa5 |
| A log-named method on a non-logger (`response.error("x")`) counted as logging, hiding the swallow (false negative) | tests/engine/testsession/test_swallowed.py::test_non_logger_error_call_is_not_logging | 0dc5568ac00edbee3794dc1ffe68d157101a909b | `AssertionError: assert False is True` (handler_swallows on the `except Exception:` line) | Fixed in 9503c401b309ea5ba1fe7f5a2f074aa71518ebd1 |

Both reds replayed at `0dc5568` in a detached worktree with `PYTHONPATH=<tree>/src`: `2 failed`, each an
AssertionError in `tests/engine/testsession/test_swallowed.py`. `red_check.py`: both `RED (assertion under tests/)`.

## Pins (passed first time; behaviour 0.4.0 already had)

### Historical SHA

| Test | Historical SHA | Reason |
|---|---|---|
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_library_warn_does_not_hide_app_swallow | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin (U19). Mutation at head `9503c40`: `_silent` returns False at its end -> fails `targets == ['twinapp.py:17']` (empty list) |
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_swallow_in_loop_is_one_finding | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin (U17). 200 iterations -> 1 finding. Mutation: `record` keeps duplicates AND `outcome.py` de-duplication keyed by position (lines 130, 161) -> `Left contains 199 more items` (200 findings). Removing only `record`'s dedup survives: the report de-duplicates by fingerprint too |
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_db_error_swallow_found | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin (U2 / D13 twin, `sqlite3.OperationalError`, INFO). Mutation: `_silent` returns False -> fails on empty targets |
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_logged_handler_is_not_a_finding | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin. Mutation: `"exception"` removed from `_LOG_CALLS` -> the twin test fails and a finding appears |
| tests/engine/testsession/test_swallowed.py::test_logger_receivers_still_count_as_logging | 9503c401b309ea5ba1fe7f5a2f074aa71518ebd1 | Guard for fix 2 (passes before it too). Mutation: `_module_loggers` returns `frozenset()` -> fails "module logger" |
