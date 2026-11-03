# T-swallowed-2 findings

## Reds

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| A broad handler that hands the caught exception to a helper (`self._report(e)`) was reported as a swallow (false positive) | tests/engine/testsession/test_swallowed.py::test_helper_that_logs_is_not_a_swallow | 0dc5568ac00edbee3794dc1ffe68d157101a909b | `AssertionError: assert True is False` (handler_swallows on the `except Exception as e:` line) | Fixed in 93c22a3b4a72703f1758b20a7c8e3032a4666aa5 |
| A log-named method on a non-logger (`response.error("x")`) counted as logging, hiding the swallow (false negative) | tests/engine/testsession/test_swallowed.py::test_non_logger_error_call_is_not_logging | 0dc5568ac00edbee3794dc1ffe68d157101a909b | `AssertionError: assert False is True` (handler_swallows on the `except Exception:` line) | Fixed in 9503c401b309ea5ba1fe7f5a2f074aa71518ebd1 |
| Review fix 1 (major): any call receiving the caught name counted as handling, so `errors.append(e); return 200` hid a swallow | tests/engine/testsession/test_swallowed.py::test_appending_the_error_is_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | `AssertionError: assert False is True` | Fixed in bef2d10f8d6cbf84f97af9fb72c2ab6467a0cc85 |
| Review fix 1: `str(e)`, `repr(e)`, `print(e)`, `isinstance(e, X)`, `json.dumps({"err": str(e)})`, `setattr(obj, "err", e)` hid a swallow (6 params, all red) | tests/engine/testsession/test_swallowed.py::test_builtin_use_of_the_error_is_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | `AssertionError: assert False is True` | Fixed in bef2d10f8d6cbf84f97af9fb72c2ab6467a0cc85 |
| Review fix 1: `self._report(e)` whose same-module `_report` only stores hid a swallow | tests/engine/testsession/test_swallowed.py::test_method_that_only_stores_is_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | `AssertionError: assert False is True` | Fixed in bef2d10f8d6cbf84f97af9fb72c2ab6467a0cc85 |
| Review fix 1: error-tracker capture without the name (`sentry_sdk.capture_exception()`, `rollbar.report_exc_info()`, `capture_exception()`) reported as a swallow (3 params, all red) | tests/engine/testsession/test_swallowed.py::test_error_tracker_capture_is_not_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | `AssertionError: assert True is False` | Fixed in bef2d10f8d6cbf84f97af9fb72c2ab6467a0cc85 |
| Review fix 1: returning an HTTP error response (`status_code=500`, `status.HTTP_503_...`) reported as a swallow (2 params, all red) | tests/engine/testsession/test_swallowed.py::test_returning_an_http_error_response_is_not_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | `AssertionError: assert True is False` | Fixed in bef2d10f8d6cbf84f97af9fb72c2ab6467a0cc85 |

Both reds replayed at `0dc5568` in a detached worktree with `PYTHONPATH=<tree>/src`: `2 failed`, each an
AssertionError in `tests/engine/testsession/test_swallowed.py`. `red_check.py`: both `RED (assertion under tests/)`.

Fix-1 reds: `red_check.py` RED (assertion under tests/) for all five at `84f4d78`; replayed at `84f4d78` in a detached
worktree with `PYTHONPATH=<tree>/src`: `13 failed, 21 deselected`, each an AssertionError under `tests/`.

## Pins (passed first time; behaviour 0.4.0 already had)

### Historical SHA

| Test | Historical SHA | Reason |
|---|---|---|
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_library_warn_does_not_hide_app_swallow | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin (U19). Mutation at head `9503c40`: `_silent` returns False at its end -> fails `targets == ['twinapp.py:17']` (empty list) |
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_swallow_in_loop_is_one_finding | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin (U17). 200 iterations -> 1 finding. Mutation: `record` keeps duplicates AND `outcome.py` de-duplication keyed by position (lines 130, 161) -> `Left contains 199 more items` (200 findings). Removing only `record`'s dedup survives: the report de-duplicates by fingerprint too |
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_db_error_swallow_found | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin (U2 / D13 twin, `sqlite3.OperationalError`, INFO). Mutation: `_silent` returns False -> fails on empty targets |
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_logged_handler_is_not_a_finding | 5ba446c00c95aa7ef379f6db48f00ce4e36acb2f | Pin. Mutation: `"exception"` removed from `_LOG_CALLS` -> the twin test fails and a finding appears |
| tests/engine/testsession/test_swallowed.py::test_logger_receivers_still_count_as_logging | 9503c401b309ea5ba1fe7f5a2f074aa71518ebd1 | Guard for fix 2 (passes before it too). Mutation: `_module_loggers` returns `frozenset()` -> fails "module logger" |
| tests/engine/testsession/test_swallowed.py::test_helper_that_logs_in_this_module_is_not_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | Pin (helper resolution). Mutation at `bef2d10`: `_hands_on` returns False for a defined name -> fails (assert True is False) |
| tests/engine/testsession/test_swallowed.py::test_method_that_logs_in_this_module_is_not_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | Pin. Same mutation -> fails |
| tests/engine/testsession/test_swallowed.py::test_error_tracker_capture_of_the_error_is_not_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | Pin (`bugsnag.notify(e)` passed before through the any-call rule). Mutation: drop `_TRACKERS` -> fails |
| tests/engine/testsession/test_swallowed.py::test_returning_a_success_response_is_a_swallow | 84f4d789c6438294c524a713d063870c82b8fdea | Pin (status 200 stays a swallow). Mutation: `>= 400` -> `>= 0` -> fails |
| tests/engine/testsession/test_swallowed.py::test_dynamic_target_is_not_reported | 84f4d789c6438294c524a713d063870c82b8fdea | Pin (0.4.0 fail-safe, `getattr(self, name)(e)`). Mutation: dynamic target returns False -> fails |
| tests/engine/testsession/test_swallowed.py::test_imported_function_is_not_reported | 84f4d789c6438294c524a713d063870c82b8fdea | Pin (fail-safe, imported `report(e)`). Mutation: unknown Name returns False -> fails |
