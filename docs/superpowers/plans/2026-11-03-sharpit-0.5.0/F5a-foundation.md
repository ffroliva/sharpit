# Lane F5a: foundation without SQLAlchemy

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `F5a` (worktree `C:\development\github\sharpit-wt\0.5.0-F5a`, branch `lane/0.5.0-F5a`) |
| **Goal** | The shared pieces the panel lanes consume, so no two lanes edit one file: `appsource` (with config's getenv scan on it), the advisor scan core extracted from rest-api, registry ownership, the extended side-effect fixture, CLI-action declarations, the interpreter-state boundary rule, the mapper walk in the engine, settings for committed lanes, `pymysql` in the test extra. |
| **Spec** | §4.2–§4.5 |
| **Worker** | codex gpt-6-luna, high; reviewer Opus |
| **Council** | **required** — on Task 2 (`appsource`) and Task 3's `[AMBIG]` vocabulary; `council.md` before either task's code |
| **Depends on** | F5-gate merged (the gate must know `F5a` is a foundation lane) |
| **May touch** | `src/sharpit/engine/appsource.py` (new), `src/sharpit/engine/collectors/config/getenv_scan.py` → removed, its logic in `appsource.py`; `src/sharpit/engine/collectors/config/__init__.py` (import from the engine, one resolver); `src/sharpit/engine/advisors/scan.py` (new), `src/sharpit/engine/advisors/registry.py` (prefix `owns`, fingerprints), `src/sharpit/engine/advisors/__init__.py`, `src/sharpit/engine/collectors/restapi/service.py` (moved onto the core), `src/sharpit/engine/models.py` (new: mapper walk + configured-gate moved from `collectors/data.py`), `src/sharpit/engine/collectors/data.py` (imports it), `src/sharpit/pytest_plugin/apps.py` (advisor discovery from the registry only), `src/sharpit/settings.py` (rows, env), `pyproject.toml` + `uv.lock` (`pymysql` in `test`), `tests/conftest.py` (`SideEffectGuard.verify`), `tests/safety/__init__.py` (`load()` reads per-lane CLI actions), `tests/test_safety_matrix.py` (`CLI_ACTIONS` from `load()`, `postgresql_read` added, stale comment at `:199`), `tests/engine/test_import_boundary.py` (call-site rule), `tests/engine/test_appsource.py`, `tests/engine/advisors/test_scan.py`, `tests/engine/test_models.py`, `tests/test_surface_05.py`, `tests/test_settings_05.py`, the lane folder |
| **Must NOT touch** | `engine/sqla.py` (F5b's), any panel flag, route stub or view; budget constants |

## Must-cover

`test_appsource_never_imports_or_follows_symlinks`, `test_single_module_app_indexes_only_that_file`,
`test_main_module_app_not_scanned_with_reason`, `test_app_package_setting_never_imports`,
`test_config_and_advisors_resolve_same_root`, `test_source_index_not_retained_after_scan`,
`test_advisor_core_matches_rest_api_post_scan_golden`, `test_advisor_core_pre_scan_shape_all_four_goldens`,
`test_advisor_core_masks_every_string`, `test_registry_owns_by_prefix`, `test_side_effect_guard_catches_interpreter_state`,
`test_interpreter_state_call_sites_only_in_session_modules`, `test_cli_actions_declared_per_lane`,
`test_unimplemented_panel_has_no_surface_05`, `test_05_settings_defaults_and_env`.

## Tasks

### Task 1: council
- [ ] `/sharpit:llm-council --tier high` on spec §4.2 (containment, resolver, threading, the config exemption) and the
  WAVE-B §1 `[AMBIG]` vocabulary (`PASSED`/`PASS`, `DISABLED`, no base package) → `council.md`.

### Task 2: `appsource` and the getenv scan on it
**Interfaces:** `resolve_package_root(app, modules) -> Path | None` (module globals only), `build_index(root, *,
max_files=2000, max_file_bytes=524288, wall_budget_s=10.0) -> SourceIndex` (runs in a worker thread),
`SourceIndex(modules, limitations, truncated)`, `ModuleInfo(name, path, tree, imports, functions)`, and the getenv
helpers moved from `collectors/config/getenv_scan.py`.
- [ ] **Step 1:** Red commit (skeleton: `build_index` returns an empty index, `resolve_package_root` returns `None`):
  - `test_appsource_never_imports_or_follows_symlinks` — package whose `__init__` writes a sentinel on import, a
    symlink and (Windows) a junction to an outside dir: modules from the root present, sentinel absent, outside
    modules absent, one limitation per skip. Expected failure: `assert "pkg.mod" in index.modules`.
  - `test_bounded_files_and_size`, `test_fifo_and_device_skipped` (POSIX; `S_ISREG`), `test_recursion_error_is_a_limitation`
    (a 10,000-deep nested expression).
  - `test_resolve_package_root_from_factory_app`, `test_single_module_app_indexes_only_that_file`,
    `test_main_module_app_not_scanned_with_reason`, `test_app_package_setting_never_imports` (setting names a module
    not in `sys.modules` → `None` + reason; `sys.modules` unchanged).
  - `test_config_and_advisors_resolve_same_root`; `test_source_index_not_retained_after_scan` (`weakref` dead after
    the scan returns).
  - config's existing getenv tests stay green unchanged (move proven by them).
- [ ] **Step 2:** Implement (`os.scandir`, `realpath` + `commonpath`, `os.stat` + `S_ISREG`, `tokenize.open`,
  `ast.parse`). **Step 3:** Green. Commit `feat: bounded app-source index; config getenv scan moves onto it`.

### Task 3: advisor scan core from rest-api
**Interfaces:** `AdvisorScan(spec, rules, run, *, scope: Callable[[ScanInput], Mapping[str, object]],
extra_sections: Callable[[ScanResult], Mapping[str, object]])`, `report()`, `scan(input)` (single-flight → 409
`"sharpit action already in progress"`), `violations(rule_id, scan_id, offset, limit)`.
- [ ] **Step 1:** Red commit (skeleton core returning `{}`):
  - `test_advisor_core_matches_rest_api_post_scan_golden` — rest-api through the core: `assert_parity("rest-api",
    "captured", report)` with `scan.status == "SCANNED"` and `results[0].status == "VIOLATION"`.
  - `test_advisor_core_pre_scan_shape_all_four_goldens` — a fake advisor with each of the four scope hooks against
    `security`, `architecture`, `fastapi`, `database-advisor` `captured.json`.
  - `test_advisor_core_single_flight` (`# ported: ArchitectureScannerTests.duplicateScanFailsFastAndLaterRetryRuns`),
    `test_advisor_core_violations_paged`, `test_advisor_core_unknown_rule_404`,
    `test_advisor_core_masks_every_string` (a route path `/hooks/sk_live_...` and a file path holding a token come
    out masked).
- [ ] **Step 2:** Extract from `collectors/restapi/service.py:138-215`; rest-api uses it. All rest-api tests green
  unchanged. **Step 3:** Commit `refactor: rest-api runs on the shared advisor scan core`.

### Task 4: registry, safety harness, boundary, models, settings, extra
- [ ] **Step 1:** Red commit:
  - `test_registry_owns_by_prefix` — with the security flag monkeypatched on, `advisor_for("SEC-001").id ==
    "security"`; expected failure: `None` (`owns=lambda _: False`, `registry.py:59-82`).
  - `test_side_effect_guard_catches_interpreter_state` — a fake GET that calls `tracemalloc.start()` (and, separately,
    appends to `gc.callbacks`, sets `sys.settrace`, opens an app source file) → the guard's `verify` raises; expected
    failure: no raise.
  - `test_interpreter_state_call_sites_only_in_session_modules` — planted `tracemalloc.start()` in
    `engine/collectors/` is reported; existing `import gc` heap walks are not.
  - `test_cli_actions_declared_per_lane` — a safety file declaring `CLI_ACTIONS = [...]` is picked up by
    `test_cli_action_tools_gated`; `postgresql_read` listed.
  - `tests/engine/test_models.py::test_mapper_walk_in_engine_never_configures` (moved tests from `test_data.py` stay
    green; the new one asserts `collectors/data.py` imports `engine.models`).
  - `test_05_settings_defaults_and_env` — asserts each new name is in `{f.name for f in dataclasses.fields(SharpitSettings)}`
    and its env override works (assertion, not `AttributeError`).
  - `test_unimplemented_panel_has_no_surface_05` — each of the eight flags monkeypatched `False`: absent from
    `/panels`, `tools/list`, CLI, nav; path 404. A pin (mutation: drop the flag check in a scratch tree).
- [ ] **Step 2:** Implement; `pymysql` in the `test` extra, `uv lock` (background). **Step 3:** Full gate
  (background). Commit `feat: 0.5.0 foundation: registry, safety harness, boundary, settings`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/F5a/`: `council.md`, `handoff.md` (consumer interface table), `findings.md`,
`field-map.md` (`N/A`), `checklist.md`.
