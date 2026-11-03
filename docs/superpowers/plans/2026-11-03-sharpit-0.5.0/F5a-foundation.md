# Lanes F5a-harness, F5a-source, F5a-core: foundation without SQLAlchemy

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.
> Three lanes (council r2 M2: one F5a was too big for the critical path). F5a-harness first; then F5a-source and
> F5a-core in parallel (disjoint files). Each has its own worktree, evidence folder and gate run.

| | F5a-harness | F5a-source | F5a-core |
|---|---|---|---|
| **Worktree / branch** | `C:\development\github\sharpit-wt\0.5.0-F5a-harness`, `lane/0.5.0-F5a-harness` | `...\0.5.0-F5a-source`, `lane/0.5.0-F5a-source` | `...\0.5.0-F5a-core`, `lane/0.5.0-F5a-core` |
| **Goal** | Safety harness every lane inherits: extended `SideEffectGuard`, per-lane CLI-action declarations, the interpreter-state call-site boundary rule, the mapper walk in the engine, settings for committed lanes, `pymysql` in the test extra, the 0.5.0 surface pin | `engine/appsource.py`, config's getenv scan moved onto it, one package-root resolver | The advisor scan core extracted from rest-api, the `RuleResult` contract (`VIOLATION`/`PASSED`/`SKIPPED`, `sampleLocations`), registry ownership, enum-value parity check |
| **Spec** | §4.4, §4.5 | §4.2 | §4.3, §4.4 (registry), §5 (post-scan parity) |
| **Worker** | codex gpt-6-luna; reviewer Opus | codex gpt-6-luna (high); reviewer Opus | codex gpt-6-luna (high) or claude-flavio; reviewer the other |
| **Council** | not required | **required** (`appsource`) | **required** (WAVE-B `[AMBIG]` vocabulary) |
| **Depends on** | F5-gate | F5a-harness | F5a-harness |
| **Protected files allowed (F5-gate `PROTECTED_ALLOWED`)** | `tests/conftest.py`, `pyproject.toml`, `uv.lock`, `tests/engine/test_import_boundary.py`, `src/sharpit/settings.py` | none | none |
| **May touch** | `tests/conftest.py` (`SideEffectGuard.verify`), `tests/safety/__init__.py` (`load()` reads per-lane CLI actions), `tests/test_safety_matrix.py` (`CLI_ACTIONS` from `load()`, `postgresql_read` added, stale comment at `:199`), `tests/engine/test_import_boundary.py` (call-site rule), `src/sharpit/engine/models.py` (new: mapper walk + configured-gate from `collectors/data.py`; no SQLAlchemy import, `getattr_static` only), `src/sharpit/engine/collectors/data.py` (imports it), `tests/engine/test_models.py`, `tests/engine/test_data.py` (moved tests), `src/sharpit/settings.py`, `pyproject.toml`, `uv.lock`, `tests/test_surface_05.py`, `tests/test_settings_05.py`, `tests/test_side_effect_guard.py`, the lane folder | `src/sharpit/engine/appsource.py` (new), `src/sharpit/engine/collectors/config/getenv_scan.py` (removed; logic in `appsource.py`), `src/sharpit/engine/collectors/config/__init__.py` (imports the engine, one resolver), `tests/engine/test_appsource.py`, the config getenv tests (import path only), the lane folder | `src/sharpit/engine/advisors/scan.py` (new), `src/sharpit/engine/advisors/rules.py` (`Status` → `VIOLATION`/`PASSED`/`SKIPPED`, `sampleLocations` default `[]`), `src/sharpit/engine/advisors/report.py` (filters on `VIOLATION`), `src/sharpit/engine/advisors/registry.py` (prefix `owns`, fingerprints), `src/sharpit/engine/advisors/__init__.py`, `src/sharpit/engine/collectors/restapi/{service,report}.py` (onto the core; `VIOLATION`), `src/sharpit/pytest_plugin/apps.py` (advisor discovery from the registry), `tests/golden.py` (`assert_enum_values`), `tests/fixtures/bootui/2.2.0/*/enums.json` (new: enum key paths per golden folder), `tests/engine/restapi/test_restapi_{report,rules,findings}.py`, `tests/engine/advisors/test_scan.py`, `tests/engine/advisors/test_advisor_rules.py`, the lane folder |
| **Must NOT touch** | `engine/sqla.py`, panel flags, routes, views; budget constants | anything outside its list | `engine/sqla.py`, `engine/collectors/restapi/rules.py` (D4's new rules), budget constants |

## Must-cover

F5a-harness: `tests/test_side_effect_guard.py::test_side_effect_guard_catches_interpreter_state`,
`tests/engine/test_import_boundary.py::test_interpreter_state_call_sites_only_in_session_modules`,
`tests/test_safety_matrix.py::test_cli_actions_declared_per_lane`,
`tests/engine/test_models.py::test_mapper_walk_in_engine_never_configures`,
`tests/test_surface_05.py::test_unimplemented_panel_has_no_surface_05`,
`tests/test_settings_05.py::test_05_settings_defaults_and_env`.

F5a-source: `tests/engine/test_appsource.py::test_appsource_never_imports_or_follows_symlinks`,
`tests/engine/test_appsource.py::test_single_module_app_indexes_only_that_file`,
`tests/engine/test_appsource.py::test_main_module_app_not_scanned_with_reason`,
`tests/engine/test_appsource.py::test_app_package_setting_never_imports`,
`tests/engine/test_appsource.py::test_config_and_advisors_resolve_same_root`,
`tests/engine/test_appsource.py::test_source_index_not_retained_after_scan`.

F5a-core: `tests/engine/advisors/test_scan.py::test_advisor_core_matches_rest_api_post_scan_golden`,
`tests/engine/advisors/test_scan.py::test_advisor_core_pre_scan_shape_all_four_goldens`,
`tests/engine/advisors/test_scan.py::test_advisor_core_masks_every_string`,
`tests/engine/advisors/test_scan.py::test_registry_owns_by_prefix`,
`tests/engine/advisors/test_scan.py::test_enum_values_checked_against_golden`.

## F5a-harness tasks

### Task 1: harness
- [ ] **Step 1:** Red commit (skeletons exist; assertions on behaviour):
  - `test_side_effect_guard_catches_interpreter_state` — parametrised fake GETs that each do one of:
    `tracemalloc.start()`, append to `gc.callbacks`, `gc.set_threshold(1)`, `gc.disable()`, `sys.settrace(f)`,
    `sys.setprofile(f)`, `sys.monitoring.use_tool_id(4, "x")`, open an app source file → `verify()` raises (expected
    failure: no raise). Each case restores state in `finally`.
  - `test_interpreter_state_call_sites_only_in_session_modules` — planted `tracemalloc.start()` in
    `engine/collectors/` reported; existing `import gc` heap walks not.
  - `test_cli_actions_declared_per_lane` — a safety file declaring `CLI_ACTIONS = [...]` is picked up by
    `test_cli_action_tools_gated`; `postgresql_read` listed.
  - `test_mapper_walk_in_engine_never_configures` (moved tests from `test_data.py` green; the new one asserts
    `collectors/data.py` imports `engine.models`).
  - `test_05_settings_defaults_and_env` — each new name in `{f.name for f in dataclasses.fields(SharpitSettings)}`
    (assertion, not `AttributeError`) and its env override works.
  - `test_unimplemented_panel_has_no_surface_05` — each of the eight flags monkeypatched `False`; a pin (mutation:
    drop the flag check in a scratch tree).
- [ ] **Step 2:** Implement; `pymysql` in `test`, `uv lock` (background). **Step 3:** Full gate (background). Commit
  `feat: 0.5.0 safety harness, boundary, settings`.

## F5a-source tasks

### Task 1: council
- [ ] `/sharpit:llm-council --tier high` on spec §4.2 → `council.md`.

### Task 2: `appsource` and the getenv scan on it
**Interfaces:** `resolve_package_root(app, modules) -> Path | None`, `build_index(root, *, max_files=2000,
max_file_bytes=524288, wall_budget_s=10.0) -> SourceIndex` (worker thread), `SourceIndex(modules, limitations,
truncated)`, `ModuleInfo(name, path, tree, imports, functions)`, the getenv helpers.
- [ ] **Step 1:** Red commit (skeleton: empty index, `None` root): `test_appsource_never_imports_or_follows_symlinks`
  (sentinel-on-import package, symlink and Windows junction to an outside dir; expected failure
  `assert "pkg.mod" in index.modules`), `test_bounded_files_and_size`, `test_fifo_and_device_skipped` (POSIX),
  `test_recursion_error_is_a_limitation`, `test_resolve_package_root_from_factory_app`,
  `test_single_module_app_indexes_only_that_file`, `test_main_module_app_not_scanned_with_reason`,
  `test_app_package_setting_never_imports`, `test_config_and_advisors_resolve_same_root`,
  `test_source_index_not_retained_after_scan`. Config's getenv tests stay green (import path only).
- [ ] **Step 2:** Implement (`os.scandir`, `realpath` + `commonpath`, `os.stat` + `S_ISREG`, `tokenize.open`,
  `ast.parse`). **Step 3:** Commit `feat: bounded app-source index; config getenv scan moves onto it`.

## F5a-core tasks

### Task 1: council
- [ ] `/sharpit:llm-council --tier high` on the WAVE-B §1 `[AMBIG]` vocabulary (`PASSED` vs `PASS`, `DISABLED`, no base
  package) and the `RuleResult` contract → `council.md`.

### Task 2: `RuleResult` contract and enum-value parity
- [ ] **Step 1:** Red commit:
  - `test_enum_values_checked_against_golden` — `assert_enum_values("rest-api", "captured", payload)` with
    `tests/fixtures/bootui/2.2.0/rest-api/enums.json` listing `scan.status` and `results[].status`; a payload whose
    result status is `FAILED` fails (expected failure today: `assert_parity` checks keys and types only,
    `tests/golden.py:66-100`, so `FAILED` passes).
  - `test_advisor_core_matches_rest_api_post_scan_golden` — rest-api report: `results[0].status == "VIOLATION"`,
    `sampleLocations` present (expected failure: `"FAILED"`, `advisors/rules.py:41`).
  - existing `tests/engine/restapi/test_restapi_{report,rules,findings}.py` assertions on `"FAILED"` change to
    `"VIOLATION"` in this commit (they encode the bug; listed in `findings.md`).
- [ ] **Step 2:** `Status = Literal["VIOLATION", "PASSED", "SKIPPED"]` (`rules.py:13`, final names per the council),
  `report.py:42` and `restapi/report.py:38` filter on `VIOLATION`, `sampleLocations` default `[]` (D4 fills it).
- [ ] **Step 3:** Green. Commit `fix: advisor rule results use BootUI's VIOLATION status and carry sampleLocations`.

### Task 3: advisor scan core from rest-api
**Interfaces:** `AdvisorScan(spec, rules, run, *, scope, extra_sections)`, `report()`, `scan(input)` (single-flight →
409 `"sharpit action already in progress"`), `violations(rule_id, scan_id, offset, limit)`.
- [ ] **Step 1:** Red commit (skeleton core returns `{}`): `test_advisor_core_pre_scan_shape_all_four_goldens` (fake
  advisor with each scope hook against `security`, `architecture`, `fastapi`, `database-advisor` `captured.json`),
  `test_advisor_core_single_flight` (`# ported: ArchitectureScannerTests.duplicateScanFailsFastAndLaterRetryRuns`),
  `test_advisor_core_violations_paged`, `test_advisor_core_unknown_rule_404`, `test_advisor_core_masks_every_string`.
- [ ] **Step 2:** Extract from `collectors/restapi/service.py:138-215`; rest-api runs on it; all rest-api tests green.
  Commit `refactor: rest-api runs on the shared advisor scan core`.

### Task 4: registry
- [ ] **Step 1:** Red commit: `test_registry_owns_by_prefix` — security flag monkeypatched on →
  `advisor_for("SEC-001").id == "security"` (expected failure: `None`, `registry.py:59-82`).
- [ ] **Step 2:** Prefix `owns` + fingerprint patterns; `pytest_plugin/apps.py` discovers advisors from the registry.
  Commit `feat: 0.5.0 advisors owned by id prefix`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/<lane id>/`: `handoff.md` (consumer interface table), `findings.md`, `field-map.md`
(`N/A`), `checklist.md`, `council.md` (F5a-source, F5a-core).
