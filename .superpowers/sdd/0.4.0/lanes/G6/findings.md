# Lane G6 — Findings & Red-to-Green Log

## Red-to-Green Table

Every red was replayed at its red SHA (detached temp worktree, `PYTHONPATH=<wt>/src`, `--junitxml`): each
test is a `<failure>` (an `AssertionError`; no `<error>`, no collection error, no pass), and all pass at the lane head.
Rows whose message starts with `assert` are AssertionErrors whose junit message pytest prints without the
`AssertionError:` prefix (a rewritten `assert result.ret == N`).

| Test id | Red SHA | Assertion message |
|---|---|---|
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_spike_f3_clean_suite_reaches_green | 1955ea34148c685581ca5f5cf088862b79e55e05 | assert <ExitCode.TESTS_FAILED: 1> == 0 (0.3.0 no-app unknown, exit 1) |
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_autodetect_single_prints_choice | 1955ea34148c685581ca5f5cf088862b79e55e05 | AssertionError: assert 'sharpit: using app appmod:app (pass --sharpit-app to choose)' in '...' |
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_autodetect_ambiguous_uses_none | 1955ea34148c685581ca5f5cf088862b79e55e05 | AssertionError: assert 'sharpit: several apps found (first_app:app, second_app:app); pass --sharpit-app module:attr' in '...' |
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_autodetect_ambiguous_across_workers_uses_none | 1955ea34148c685581ca5f5cf088862b79e55e05 | AssertionError: assert 'sharpit: several apps found (first_app:app, second_app:app); pass --sharpit-app module:attr' in 'bringing up nodes...' |
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_autodetect_never_imports | 1955ea34148c685581ca5f5cf088862b79e55e05 | AssertionError: assert 'sharpit: using app loaded_app:app (pass --sharpit-app to choose)' in '...' |
| tests/pytest_plugin/test_plugin_apps.py::test_autodetect_accepts_fastapi_and_starlette_only | 1955ea34148c685581ca5f5cf088862b79e55e05 | AssertionError: assert 'sample_autodetect_mod:main_app' in {} |
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_require_app_no_app_is_unknown | fe18128a907a98b04bed9192bcbe86ac8d397c5e | assert <ExitCode.OK: 0> == 1 |
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_require_app_ini_true_is_unknown | fe18128a907a98b04bed9192bcbe86ac8d397c5e | assert <ExitCode.OK: 0> == 1 |
| tests/pytest_plugin/test_plugin_gate_defaults.py::test_worst_status_order | fe18128a907a98b04bed9192bcbe86ac8d397c5e | AssertionError: assert 'PASSED' == 'SKIPPED' |
| tests/pytest_plugin/test_plugin_options.py::test_require_app_cli_and_ini | fe18128a907a98b04bed9192bcbe86ac8d397c5e | AssertionError: assert False is True (PluginOptions.require_app) |
| tests/pytest_plugin/test_plugin_terminal.py::test_verbose_keeps_advisor_notes | 04f05629ea658829f509a21991101249c7c8d2c7 | AssertionError: assert False is True (PluginOptions.verbose) |
| tests/pytest_plugin/test_plugin_terminal.py::test_gate_failure_still_printed | 04f05629ea658829f509a21991101249c7c8d2c7 | AssertionError: assert '  RAPI-DOC-001' not in '...' |
| tests/pytest_plugin/test_plugin_reports.py::test_default_terminal_counts_notes_but_reports_keep_findings | 04f05629ea658829f509a21991101249c7c8d2c7 | AssertionError: assert 'sharpit: 10 advisor notes in report.json' in '...' |

## Fix round 1 (/code-review xhigh) — finding → test → red

Code is unchanged across the red commits aac033a..b43e31b, so every red below was run at b43e31b (and the two cb6cc49
rows at cb6cc49) with `--junitxml`: each a `<failure>` AssertionError. All pass at the fix c1092bc8420a00a723fa1443d9f46ccc789c900f.

