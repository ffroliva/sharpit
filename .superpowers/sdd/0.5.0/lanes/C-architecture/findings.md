# C-architecture findings

Implementer: Antigravity (Gemini 3.8 Flash); fix round 1: Claude Code (claude-opus-5-5 subagent)

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/test_architecture_docs_table.py::test_docs_table_matches_registry | 9abd8fd0647cbef2b7281b7b5b96bf57948641df | `assert [] == ['ARCH-PKG-001', ...]` | Fixed in e4fb22382ed8adbe9087e935fdb5cafbf35f9f77 |
| tests/engine/collectors/architecture/test_graph.py::test_cycle_detected_with_members | 023a622544aa885e7e840d9f754b0045132dbedd | `assert len(cycles) == 1`: 0 cycles | Fixed in e2676287151c75aecda5f3a8385c0b9cc5952f5e |
| tests/engine/collectors/architecture/test_graph.py::test_relative_imports_resolved | 023a622544aa885e7e840d9f754b0045132dbedd | `assert 'rel_app.sub.b' in targets`: empty targets | Fixed in e2676287151c75aecda5f3a8385c0b9cc5952f5e |
| tests/engine/collectors/architecture/test_graph.py::test_type_checking_imports_excluded | 023a622544aa885e7e840d9f754b0045132dbedd | `assert targets == ['tc_app.runtime']`: empty targets | Fixed in e2676287151c75aecda5f3a8385c0b9cc5952f5e |
| tests/engine/collectors/architecture/test_graph.py::test_conditional_import_is_an_edge | 023a622544aa885e7e840d9f754b0045132dbedd | `assert 'cond_app.target' in targets`: empty targets | Fixed in e2676287151c75aecda5f3a8385c0b9cc5952f5e |
| tests/engine/collectors/architecture/test_graph.py::test_external_imports_ignored | 023a622544aa885e7e840d9f754b0045132dbedd | `assert targets == ['ext_app.internal']`: empty targets | Fixed in e2676287151c75aecda5f3a8385c0b9cc5952f5e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_packages_free_of_cycles | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_internal_packages | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_standard_streams | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_generic_exceptions | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_joda_time | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_forcibly_terminate | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_jdk_internal_apis | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_legacy_date_time | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_exceptions_naming | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_loggers_private | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_test_frameworks | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_mutable_static_fields | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_instantiate_thread | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_assertions_detail_message | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_controllers_repositories | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_repositories_controllers | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_services_controllers | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_repositories_services | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_rule_web_request_types | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_importlinter_layers_contract_violation | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_importlinter_forbidden_contract_violation | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(violations) >= 1`: 0 >= 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_malformed_pyproject_is_a_limitation | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert any("malformed" in lim.lower() for lim in limitations)`: False | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_pyproject_read_only_from_package_sys_path_entry | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert len(contracts) == 1`: 0 == 1 | Fixed in 353f78e |
| tests/engine/collectors/architecture/test_rules.py::test_violation_never_contains_literal_secret | 186749dce61175c0f5702a3186df57f2c4390a49 | `assert not any(SECRET in v.detail for v in violations)`: SECRET was in detail | Fixed in 353f78e |
| tests/fastapi/test_architecture_api.py::test_package_root_from_factory_app | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert resp.status_code == 200`: 404 == 200 | Fixed in 356479f |
| tests/fastapi/test_architecture_api.py::test_main_module_app_not_scanned_through_route | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert resp.status_code == 200`: 404 == 200 | Fixed in 356479f |
| tests/fastapi/test_architecture_api.py::test_read_only_blocks_scan | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert resp.status_code == 403`: 404 == 403 | Fixed in 356479f |
| tests/fastapi/test_architecture_api.py::test_inactive_architecture_paths_404 | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert client_active.get(...).status_code == 200`: 404 == 200 | Fixed in 356479f |
| tests/fastapi/test_architecture_api.py::test_architecture_get_no_side_effects | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert rep.status_code == 200`: 404 == 200 | Fixed in 356479f |
| tests/fastapi/test_architecture_api.py::test_mcp_tools_list_has_only_get | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert "get_architecture_report" in tool_names`: "get_architecture_report" in [] | Fixed in 356479f |
| tests/safety/test_c_architecture_safety.py::test_architecture_violations_tool_uses_rule_violations_schema | 4e8123845642daf96afed560eda3018b95a79866 | `assert architecture.input_schema == rest_api.input_schema` (pageLimit/maxResults vs limit; scanId optional) | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |
| tests/fastapi/test_architecture_source_reads.py::test_max_files_setting_bounds_scan | 4e8123845642daf96afed560eda3018b95a79866 | `assert data["scan"]["status"] == "PARTIAL"`: 'SCANNED' == 'PARTIAL' | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |
| tests/fastapi/test_architecture_source_reads.py::test_max_file_bytes_setting_bounds_scan | 4e8123845642daf96afed560eda3018b95a79866 | `assert any("larger than 1024 bytes" in lim ...)`: False | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |
| tests/fastapi/test_architecture_source_reads.py::test_app_package_not_imported_is_not_scanned | 4e8123845642daf96afed560eda3018b95a79866 | `assert data["scan"]["status"] == "NOT_SCANNED"`: 'SCANNED' == 'NOT_SCANNED' | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |
| tests/engine/collectors/architecture/test_contracts.py::test_pyproject_ignores_ancestor_sys_path_entry | 4e8123845642daf96afed560eda3018b95a79866 | `assert [c.name for c in contracts] == []`: ['ancestor'] == [] | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |
| tests/engine/collectors/architecture/test_contracts.py::test_pyproject_read_from_src_layout_entry_not_ancestor | 4e8123845642daf96afed560eda3018b95a79866 | `assert [c.name for c in contracts] == ["own"]`: ['ancestor'] == ['own'] | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |
| tests/engine/collectors/architecture/test_contracts.py::test_pyproject_not_read_when_package_entry_not_on_sys_path | 4e8123845642daf96afed560eda3018b95a79866 | `assert [c.name for c in contracts] == []`: ['parent'] == [] | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |
| tests/engine/collectors/architecture/test_graph.py::test_deep_import_chain_does_not_crash | 4e8123845642daf96afed560eda3018b95a79866 | `assert [len(c.members) for c in cycles] == [3000]`: [] == [3000] (RecursionError) | Fixed in bb968c94e627ce054700733fb27b1cdd66eadf7d |

## Historical SHA

Superseded in fix round 1 (review findings 3 and 6). Each test passed without testing anything or pinned a removed
behaviour; the replacement is named.

| Test | Historical SHA | Assertion | Superseded by |
|---|---|---|---|
| tests/fastapi/test_architecture_api.py::test_namespace_package_root | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert resp.status_code == 200`: 404 == 200 | deleted: needed the on-disk sys.path lookup spec §4.2 forbids; replaced by `test_loaded_namespace_package_root` |
| tests/fastapi/test_architecture_api.py::test_bounded_files_and_symlinks | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert resp.status_code == 200`: 404 == 200 | kept (vacuous: a path as app_package is rejected, scan NOT_SCANNED); replaced by `test_real_scan_bounded_files_and_symlinks` + `test_max_files_setting_bounds_scan` |
| tests/fastapi/test_architecture_api.py::test_get_after_scan_opens_no_source_file | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert scan_resp.status_code == 200`: 404 == 200 | kept (vacuous, same cause); replaced by `test_real_scan_then_get_opens_no_source_file` |
| tests/fastapi/test_architecture_api.py::test_scan_reads_only_app_package | 83d8567d24ff7afbd5bb0918dbe0f0b72108b6e3 | `assert resp.status_code == 200`: 404 == 200 | kept (vacuous, same cause); replaced by `test_real_scan_reads_only_app_package` |

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/engine/collectors/architecture/test_architecture_report.py::test_report_golden_parity | cd05632 | `report['scan']['status'] = 'WRONG_STATUS'` | `AssertionError: architecture/captured enum values: scan.status: 'WRONG_STATUS' not in [...]` |
| tests/fastapi/test_architecture_source_reads.py::test_real_scan_bounded_files_and_symlinks | 4e8123845642daf96afed560eda3018b95a79866 | appsource `_fill` link/containment check replaced by `if False:` | `assert [WindowsPath(...secret.py')] == []` |
| tests/fastapi/test_architecture_source_reads.py::test_real_scan_then_get_opens_no_source_file | 4e8123845642daf96afed560eda3018b95a79866 | `ArchitectureService.report` re-runs `scan_application` on every GET | `assert [WindowsPath(...b.py')] == []` |
| tests/fastapi/test_architecture_source_reads.py::test_real_scan_reads_only_app_package | 4e8123845642daf96afed560eda3018b95a79866 | `build_index(root.parent, ...)` (reads the sibling dir) | `assert [WindowsPath(...other_pkg/mod.py')] == []` |
| tests/fastapi/test_architecture_source_reads.py::test_loaded_namespace_package_root | 4e8123845642daf96afed560eda3018b95a79866 | resolver called with `app_package=None` | `assert 'NOT_SCANNED' == 'SCANNED'` |
| tests/fastapi/test_architecture_source_reads.py::test_architecture_uses_the_one_resolver | 4e8123845642daf96afed560eda3018b95a79866 | own `sys.modules[...].__path__` lookup instead of `appsource.resolve_package_root` | `assert 'arch_spy_pkg' in []` |
| tests/engine/collectors/architecture/test_architecture_report.py::test_post_scan_golden_parity_on_fixture_app | 4e8123845642daf96afed560eda3018b95a79866 | `_eval_cycles` cycles = [] | `assert 'ARCH-PKG-001' in []` |

