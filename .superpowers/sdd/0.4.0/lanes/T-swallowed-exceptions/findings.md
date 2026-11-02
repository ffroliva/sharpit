# T-swallowed-exceptions findings

Implementer: claude-flavio opus

Each red was replayed at its red SHA from a `git archive` export (PYTHONPATH on the export's `src`) with
`--junitxml`; every row below failed with an AssertionError raised in the test file (the budget row: in the shared
helper `tests/overhead.py::check_budget`).

## Red tests

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| F1 spike T4: AttributeError swallowed by `except Exception: return 0` passes silently | `tests/pytest_plugin/test_plugin_swallowed.py::test_spike_f1_swallowed_attribute_error_fails` | 29058b1b7e1a52f78172b3e4476512107fcdcb5d | `AssertionError: no sharpit.swallowed-exception finding for the planted handler: ['RAPI-DTO-002', ...]` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| broad/bare clauses not detected | `tests/engine/testsession/test_swallowed.py::test_detects_bare_and_broad_catches` | eb89f13f6acb1c2b273d988e886fab67ebeb0e67 | `AssertionError: assert False is True` | Fixed in c9a4307dcf8f847dea9b991a274ec8b1559ef358 |
| programming-error classification missing | `tests/engine/testsession/test_swallowed.py::test_programming_error_types` | eb89f13f6acb1c2b273d988e886fab67ebeb0e67 | `AssertionError: assert False is True (is_programming_error(AttributeError('x')))` | Fixed in c9a4307dcf8f847dea9b991a274ec8b1559ef358 |
| static FASTAPI-ERR-001 does not flag a swallowing module | `tests/engine/restapi/test_swallowed_rule.py::test_fastapi_err_rule_flags_swallowed_broad_handler` | eb89f13f6acb1c2b273d988e886fab67ebeb0e67 | `AssertionError: assert [] == ['swallow_routes_flagged:4']` | Fixed in c9a4307dcf8f847dea9b991a274ec8b1559ef358 |
| narrow catch reported as swallowing | `tests/engine/testsession/test_swallowed.py::test_ignores_narrow_catch` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert True is False` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| re-raising clause reported as swallowing | `tests/engine/testsession/test_swallowed.py::test_ignores_reraise` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert True is False` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| logging/warnings clause reported as swallowing | `tests/engine/testsession/test_swallowed.py::test_ignores_logger_and_warnings_calls` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert True is False` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| nested handler judged by the wrong location | `tests/engine/testsession/test_swallowed.py::test_nested_handler_uses_handled_location` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert True is False` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| a narrow clause that handled the exception is ignored in favour of a later broad one | `tests/engine/testsession/test_swallowed.py::test_first_matching_clause_decides` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert True is False` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| an unresolvable user exception clause produces a finding | `tests/engine/testsession/test_swallowed.py::test_unresolvable_clause_is_never_flagged` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert True is False` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| cleanup blocks (COPY/POP_EXCEPT/RERAISE) treated as handlers | `tests/engine/testsession/test_swallowed.py::test_cleanup_offset_is_not_a_handler` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert [True, True] == [False, False]` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| source parsed per event instead of once per code object | `tests/engine/testsession/test_swallowed.py::test_ast_cache_is_per_code_object` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert 0 == 1` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| static rule flags a logged broad handler | `tests/engine/restapi/test_swallowed_rule.py::test_fastapi_err_rule_ignores_logged_handler` | d759f74222225b919b441de595d56f999c3932cd | `AssertionError: assert [Violation(ta...es nor logs')] == []` | Fixed in 679eef0f295e97a5c4be931b1f44e074fd02b3c6 |
| library raise handled in app code not recorded correctly | `tests/pytest_plugin/test_plugin_swallowed.py::test_library_raise_app_handler_is_seen` | 8660ea5a238dec3173f153d384a417cedf7b651c | `AssertionError: assert [(('', 0, 'ca...=False)), ...] == [(('tests/tes...error=False))]` | Fixed in 19353b5ee15d2d405fb248026847b7f88d142b1b |
| library handlers recorded | `tests/pytest_plugin/test_plugin_swallowed.py::test_library_handler_is_ignored` | 8660ea5a238dec3173f153d384a417cedf7b651c | `AssertionError: assert [(('', 0, 'ca...=False)), ...] == []` | Fixed in 19353b5ee15d2d405fb248026847b7f88d142b1b |
| events outside a test recorded | `tests/pytest_plugin/test_plugin_swallowed.py::test_event_outside_a_test_is_ignored` | 8660ea5a238dec3173f153d384a417cedf7b651c | `AssertionError: assert [(('', 0, 'ca...=False)), ...] == []` | Fixed in 19353b5ee15d2d405fb248026847b7f88d142b1b |
| ids 3 and 4 taken still reports attached | `tests/pytest_plugin/test_plugin_swallowed.py::test_tool_id_conflict_reports_unattached` | 8660ea5a238dec3173f153d384a417cedf7b651c | `AssertionError: assert True is False` | Fixed in 19353b5ee15d2d405fb248026847b7f88d142b1b |
| RAISE subscribed besides EXCEPTION_HANDLED | `tests/pytest_plugin/test_plugin_swallowed.py::test_raise_is_not_subscribed` | 8660ea5a238dec3173f153d384a417cedf7b651c | `AssertionError: assert 3072 == 2048` | Fixed in 19353b5ee15d2d405fb248026847b7f88d142b1b |
| swallowed AttributeError produces no failing finding | `tests/engine/testsession/test_gates.py::test_swallowed_attribute_error_fails_test_by_default` | 29716480fc7c3e62345bc2a0d47bd592f0797fe0 | `AssertionError: assert 0 == 1` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| non-programming-error swallow is not a note (canonical Review Focus 8) | `tests/engine/testsession/test_gates.py::test_non_programming_error_swallow_is_a_note` | 29716480fc7c3e62345bc2a0d47bd592f0797fe0 | `AssertionError: assert 0 == 1` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| marker allow_swallowed ignored | `tests/engine/testsession/test_gates.py::test_allow_swallowed_marker` | 29716480fc7c3e62345bc2a0d47bd592f0797fe0 | `AssertionError: assert False is True` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| message names something other than handler and type | `tests/engine/testsession/test_gates.py::test_swallowed_message_names_handler_and_type_only` | 29716480fc7c3e62345bc2a0d47bd592f0797fe0 | `AssertionError: assert [] == ['AttributeEr... nor logged)']` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| bare except swallowing a NameError does not fail the test | `tests/pytest_plugin/test_plugin_swallowed.py::test_bare_exception_handler_gates` | 29716480fc7c3e62345bc2a0d47bd592f0797fe0 | `AssertionError: assert 'passed' == 'failed'` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| allow_swallowed does not leave a note | `tests/pytest_plugin/test_plugin_swallowed.py::test_allow_swallowed_marker_keeps_the_test_passing` | 29716480fc7c3e62345bc2a0d47bd592f0797fe0 | `AssertionError: assert [] == ['INFO']` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| report-only/baseline do not apply to the finding | `tests/pytest_plugin/test_plugin_swallowed.py::test_swallowed_respects_report_only_and_baseline` | 29716480fc7c3e62345bc2a0d47bd592f0797fe0 | `AssertionError: assert [] == ['sharpit.swa...ed-exception']` | Fixed in c6c549347dfb1348c9aeed74530ff9f901b52639 |
| monitoring callback costs ~6 us per handled exception (relpath per event) | `tests/engine/test_swallowed_overhead.py::test_swallowed_monitoring_overhead_budget` | 025956260890a0c96e0ef8b6273e79dfae8b1f71 | `AssertionError: swallowed-exception monitoring: overhead 6.750 us/exception ...; budget 1.500 us/exception` | Fixed in 2e40aef0ed2910fcdf3a6f792bb8654eda6d568b |
| fix1 review #1 (major): a `raise`/logger call inside an unexecuted nested def, async def, lambda or class method hides a real swallow | `tests/engine/testsession/test_swallowed.py::test_ignores_unexecuted_nested_raise_and_logger` | e6ec74d5f882f40cb6fa37ad19cb6169cc1a12fa | `AssertionError: nested def raise` / `assert False is True` | Fixed in 85eb0a34a7d176502aba1c5b3370a4bf3cd5300c |
| fix1 review #2 (minor): `register_callback` or `set_events` failing after `use_tool_id` leaves the tool id claimed | `tests/pytest_plugin/test_plugin_swallowed.py::test_partial_attach_failure_releases_tool_id_and_callback` | e6ec74d5f882f40cb6fa37ad19cb6169cc1a12fa | `AssertionError: tool id still claimed` / `assert ['sharpit', None] == [None, None]` (both params) | Fixed in 85eb0a34a7d176502aba1c5b3370a4bf3cd5300c |
| fix2 review #1 (major): round 1 skipped every nested scope, so a handler that calls a nested helper which raises or logs (or awaits an async one, or calls a bound/inline lambda) was reported as swallowing; an uncalled helper must stay skipped | `tests/engine/testsession/test_swallowed.py::test_called_nested_scopes_are_followed` | 15e30a35a12381ff24f7cd73310d8e744c4b8672 | `E       AssertionError: called helper raises` (replayed at its SHA in detached `C:/t/sw-red2`, `PYTHONPATH=C:/t/sw-red2/src`; module loaded from `C:/t/sw-red2/src`; worktree removed) | Fixed in 97509bfde92b6a816e64139a430acb18d10f52d4 |

## Budget mutation proof

With the fix in place, a temporary 5 us busy-wait at the top of `MonitoringCapture._handled` made the budget test
fail: `AssertionError: swallowed-exception monitoring: overhead 5.998 us/exception, noise 0.234 us/exception; ...;
budget 1.500 us/exception`. The busy-wait was removed before any commit.

## Historical SHA (superseded reds)

| Test | Historical SHA | Reason |
|---|---|---|
| `tests/pytest_plugin/test_plugin_swallowed.py::test_monitoring_tool_freed_at_session_end` | 8660ea5a238dec3173f153d384a417cedf7b651c | removed: red at its SHA (`AssertionError: assert ['sharpit', None] == [None, None]`), but its pytester probe module `test_tools` collided with `tests/engine/test_tools.py` in an xdist worker (import file mismatch, full suite). Superseded by `test_monitoring_tool_freed_after_the_session` (unique probe module), mutation-proven: the HEAD test file run against the `src/` of 8660ea5 (stub `detach_session`) fails with `AssertionError: assert ['sharpit', None] == [None, None]`; green at head. |
