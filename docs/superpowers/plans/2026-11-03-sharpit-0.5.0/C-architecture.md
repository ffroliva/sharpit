# Lane C-architecture: the `architecture` advisor (Python import graph)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `C-architecture` (worktree `C:\development\github\sharpit-wt\0.5.0-C-architecture`, branch `lane/0.5.0-C-architecture`) |
| **Goal** | BootUI's architecture advisor for the app package: import graph from F5a's `appsource`, cycles, layering contracts from `pyproject.toml`, ~20 `ARCH-*` rules, on F5a's advisor core. |
| **Spec** | §5, §5.5 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §1, §6; golden `architecture/captured.json` (pre-scan) + G0's `scanned.captured.json`/`violations.captured.json` if present |
| **Worker** | agy-sergio, Gemini 4 Argon; reviewer Opus |
| **Council** | not required (source reading is F5a's, reviewed by its council) |
| **Depends on** | F5a |
| **May touch** | `src/sharpit/engine/collectors/architecture/` (new: `graph.py`, `contracts.py`, `rules.py`, `report.py`), `src/sharpit/fastapi/routes/architecture.py`, `src/sharpit/engine/panels04/architecture.py`, `ui/src/lib/panels04/architecture.ts`, `src/sharpit/engine/tools04/architecture.py`, `ui/src/views/Architecture.svelte`, `ui/tests/component/Architecture.test.ts`, `docs/architecture-advisor-checks.md`, `tests/engine/collectors/architecture/`, `tests/fastapi/test_architecture_api.py`, `tests/safety/test_c_architecture_safety.py` (declares `architecture_scan` as a CLI action, F5a's `load()`), `tests/test_architecture_docs_table.py`, `tests/fixtures/apps/arch_*`, `tests/fixtures/bootui/2.2.0/architecture/nullable.json`, the lane folder |
| **Must NOT touch** | `engine/appsource.py`, `engine/advisors/*`, `settings.py`, `fastapi/introspector.py` |

**Architecture:** POST scan → root from `appsource.resolve_package_root` (or `settings.app_package`) → `build_index` →
graph → rules → the core caches the report (scope hook: `basePackages`, `classesAnalyzed` = modules analysed).
`pyproject.toml`: only the one in the `sys.path` entry that holds the package (or its parent for a `src/` layout),
read with `tomllib`, contracts never executed, no import-linter import (spec §5.5, §14).

**Contract surface:** `GET {api}/architecture`, `POST {api}/architecture/scan`,
`GET {api}/architecture/rules/{id}/violations`; MCP `get_architecture_report`, `get_architecture_rule_violations`
(the latter is in the `mcp-server` golden's tool list); `architecture_scan` CLI-only (§14).

## Must-cover

`test_report_golden_parity`, `test_package_root_from_factory_app`, `test_namespace_package_root`,
`test_main_module_app_not_scanned_through_route`, `test_bounded_files_and_symlinks`, `test_pyproject_read_only_from_package_sys_path_entry`,
`test_get_after_scan_opens_no_source_file`, `test_scan_reads_only_app_package`, `test_violation_never_contains_literal_secret`,
`test_read_only_blocks_scan`, `test_inactive_architecture_paths_404`, `test_architecture_get_no_side_effects`,
`test_mcp_tools_list_has_only_get`, `test_docs_table_matches_registry`.

## Tasks

### Task 1: contract first
- [ ] `test_report_golden_parity` (pre-scan: a pin, F5a's core emits it; post-scan if G0 delivered: the red),
  `test_docs_table_matches_registry` (red: catalogue file absent → assertion on the missing ids), `nullable.json`.

### Task 2: graph
- [ ] Red commit (skeleton `build_graph` returns an empty graph; each test asserts an edge or a cycle member):
  `test_cycle_detected_with_members`, `test_relative_imports_resolved`, `test_type_checking_imports_excluded`,
  `test_conditional_import_is_an_edge`, `test_external_imports_ignored`. Implement. Commit
  `feat: app import graph with cycle detection`.

### Task 3: rules and contracts
- [ ] Red commit, one test per rule (`# ported: ArchitectureRulesTests.<method>` where BootUI has the analogue; the
  single-flight behaviour is F5a's, cited there as `ArchitectureScannerTests.duplicateScanFailsFastAndLaterRetryRuns`),
  plus `test_importlinter_layers_contract_violation`, `test_importlinter_forbidden_contract_violation`,
  `test_malformed_pyproject_is_a_limitation`, `test_pyproject_read_only_from_package_sys_path_entry` (a
  `pyproject.toml` two levels above the project is never opened: `open` spy), `test_violation_never_contains_literal_secret`
  (a module defining `API_KEY = "sk-live-..."` in a cycle: message, preview and MCP output hold `file:line` only).
  Implement. Commit `feat: architecture rules`.

### Task 4: adapter, routes, MCP, safety
- [ ] Red commit: `test_package_root_from_factory_app`, `test_namespace_package_root`,
  `test_main_module_app_not_scanned_through_route` (`NOT_SCANNED` + reason), `test_bounded_files_and_symlinks`,
  `test_get_after_scan_opens_no_source_file`, `test_scan_reads_only_app_package` (`open` spy: every path under the
  root), `test_read_only_blocks_scan`, `test_inactive_architecture_paths_404`, `test_architecture_get_no_side_effects`,
  `test_mcp_tools_list_has_only_get`. Implement; flag on. Commit `feat: architecture advisor panel`.

### Task 5: view and live check
- [ ] Svelte view (reference `views/Architecture.vue`), vitest; live check on `examples/fastapi_sqla`. Commit
  `feat: architecture view`.

**Split / stop:** if Task 3 passes ~600 lines of rules, the remaining rules park as `C-architecture-2` with the
catalogue rows marked "not yet"; the panel still merges.

## Evidence

`.superpowers/sdd/0.5.0/lanes/C-architecture/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
