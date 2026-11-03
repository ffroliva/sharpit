# C-architecture findings

Implementer: Antigravity (Gemini 3.8 Flash)

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

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/engine/collectors/architecture/test_architecture_report.py::test_report_golden_parity | cd05632 | `report['scan']['status'] = 'WRONG_STATUS'` | `AssertionError: architecture/captured enum values: scan.status: 'WRONG_STATUS' not in [...]` |

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
