# G3 findings

| Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| `tests/test_report_summary.py::test_summary_golden` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | stub rendered empty text, not the golden | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_has_status_mode_totals` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | status line missing | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_includes_baseline_counts_when_present` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | baseline golden not rendered | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_escapes_markdown_values` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | pipe not escaped | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_limits_findings_to_top_20_and_reports_totals` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | no rows rendered (0 != 20) | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_renders_unknown_reasons_even_when_status_is_fail` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | unknown reason not rendered | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_cli_invalid_json_returns_error` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | invalid JSON exited 0 | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_cli_missing_file_returns_error` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | missing file exited 0 | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/test_report_summary.py::test_summary_cli_runs_as_module` | `8bd33f7184e715062f1b387bef908ec5af65c9dd` | module run printed nothing | Fixed in cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6 |
| `tests/action/test_action_definition.py::test_action_declares_all_inputs_and_defaults` | `c3ba9201e065905f613b80608dae5965af0c756f` | only `runner` declared | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_version_is_literal` | `c3ba9201e065905f613b80608dae5965af0c756f` | no literal pin (0 != 1) | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_respects_install_none` | `c3ba9201e065905f613b80608dae5965af0c756f` | bad install value exited 0 | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_runner_default` | `c3ba9201e065905f613b80608dae5965af0c756f` | default was `pytest` | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_invokes_summary_cli` | `c3ba9201e065905f613b80608dae5965af0c756f` | summary command missing | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_pytest_args_are_shlex_split_not_shell_evaluated` | `c3ba9201e065905f613b80608dae5965af0c756f` | argv empty | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_has_no_expressions_inside_run_and_all_inputs_use_env` | `c3ba9201e065905f613b80608dae5965af0c756f` | expression inside run | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_quotes_every_expansion` | `c3ba9201e065905f613b80608dae5965af0c756f` | unquoted expansion | Fixed in 912b1fc |
| `tests/action/test_action_definition.py::test_action_has_no_unquoted_or_expression_run_values` | `c3ba9201e065905f613b80608dae5965af0c756f` | expression inside run | Fixed in 912b1fc |

## Review round 1 (coordinator fix, 06:05)

| Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|

## Review round 2 (fix round, 06:10)

| Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/test_report_summary.py::test_summary_cli_writes_utf8_regardless_of_console_code_page | 009194c4ca2625d21cb0f0671a19a0d0f5772778 | message missing from stdout (UnicodeEncodeError traceback) | Fixed in 0abf952f8795bf13048498377f0665e1f1b2a45b |
| tests/test_report_summary.py::test_summary_cli_deeply_nested_json_fails_cleanly | 009194c4ca2625d21cb0f0671a19a0d0f5772778 | stderr does not start with "sharpit.report: " (RecursionError traceback) | Fixed in 0abf952f8795bf13048498377f0665e1f1b2a45b |
| tests/test_report_summary.py::test_summary_unknown_status_prints_each_reason_once | 66fd75cd5563f5822414a24ad2fff51cb267cbdf | assert 2 == 1 | Fixed in 2e559564bc91c974a94b5cca77d4a81d107a4ca9 |
| tests/test_report_summary.py::test_summary_excludes_dismissed_findings_from_count_and_table | 66fd75cd5563f5822414a24ad2fff51cb267cbdf | '- **Findings:** 1' not in output | Fixed in 2e559564bc91c974a94b5cca77d4a81d107a4ca9 |
| tests/test_report_summary.py::test_summary_orders_failing_findings_before_severity | 66fd75cd5563f5822414a24ad2fff51cb267cbdf | assert 284 < 239 | Fixed in 2e559564bc91c974a94b5cca77d4a81d107a4ca9 |
| tests/test_report_summary.py::test_summary_escapes_baseline_fixed | 66fd75cd5563f5822414a24ad2fff51cb267cbdf | 'fixed \<b\>x\</b\>' not in output | Fixed in 2e559564bc91c974a94b5cca77d4a81d107a4ca9 |
| tests/test_report_summary.py::test_summary_neutralises_bare_urls | 66fd75cd5563f5822414a24ad2fff51cb267cbdf | bare URLs not broken with U+200B | Fixed in 2e559564bc91c974a94b5cca77d4a81d107a4ca9 |
| tests/action/test_action_definition.py::test_action_forwards_report_only_baseline_fail_on_and_report_path | eb39bf939a058f8b72ce3fc0515fb2be4e6354b0 | argv lacks -o sharpit_report_only=false | Fixed in 3f013d9b9de9ee59fa423ce73309f711762c402e |
| tests/action/test_action_definition.py::test_action_removes_stale_report_before_pytest | eb39bf939a058f8b72ce3fc0515fb2be4e6354b0 | 'rm -f "$REPORT_PATH"' not in run | Fixed in 3f013d9b9de9ee59fa423ce73309f711762c402e |
| tests/action/test_action_definition.py::test_action_rejects_invalid_report_only | 8d163103367fab0acc52797c5067a66d71ef9ca8 | assert 0 == 1 (first red in eb39bf939a058f8b72ce3fc0515fb2be4e6354b0 was a JSON decode crash; rewritten) | Fixed in 3f013d9b9de9ee59fa423ce73309f711762c402e |

## Superseded reds (coordinator, 06:55)

| Test id | Historical SHA | Reason |
|---|---|---|
| `tests/action/test_action_definition.py::test_action_forwards_report_only_baseline_fail_on_and_report_path` | `c3ba9201e065905f613b80608dae5965af0c756f` | test body changed after this red commit (fix round 06:10); test kept, see the newer row or the fix |
| tests/test_report_summary.py::test_backslash_in_finding_text_is_escaped_too | 32aaa692c95444caab40e70cf7c7c067d7551ac7 | test body changed after this red commit (fix round 06:10); test kept, see the newer row or the fix |
