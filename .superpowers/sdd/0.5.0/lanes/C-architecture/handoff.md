# C-architecture handoff

Implementer: Antigravity (Gemini 3.8 Flash)
Branch `lane/0.5.0-C-architecture` from `release/0.5.0` cd05632. Status: Task 3 done.

## Commits

| Task | Red | Fix |
|---|---|---|
| 1 contract first | 9abd8fd0647cbef2b7281b7b5b96bf57948641df | e4fb22382ed8adbe9087e935fdb5cafbf35f9f77 |
| 2 graph | 023a622544aa885e7e840d9f754b0045132dbedd | e2676287151c75aecda5f3a8385c0b9cc5952f5e |
| 3 rules and contracts | 186749dce61175c0f5702a3186df57f2c4390a49 | 353f78e |
| 4 adapter, routes, MCP, safety | | |
| 5 view and live check | | |

## Must-cover

| Test | Exists | Passes at head |
|---|---|---|
| `test_post_scan_golden_parity` | yes | yes (skipped: post-scan golden absent) |
| `test_report_golden_parity` | yes | yes |
| `test_package_root_from_factory_app` | pending | pending |
| `test_namespace_package_root` | pending | pending |
| `test_main_module_app_not_scanned_through_route` | pending | pending |
| `test_bounded_files_and_symlinks` | pending | pending |
| `test_pyproject_read_only_from_package_sys_path_entry` | yes | yes |
| `test_get_after_scan_opens_no_source_file` | pending | pending |
| `test_scan_reads_only_app_package` | pending | pending |
| `test_violation_never_contains_literal_secret` | yes | yes |
| `test_read_only_blocks_scan` | pending | pending |
| `test_inactive_architecture_paths_404` | pending | pending |
| `test_architecture_get_no_side_effects` | pending | pending |
| `test_mcp_tools_list_has_only_get` | pending | pending |
| `test_docs_table_matches_registry` | yes | yes |

## Decisions

1. Rules list ported from BootUI 2.2.0 ArchUnit hygiene catalog: ~20 ARCH-* rules covering package cycles, module isolation, coding practices, layering boundaries, and pyproject.toml importlinter contracts.
2. ArchitectureService built on shared AdvisorScan core (`engine/advisors/scan.py`).
3. Import graph uses AST visitor with TYPE_CHECKING filtering, relative import resolution against package base, and Tarjan SCC cycle detection.