| Finding | Test id | Red SHA | Assertion message |
|---|---|---|---|
| 1 quiet filter hid a failed test gate (terminal.py:28; one predicate with JUnit) | tests/pytest_plugin/test_plugin_terminal.py::test_gate_failure_counted_whatever_fail_on | aac033a2173468c1729da1f6b8805638c48efbbc | AssertionError: assert '  sharpit.n-plus-one: 1' in '...' |
| 2 autodetected app without routes went down the install branch (UNKNOWN) | tests/pytest_plugin/test_plugin_gate_defaults.py::test_autodetected_app_without_routes_is_skipped | 379ca9c265af82cbd88970a8da9165706aa6fa93 | assert <ExitCode.TESTS_FAILED: 1> == 0 |
| 3 xdist: a snapshot on one worker did not suppress autodetect on another | tests/pytest_plugin/test_plugin_xdist.py::test_xdist_snapshot_suppresses_worker_autodetect | 0aa0a61045c064c6fbe62ba5ae07e1d849abdac1 | AssertionError: assert 'otherapp:app' not in ['otherapp:app', 'FastAPI#902cdf40'] |
| 3 xdist: "no application found" printed although an installed app was assessed | tests/pytest_plugin/test_plugin_xdist.py::test_xdist_snapshot_hides_no_app_notice | 0aa0a61045c064c6fbe62ba5ae07e1d849abdac1 | AssertionError: assert 'no application found' not in '...' |
| 4 installed/stdlib modules were candidates | tests/pytest_plugin/test_plugin_apps.py::test_autodetect_skips_installed_and_stdlib_modules | dd3ce5f860b5be2f525b6e7091f71ab5ea03309e | AssertionError: assert 'fake_dist_app_mod:app' not in {...} |
| 4 a test-module app was a candidate | tests/pytest_plugin/test_plugin_gate_defaults.py::test_autodetect_ignores_test_module_apps | cb6cc49973e4b8c34cb1b769552b399b8d57b406 | AssertionError: assert 'sharpit: using app realpkg.main:app (pass --sharpit-app to choose)' in '...' |
| 5 the name depended on import order | tests/pytest_plugin/test_plugin_apps.py::test_autodetect_names_app_by_shortest_module | cb6cc49973e4b8c34cb1b769552b399b8d57b406 | AssertionError: assert 'short_mod:app' in {'a_longer_reexport_mod:app': ...} |
| 6 wrapped / Host / subclassed mounts not excluded | tests/pytest_plugin/test_plugin_apps.py::test_autodetect_drops_wrapped_host_and_subclassed_mounts | 6a2fea19eba9aa1357a1c1f12322757fd1333a25 | AssertionError: assert 'mounted_children_mod:gz_child' not in {...} |
| 7 placeholders found by string matching | tests/pytest_plugin/test_plugin_apps.py::test_reconcile_keeps_a_skipped_run_that_is_not_a_placeholder | e417555094244e9c94c0f13748f7e352fa9f7c64 | AssertionError: assert AdvisorRun(... reason='several apps found (x); rule errored' ...) in [] |
| 8 classes matched by name | tests/pytest_plugin/test_plugin_apps.py::test_autodetect_matches_framework_classes_by_identity | b43e31b23d5a238111e92c2c09ccd96c29ff01d5 | AssertionError: assert 'named_like_starlette_mod:app' not in {...} |
| 8 candidates without the framework loaded | tests/pytest_plugin/test_plugin_apps.py::test_autodetect_is_empty_without_starlette_loaded | b43e31b23d5a238111e92c2c09ccd96c29ff01d5 | AssertionError: assert (('no_framework_loaded_mod:app', ...),) == () |

Notes:
- dd3ce5f's version of `test_autodetect_ignores_test_module_apps` crashed (`FileNotFoundError`: `mkpydir` does not
  create `src/`), so it is not a red; cb6cc49 corrected the setup and is its red SHA.
