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

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/engine/collectors/architecture/test_architecture_report.py::test_report_golden_parity | cd05632 | `report['scan']['status'] = 'WRONG_STATUS'` | `AssertionError: architecture/captured enum values: scan.status: 'WRONG_STATUS' not in [...]` |

## Rule mutations (each new rule removed in place, the named test run, the file restored with `git checkout`)

| Rule | Test | Assertion on removal |
|---|---|---|
