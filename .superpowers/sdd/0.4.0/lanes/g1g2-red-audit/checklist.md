| # | Item | Evidence |
|---|---|---|
| 1 | Change implemented | `scripts/dev/red_check.py` |
| 2 | Red tests first, assertion reds | `.superpowers/sdd/0.4.0/lanes/g1g2-red-audit/findings.md` |
| 3 | Shared red rule in the gate | `scripts/dev/lane_gate.py` |
| 4 | Tests for the gate rule | `tests/scripts/test_lane_gate.py` |
| 5 | Tests for red_check | `tests/scripts/test_red_check.py` |
| 6 | Strengthened baseline tests | `tests/engine/testsession/test_baseline.py` |
| 7 | Audit report | `docs/reports/2026-11-02-g1g2-red-audit.md` |
| 8 | Workflow docs | `docs/development/workflow.md` |
| 9 | Contract DTOs or HTTP surface | N/A — no runtime code in src/ changed |
| 10 | Safety model (activation, guard, masking, no side effects) | N/A — no src/ change; dev scripts and tests only |
