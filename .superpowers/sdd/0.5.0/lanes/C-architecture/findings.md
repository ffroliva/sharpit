# C-architecture findings

Implementer: Antigravity (Gemini 3.8 Flash)

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/test_architecture_docs_table.py::test_docs_table_matches_registry | 9abd8fd0647cbef2b7281b7b5b96bf57948641df | `assert [] == ['ARCH-PKG-001', ...]` | Fixed in e4fb22382ed8adbe9087e935fdb5cafbf35f9f77 |

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/engine/collectors/architecture/test_architecture_report.py::test_report_golden_parity | cd05632 | `report['scan']['status'] = 'WRONG_STATUS'` | `AssertionError: architecture/captured enum values: scan.status: 'WRONG_STATUS' not in [...]` |

## Rule mutations (each new rule removed in place, the named test run, the file restored with `git checkout`)

| Rule | Test | Assertion on removal |
|---|---|---|