## Rule mutations (each new rule removed in place, the named test run, the file restored with `git checkout`)

| Rule | Test | Assertion on removal |
|---|---|---|
| ARCH-PKG-001 | tests/engine/collectors/architecture/test_rules.py::test_rule_packages_free_of_cycles | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-PKG-002 | tests/engine/collectors/architecture/test_rules.py::test_rule_internal_packages | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-001 | tests/engine/collectors/architecture/test_rules.py::test_rule_standard_streams | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-002 | tests/engine/collectors/architecture/test_rules.py::test_rule_generic_exceptions | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-003 | tests/engine/collectors/architecture/test_rules.py::test_rule_joda_time | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-004 | tests/engine/collectors/architecture/test_rules.py::test_rule_forcibly_terminate | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-005 | tests/engine/collectors/architecture/test_rules.py::test_rule_jdk_internal_apis | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-006 | tests/engine/collectors/architecture/test_rules.py::test_rule_legacy_date_time | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-007 | tests/engine/collectors/architecture/test_rules.py::test_rule_exceptions_naming | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-008 | tests/engine/collectors/architecture/test_rules.py::test_rule_loggers_private | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-009 | tests/engine/collectors/architecture/test_rules.py::test_rule_test_frameworks | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-010 | tests/engine/collectors/architecture/test_rules.py::test_rule_mutable_static_fields | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-011 | tests/engine/collectors/architecture/test_rules.py::test_rule_instantiate_thread | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-COD-012 | tests/engine/collectors/architecture/test_rules.py::test_rule_assertions_detail_message | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-LAY-001 | tests/engine/collectors/architecture/test_rules.py::test_rule_controllers_repositories | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-LAY-002 | tests/engine/collectors/architecture/test_rules.py::test_rule_repositories_controllers | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-LAY-003 | tests/engine/collectors/architecture/test_rules.py::test_rule_services_controllers | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-LAY-004 | tests/engine/collectors/architecture/test_rules.py::test_rule_repositories_services | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-LAY-005 | tests/engine/collectors/architecture/test_rules.py::test_rule_web_request_types | `assert len(violations) >= 1` (0 >= 1) |
| ARCH-CON-001 | tests/engine/collectors/architecture/test_rules.py::test_importlinter_layers_contract_violation | `assert len(violations) >= 1` (0 >= 1) |
