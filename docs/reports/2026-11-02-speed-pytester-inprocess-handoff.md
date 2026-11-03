# Pytester in-process speed handoff

## Scope and cause

- Base: `release/0.4.0` at `52060f1b756a1de232792609b6bde29a5e7a20ab`; lane branch `fix/0.4.0-speed-pytester-inprocess`.
- The supplied `docs/reports/2026-11-02-test-speed-research.md` is absent from this worktree. This follows its described technique 3: remove interpreter startups where the test does not assert process behavior.
- Static budget red: `test_pytester_subprocess_calls_stay_within_file_budgets`; it failed on `test_plugin_bad_baseline.py` with `1 subprocess pytest run; budget is 0`. Red commit: `8eaa9d6e459349aae79241306a55eff241674b40`.
- Per-file source-call ceilings: bad baseline 0; baseline 9; gate defaults 9; gates 11; inert 3; report-only 0; reports 1; swallowed 5; terminal 0; xdist 11.
- Final classification: 24 original call sites switched in-process and 49 kept as subprocesses (73 original call sites). `Pytester.runpytest` defaults to in-process in the installed pytest version; the cost test counts explicit `runpytest_subprocess` call sites.

## Classification of every original `runpytest_subprocess` call site

| Original call site | Decision | Per-call reason |
|---|---|---|
| `test_plugin_bad_baseline.py:25` `_run` #1 | Switched in-process | checks malformed/unreadable baseline handling through exit codes and report files; Pytester preserves both in-process. |
| `test_plugin_baseline.py:10` `test_write_baseline_refused_on_partial_xdist_run` #1 | Kept subprocess | real partial xdist worker/controller aggregation is asserted |
| `test_plugin_baseline.py:34` `test_write_baseline_is_only_writer` #1 | Kept subprocess | baseline writing depends on a clean process; unrelated outer tests preload sqlite aliases/drivers and make the inline session unknown |
| `test_plugin_baseline.py:41` `test_write_baseline_is_only_writer` #2 | Kept subprocess | baseline writing depends on a clean process; unrelated outer tests preload sqlite aliases/drivers and make the inline session unknown |
| `test_plugin_baseline.py:43` `test_write_baseline_is_only_writer` #3 | Kept subprocess | baseline writing depends on a clean process; unrelated outer tests preload sqlite aliases/drivers and make the inline session unknown |
| `test_plugin_baseline.py:59` `test_partial_xdist_report_keeps_fixed_null` #1 | Kept subprocess | real partial xdist worker report merging is asserted |
| `test_plugin_baseline.py:85` `test_write_baseline_refuses_unknown_even_when_status_fails` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:109` `test_baseline_loaded_on_every_xdist_worker` #1 | Kept subprocess | loads and writes a baseline on every actual xdist worker |
| `test_plugin_baseline.py:110` `test_baseline_loaded_on_every_xdist_worker` #2 | Kept subprocess | loads and writes a baseline on every actual xdist worker |
| `test_plugin_baseline.py:132` `test_write_baseline_refused_on_single_process_deselection` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:137` `test_write_baseline_refused_on_single_process_marker_addopts` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:148` `test_write_baseline_refused_on_conftest_deselection` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:157` `test_write_baseline_refused_on_single_process_command_line_selection` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:169` `test_single_process_keyword_addopts_keeps_fixed_null` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:177` `test_write_baseline_requires_path` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:186` `test_write_baseline_ini_option_writes_nothing` #1 | Switched in-process | checks baseline selection, fixed-state and usage-error policy; calls requiring a clean baseline state remain subprocesses. |
| `test_plugin_baseline.py:194` `_complete_write` #1 | Kept subprocess | these cases require a complete baseline run; host-loaded aliases make the inline session unknown |
| `test_plugin_baseline.py:218` `test_baseline_write_failure_is_reported_unknown` #1 | Kept subprocess | the test must reach its atomic-write failure; host-import unknown reasons otherwise refuse the write first |
| `test_plugin_gate_defaults.py:24` `test_spike_f3_clean_suite_reaches_green` #1 | Kept subprocess | checks a clean target sys.modules environment before and after injecting a fake asyncpg driver |
| `test_plugin_gate_defaults.py:44` `test_spike_f3_clean_suite_reaches_green` #2 | Kept subprocess | checks a clean target sys.modules environment before and after injecting a fake asyncpg driver |
| `test_plugin_gate_defaults.py:67` `test_autodetect_single_prints_choice` #1 | Kept subprocess | asserts single-app discovery and a passing clean session; host-loaded modules change the result |
| `test_plugin_gate_defaults.py:104` `test_autodetect_ambiguous_uses_none` #1 | Kept subprocess | asserts only the two target apps are discovered in sys.modules |
| `test_plugin_gate_defaults.py:141` `test_autodetect_ambiguous_across_workers_uses_none` #1 | Kept subprocess | requires two distinct xdist worker environments |
| `test_plugin_gate_defaults.py:188` `test_autodetect_never_imports` #1 | Kept subprocess | asserts import-time app discovery in a clean interpreter and that unimported apps stay unimported |
| `test_plugin_gate_defaults.py:207` `test_require_app_no_app_is_unknown` #1 | Switched in-process | checks app autodetection/status/report output; inline runs are used only where host module state is not part of the assertion. |
| `test_plugin_gate_defaults.py:223` `test_require_app_ini_true_is_unknown` #1 | Switched in-process | checks app autodetection/status/report output; inline runs are used only where host module state is not part of the assertion. |
| `test_plugin_gate_defaults.py:252` `test_autodetected_app_without_routes_is_skipped` #1 | Kept subprocess | asserts clean app discovery and pass/require-app outcomes across two runs |
| `test_plugin_gate_defaults.py:254` `test_autodetected_app_without_routes_is_skipped` #2 | Kept subprocess | asserts clean app discovery and pass/require-app outcomes across two runs |
| `test_plugin_gate_defaults.py:285` `test_autodetect_ignores_test_module_apps` #1 | Switched in-process | checks app autodetection/status/report output; inline runs are used only where host module state is not part of the assertion. |
| `test_plugin_gate_defaults.py:315` `test_autodetect_names_app_by_shortest_module_across_workers` #1 | Kept subprocess | requires xdist worker app discovery |
| `test_plugin_gates.py:45` `test_n_plus_one_fails_the_test` #1 | Switched in-process | checks gate/report behavior in generated suites; clean-environment and SQLAlchemy-sensitive cases remain subprocesses. |
| `test_plugin_gates.py:93` `test_spike_f5_message_names_relationship` #1 | Kept subprocess | SQLAlchemy Cython module/cache state breaks when inline runs unload and reload SQLAlchemy |
| `test_plugin_gates.py:119` `test_spike_f5_full_count_1018` #1 | Kept subprocess | SQLAlchemy Cython module/cache state breaks when inline runs unload and reload SQLAlchemy |
| `test_plugin_gates.py:174` `test_async_lazy_load_is_attributed` #1 | Kept subprocess | SQLAlchemy Cython module/cache state breaks when inline runs unload and reload SQLAlchemy |
| `test_plugin_gates.py:221` `test_eager_selectinload_batches_are_not_n_plus_one` #1 | Kept subprocess | SQLAlchemy Cython module/cache state breaks when inline runs unload and reload SQLAlchemy |
| `test_plugin_gates.py:267` `test_eager_selectinload_batches_are_not_n_plus_one_compatible` #1 | Kept subprocess | SQLAlchemy Cython module/cache state breaks when inline runs unload and reload SQLAlchemy |
| `test_plugin_gates.py:283` `test_fail_on_medium_gates_medium_findings` #1 | Switched in-process | checks gate/report behavior in generated suites; clean-environment and SQLAlchemy-sensitive cases remain subprocesses. |
| `test_plugin_gates.py:316` `test_committed_dismissals_are_honoured` #1 | Kept subprocess | asserts that the resulting session passes; unrelated host sqlite aliases can mark it unknown |
| `test_plugin_gates.py:324` `test_committed_dismissals_are_honoured` #2 | Kept subprocess | asserts that the resulting session passes; unrelated host sqlite aliases can mark it unknown |
| `test_plugin_gates.py:395` `test_swallowed_logged_exception_fails` #1 | Switched in-process | checks gate/report behavior in generated suites; clean-environment and SQLAlchemy-sensitive cases remain subprocesses. |
| `test_plugin_gates.py:435` `test_rerun_last_attempt_decides` #1 | Kept subprocess | the final attempt must pass based only on the generated suite, not host modules |
| `test_plugin_gates.py:451` `test_terminal_summary_block_rendered` #1 | Kept subprocess | asserts a passing terminal summary; host-import warnings change its result |
| `test_plugin_gates.py:481` `test_finalizer_logged_exception_is_unattributed` #1 | Switched in-process | checks gate/report behavior in generated suites; clean-environment and SQLAlchemy-sensitive cases remain subprocesses. |
| `test_plugin_gates.py:627` `test_plugin_hook_raises_session_continues` #1 | Kept subprocess | one parametrized case launches real xdist workers for worker-hook failures |
| `test_plugin_gates.py:653` `test_snapshot_failure_does_not_error_the_test` #1 | Switched in-process | checks gate/report behavior in generated suites; clean-environment and SQLAlchemy-sensitive cases remain subprocesses. |
| `test_plugin_gates.py:675` `test_early_attach_failure_does_not_interrupt_session` #1 | Kept subprocess | sitecustomize must run at interpreter startup before pytest/sharpit imports |
| `test_plugin_inert.py:93` `test_nothing_assessed_unknown_fails_unless_allowed` #1 | Kept subprocess | isolates autodetection from apps already loaded in the host test process |
| `test_plugin_inert.py:102` `test_no_application_unknown_has_no_synthetic_app` #1 | Kept subprocess | isolates autodetection from apps already loaded in the host test process |
| `test_plugin_inert.py:136` `test_allow_unknown_exits_zero` #1 | Kept subprocess | isolates autodetection from apps already loaded in the host test process |
| `test_plugin_report_only.py:14` `test_report_only_does_not_fail_finding_test` #1 | Switched in-process | checks report-only exit/JUnit behavior in a generated suite. |
| `test_plugin_reports.py:41` `_run_report_corpus` #1 | Switched in-process | checks masking, findings and report output; the live SQLAlchemy engine case stays isolated. |
| `test_plugin_reports.py:77` `test_failed_gate_findings_listed_on_the_test` #1 | Switched in-process | checks masking, findings and report output; the live SQLAlchemy engine case stays isolated. |
| `test_plugin_reports.py:101` `test_live_engine_driver_counts_as_covered` #1 | Kept subprocess | live SQLAlchemy engine/Cython module state can outlive inline-run sys.modules restoration |
| `test_plugin_reports.py:135` `test_default_terminal_counts_notes_but_reports_keep_findings` #1 | Switched in-process | checks masking, findings and report output; the live SQLAlchemy engine case stays isolated. |
| `test_plugin_swallowed.py:41` `test_spike_f1_swallowed_attribute_error_fails` #1 | Kept subprocess | the exception monitor uses interpreter-level sys.monitoring tool IDs and exception state |
| `test_plugin_swallowed.py:247` `test_bare_exception_handler_gates` #1 | Kept subprocess | the exception monitor uses interpreter-level sys.monitoring tool IDs and exception state |
| `test_plugin_swallowed.py:258` `test_allow_swallowed_marker_keeps_the_test_passing` #1 | Kept subprocess | the exception monitor uses interpreter-level sys.monitoring tool IDs and exception state |
| `test_plugin_swallowed.py:272` `test_swallowed_respects_report_only_and_baseline` #1 | Kept subprocess | the exception monitor uses interpreter-level sys.monitoring tool IDs and exception state |
| `test_plugin_swallowed.py:274` `test_swallowed_respects_report_only_and_baseline` #2 | Kept subprocess | the exception monitor uses interpreter-level sys.monitoring tool IDs and exception state |
| `test_plugin_terminal.py:33` `test_verbose_keeps_advisor_notes` #1 | Switched in-process | checks terminal/JUnit rendering in generated single-process suites. |
| `test_plugin_terminal.py:55` `test_gate_failure_still_printed` #1 | Switched in-process | checks terminal/JUnit rendering in generated single-process suites. |
| `test_plugin_terminal.py:82` `test_gate_failure_counted_whatever_fail_on` #1 | Switched in-process | checks terminal/JUnit rendering in generated single-process suites. |
| `test_plugin_xdist.py:13` `test_plugin_loads_without_xdist` #1 | Kept subprocess | proves entry-point plugin loading in a clean interpreter without xdist installed |
| `test_plugin_xdist.py:14` `test_plugin_loads_without_xdist` #2 | Kept subprocess | proves entry-point plugin loading in a clean interpreter without xdist installed |
| `test_plugin_xdist.py:63` `test_xdist_app_seen_by_one_worker_passes` #1 | Kept subprocess | requires actual xdist workers |
| `test_plugin_xdist.py:80` `test_xdist_untraced_driver_unknown` #1 | Kept subprocess | requires actual xdist worker state |
| `test_plugin_xdist.py:93` `test_controller_warning_does_not_add_a_master_worker` #1 | Kept subprocess | requires controller and worker identities |
| `test_plugin_xdist.py:127` `test_xdist_controller_never_imports_app_code` #1 | Kept subprocess | asserts the controller does not import worker app code |
| `test_plugin_xdist.py:145` `test_xdist_crashed_worker_unknown` #1 | Kept subprocess | uses os._exit in an actual worker and checks worker-loss handling |
| `test_plugin_xdist.py:173` `test_xdist_each_worker_restores` #1 | Kept subprocess | asserts cleanup in two actual workers |
| `test_plugin_xdist.py:194` `test_xdist_tx_without_n_merges` #1 | Kept subprocess | uses the popen transport and worker report merging |
| `test_plugin_xdist.py:238` `test_xdist_snapshot_suppresses_worker_autodetect` #1 | Kept subprocess | requires actual xdist workers and per-worker app discovery |
| `test_plugin_xdist.py:261` `test_xdist_snapshot_hides_no_app_notice` #1 | Kept subprocess | requires actual xdist workers and controller output behavior |

## State isolation

- `Pytester.inline_run` snapshots/restores `sys.modules` and `sys.path`, but all modules already loaded by the outer pytest process remain visible to the nested run.
- The first full run found 12 failures among the converted cases: outer test modules had loaded `sqlite3` aliases and `aiosqlite`, making nested sessions unknown. All 12 nodes passed on untouched `release/0.4.0`. Those clean-environment cases now remain subprocess tests.
- `test_plugin_gates.py` had a module-level `_EARLY_CONNECT` alias that polluted unrelated inline runs. The alias is temporarily installed with `monkeypatch` only in its owning test.
- SQLAlchemy nested runs produced `TypeError: 'InternalTraversal' object is not callable` after inline-run module restoration; five SQLAlchemy behavior cases and one live-engine driver case remain isolated.
- Hook-failure xdist cases, startup `sitecustomize`, monitoring tool IDs, actual xdist, entry-point import, host-app import checks, and clean baseline-state cases remain process-bound.
- Coverage uses `[tool.coverage.run].patch = ["subprocess"]`; retained process runs remain covered and inline runs execute in the outer tracer.
- Fixture profile on `test_plugin_baseline.py`: 76 fixture setups; `pytester` setup was at most 9ms. Rebuild logging showed only `event_loop_policy@session` and `tmp_path_factory@session`, each set up once per worker.
- Cause checks: TS-001 checked and not implicated; TS-002–TS-009 not checked. Product-side PS-001–PS-008 not checked because no product code changed.

## Paired A/B and gates

A/B measurements (Windows, four rounds, `-n 4 --dist loadfile`; full-plugin noise spread 0.3s, final core-file noise spread 0.0s):

| File | Base median (s) | Change median (s) | Delta (s) |
|---|---:|---:|---:|
| `test_plugin_baseline.py` | 30.4 | 21.1 | -9.3 |
| `test_plugin_gate_defaults.py` | 21.0 | 17.7 | -3.3 |
| `test_plugin_gates.py` | 38.0 | 30.8 | -7.2 |
| `test_plugin_reports.py` | 11.3 | 3.8 | -7.5 |
| `test_plugin_bad_baseline.py` | 8.8 | 1.6 | -7.2 |
| `test_plugin_terminal.py` | 5.7 | 1.2 | -4.5 |
| `test_plugin_report_only.py` | 1.3 | 0.3 | -1.0 |
| `test_plugin_swallowed.py` | 8.8 | 7.8 | -0.9 |
| `test_plugin_xdist.py` | 37.8 | 33.3 | -4.4 |
| `test_plugin_inert.py` | 6.6 | 6.4 | -0.3 |
| `test_plugin_apps.py` | 1.2 | 1.1 | -0.1 |
| `test_plugin_attribution.py` | 1.4 | 1.3 | -0.1 |
| `test_plugin_options.py` | 0.5 | 0.5 | 0.0 |
| `test_subprocess_budget.py` | new file | — | — |

The full-plugin base rank on Windows (`-n 4 --dist loadfile`, 138 passed, 52.99s wall) ranked gates 45.5s/24%, xdist 36.2s/19%, baseline 36.1s/19%, and gate defaults 24.3s/13%. Linux CI JUnit artifacts were unavailable, so this is not a full-gate rank. `first-cost` on the base showed baseline first/rest median 3.5s/1.4s, gate defaults 2.9s/1.9s, reports 2.0s/1.9s, gates 1.4s/1.3s, xdist 2.8s/3.1s.

Final full-suite Windows rank (`-n 4`, 4,390 tests): xdist 35.3s/3%, gates 28.5s/3%, baseline 24.3s/2%, gate defaults 21.6s/2%. The whole run wall time was 428.79s.

Full-suite attempt before restoring process-bound cases: 4,369 passed, 9 skipped, 12 failed. The failures were replayed on the untouched base and all 12 passed. After restoring those subprocess boundaries, the plugin blast-radius run passed 139 tests.

Final verification: `ruff check` passed; `ruff format --check` passed; `pyright` passed. Final full suite (`uv run pytest -q -n 4`): 4,381 passed, 9 skipped, 76 warnings in 428.79s. `pytest-speed check`: 178 measured, 0 flagged, 155 new, 1 not measured; the new budget guard measured 0.1s. Reports: `docs/reports/2026-11-02-pytest-speed.md` and `C:/Users/ffrol/AppData/Local/Temp/sharpit-full-final-junit/report.xml`.

Local branch review against `52060f1b756a1de232792609b6bde29a5e7a20ab`: APPROVE, no findings. Lowest-direct and no-SQLAlchemy special jobs were not run; no dependency or plugin was added, and no PR is being opened.
