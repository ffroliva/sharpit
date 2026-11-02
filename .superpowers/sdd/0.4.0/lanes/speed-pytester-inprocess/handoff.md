# Pytester in-process speed lane handoff

Status: implementation, local branch review, and final full-suite verification complete; local commits pending.

- Base: `52060f1b756a1de232792609b6bde29a5e7a20ab` (`release/0.4.0` at lane start).
- Branch: `fix/0.4.0-speed-pytester-inprocess`.
- Red test: `tests/pytest_plugin/test_subprocess_budget.py::test_pytester_subprocess_calls_stay_within_file_budgets`, red commit `8eaa9d6e459349aae79241306a55eff241674b40`.
- Detailed per-call classification and cause evidence: [`docs/reports/2026-11-02-speed-pytester-inprocess-handoff.md`](../../../../../docs/reports/2026-11-02-speed-pytester-inprocess-handoff.md).
- Final A/B medians: baseline 30.4→21.1s; gate defaults 21.0→17.7s; gates 38.0→30.8s. Other changed-file medians and the process-bound reasons are in the report.
- Verification: plugin blast radius 139 passed; final full suite 4,381 passed, 9 skipped; ruff, format check, pyright, and `pytest-speed check` passed.
- Branch review against `52060f1`: APPROVE, no findings. Lowest-direct and no-SQLAlchemy special jobs were not run; no dependency or plugin was added and no PR is being opened.
- Do not push. Next: commit the fix and evidence locally, then hand the branch back to the coordinator.
