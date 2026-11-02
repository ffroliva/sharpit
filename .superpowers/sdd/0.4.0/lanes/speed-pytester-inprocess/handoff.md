# Pytester in-process speed lane handoff

Status: complete. Branch review approved; final full-suite verification passed.

- Base: `52060f1b756a1de232792609b6bde29a5e7a20ab` (`release/0.4.0` at lane start).
- Branch: `fix/0.4.0-speed-pytester-inprocess`.
- Fix commit: `9adb317afc9e3a79391c4c8e8bd589b1eea83a0c` (after red commit `8eaa9d6e459349aae79241306a55eff241674b40`).
- Red test: `tests/pytest_plugin/test_subprocess_budget.py::test_pytester_subprocess_calls_stay_within_file_budgets`, red commit `8eaa9d6e459349aae79241306a55eff241674b40`.
- Detailed per-call classification and cause evidence: [`docs/reports/2026-11-02-speed-pytester-inprocess-handoff.md`](../../../../../docs/reports/2026-11-02-speed-pytester-inprocess-handoff.md).
- Final A/B medians: baseline 30.4→21.1s; gate defaults 21.0→17.7s; gates 38.0→30.8s. Other changed-file medians and the process-bound reasons are in the report.
- Verification: plugin blast radius 139 passed; final full suite 4,381 passed, 9 skipped; ruff, format check, pyright, and `pytest-speed check` passed.
- Branch review against `52060f1`: APPROVE, no findings. Lowest-direct and no-SQLAlchemy special jobs were not run; no dependency or plugin was added and no PR is being opened.
- Do not push. Next: hand the local branch back to the coordinator for integration.
