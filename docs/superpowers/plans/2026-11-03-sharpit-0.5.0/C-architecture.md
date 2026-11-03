# Lane C-architecture: the `architecture` advisor (Python import graph)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `C-architecture` (worktree `C:\development\github\sharpit-wt\0.5.0-C-architecture`, branch `lane/0.5.0-C-architecture`) |
| **Goal** | BootUI's architecture advisor for the app package: import graph from F5's `appsource`, cycles, layering contracts from `pyproject.toml`, ~20 `ARCH-*` rules, GET cached / POST scan / paged violations. |
| **Spec** | §5, §5.5 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §1, §6; golden `architecture/captured.json` (pre-scan: `NOT_SCANNED`, `basePackages`, `severityCounts`) + G0's `scanned.captured.json` if present |
| **Worker** | agy-sergio, Gemini 4 Argon; reviewer Opus |
| **Council** | not required (no guard/masking/activation surface; source read is F5's) |
| **Depends on** | F5 |
| **May touch** | `src/sharpit/engine/collectors/architecture/` (new: `graph.py` (import graph + Tarjan SCC), `contracts.py` (`[tool.importlinter]` via `tomllib`, read only), `rules.py`, `report.py`), `src/sharpit/fastapi/routes/architecture.py` (F stub), `src/sharpit/engine/panels04/architecture.py` + `ui/src/lib/panels04/architecture.ts` (flag only), `src/sharpit/engine/tools04/architecture.py`, `ui/src/views/Architecture.svelte` + test, `docs/architecture-advisor-checks.md`, `tests/engine/collectors/architecture/`, `tests/fastapi/test_architecture_api.py`, `tests/safety/test_c_architecture_safety.py`, `tests/test_architecture_docs_table.py`, `tests/fixtures/apps/arch_*` (fixture packages), `tests/fixtures/bootui/2.2.0/architecture/nullable.json`, the lane folder |
| **Must NOT touch** | `engine/appsource.py`, `engine/advisors/*`, `settings.py`, `fastapi/introspector.py` |

**Architecture:** POST scan → adapter resolves the package root (`appsource.resolve_package_root`, or
`settings.app_package`) → `build_index` → graph → rules → cached report. `pyproject.toml` is read from the package's
project root (first parent holding one, bounded to 5 levels), parsed with `tomllib`; no import-linter import.
Field map: `basePackages` = resolved top-level package; `classesAnalyzed` = modules analysed (spec §14);
`rulesEvaluated`, `violationsFound`, `severityCounts`, `scan` as WAVE-B §6.

## Review Focus

1. The package root is right for a factory app, a `src/` layout and a namespace package; wrong → `NOT_SCANNED` with
   the reason, never another project's code.
2. Bounded: 5,000 modules, a 2 MB generated file, a symlink to `/` (F5's bounds, surfaced as `PARTIAL` + limitation).
3. GET after scan opens no file.

## Tasks

### Task 1: contract first
- [ ] Red commit: `test_report_golden_parity` (pre-scan; post-scan if G0 delivered, else skip with reason),
  `test_docs_table_matches_registry`, `nullable.json`.

### Task 2: graph
- [ ] Red commit (`tests/engine/collectors/architecture/test_graph.py`): `test_cycle_detected_with_members`,
  `test_relative_imports_resolved`, `test_type_checking_imports_excluded` (an `if TYPE_CHECKING:` import is not an
  edge), `test_conditional_import_is_an_edge`, `test_external_imports_ignored`. Then implement. Commit
  `feat: app import graph with cycle detection`.

### Task 3: rules and contracts
- [ ] Red commit, one test per rule (`# ported: <BootUI ArchUnit rule test>.<method>` where it maps), plus
  `test_importlinter_layers_contract_violation` and `test_importlinter_forbidden_contract_violation` (fixture
  `pyproject.toml`), `test_malformed_pyproject_is_a_limitation`. Implement. Commit `feat: architecture rules`.

### Task 4: adapter, routes, MCP, safety
- [ ] Tests: `test_package_root_from_factory_app`, `test_bounded_files_and_symlinks` (end to end through the route),
  `test_get_after_scan_opens_no_source_file`, `test_read_only_blocks_scan`, `test_inactive_architecture_paths_404`,
  `test_architecture_get_no_side_effects`, `test_mcp_tools_list_has_only_get`. Implement; flag on. Commit
  `feat: architecture advisor panel`.

### Task 5: view and live check
- [ ] Svelte view (reference `views/Architecture.vue`), vitest; live check on `examples/fastapi_sqla`. Commit
  `feat: architecture view`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/C-architecture/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