- `test_autodetect_names_app_by_shortest_module_across_workers` (9a1ddb2) passed on the old code, so it is a
  regression test, not a red; the in-process `test_autodetect_names_app_by_shortest_module` is the red for finding 5.
- Finding 7: `test_explicit_app_ignores_autodetect_candidates` (red fe18128) was deleted with the dead
  `select_app(explicit, ...)` branch, as the coordinator ruled; drop its row from the gate's red list.
- Finding 1 changes JUnit in one case: a failed test gate finding under `--sharpit-fail-on=CRITICAL` is now a
  `<failure>` (it silently passed before). Logged in `docs.md` (proposed §11 entry).

## Review of the WIP commit 9dfd9e2 (Antigravity, committed by the coordinator)

- Kept: `SKIPPED` in `AdvisorRun.status` and in the advisor and `$defs.advisorApp` status enums of both
  `report.schema.json` copies; `_merge_group` / `_advisor_summary` carry the reason for `SKIPPED` as for `UNKNOWN`.
- Fixed: `_worst` ranked PASSED above SKIPPED, against council R14 (FAILED > UNKNOWN > SKIPPED > PASSED). Pinned
  by `test_worst_status_order` (red at the WIP order, ), fixed in f0dd3519c07646ecbec722c860a715c1d6e3b8e4.
- Fixed: `_advisor_summary` dropped every run with `app is None` from `apps`; narrowed to app-less `SKIPPED`
  placeholders so no existing app-less run disappears (b50fec7d8c53bea361a8201f20b0286e7f28b16d).
- The WIP was implementation before a red; its behaviour is covered by the Task 1 reds at 1955ea3 (which predates
  the WIP: SKIPPED and the no-app line are asserted there) and by `test_worst_status_order`.

## Design notes

1. **Autodetect (F3).** `autodetect_apps()` snapshots `sys.modules`, skips non-exact `ModuleType` and `sharpit.*`,
   reads `vars(module)` only, matches `type(v).__mro__` names `fastapi.applications.FastAPI` /
   `starlette.applications.Starlette` (a class value has MRO `(type, object)`, so it never matches; no
   `isinstance`, no `getattr`, no PEP 562). Dedupe by `id()`: the first-defined name wins (insertion order; the
   red test pins `main_app` over a later `alias_app`), output sorted by `module:attr`. Apps mounted on a
   candidate (one Mount level) are dropped.
2. **Where autodetect runs.** Only when there is no explicit `--sharpit-app` and no installed-app snapshot, so
   `sharpit.install` apps keep 0.3.0 behaviour. One candidate is assessed; zero → `SKIPPED` with
   `no application found; rest-api skipped (pass --sharpit-app module:attr)`; several → `SKIPPED` with
   `several apps found (a, b); pass --sharpit-app module:attr`. SQL capture unknown reasons are untouched.
3. **xdist.** Each worker writes its candidates to `workeroutput["sharpit_apps"]` (None when it did not
   autodetect). The facade's `pytest_testnodedown` is outside the May-touch list, so `session.resolve_options`
   (called by the facade's `pytest_configure` in every process) registers a small `WorkerApps` plugin whose
   optional `pytest_testnodedown` unions the names on the controller. Before writing the report,
   `apps.reconcile_workers` drops the per-worker placeholders, drops autodetected runs when the union has more than
   one app, and re-adds one placeholder only when no rest-api run remains.
4. **require-app.** `--sharpit-require-app` / `sharpit_require_app`: no app records no run (0.3.0
   `NO_APPLICATION` unknown, exit 1); ambiguity becomes `UNKNOWN` with the ambiguity reason. No "skipped" line.
5. **Quiet notes (F4).** `terminal.py` counts only findings that fail the gate, with the exact JUnit predicate
   (not dismissed and severity at or above `failOnSeverity`); the remainder prints
   `sharpit: <N> advisor notes in <report>`. `--sharpit-verbose`, `sharpit_verbose` or `-vv` print all. JSON and
   JUnit are untouched.
