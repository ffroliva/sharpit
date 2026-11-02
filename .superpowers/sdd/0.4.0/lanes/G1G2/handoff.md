# G1G2 handoff

Implementer: Codex / GPT-6

## Status

- Current head: `2cbbcadb67e99f715238773bf45438f64998ce46` (Task 6 red commit).
- Done: required rules, lane plan, council amendments, spec r5 and F interfaces reviewed.
- Next: implement report-only/baselines, partial-run refusal, unknown-reason precedence, and per-finding dismissal matching.
- Decisions: follow council-r3 R1/R6/R8; use `report.finding_fails` for terminal/JUnit. Dismissal key is `(rule_id, identity or target)`; identities may contain spaces.
- Red commit `2cbbcadb67e99f715238773bf45438f64998ce46` pins the shared failure predicate, incomplete failed advisor run reason, and unknown reasons alongside fail status. All three fail as `AssertionError`.

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/engine/testsession/test_gates.py::test_fails_excludes_existing_and_info` | `2cbbcadb67e99f715238773bf45438f64998ce46` | existing finding incorrectly fails |
| `tests/engine/advisors/test_findings.py::test_failed_run_with_incomplete_scan_has_unknown_reason` | `2cbbcadb67e99f715238773bf45438f64998ce46` | incomplete failed run drops reason |
| `tests/engine/testsession/test_outcome.py::test_session_status_reports_unknown_reasons_when_fail` | `2cbbcadb67e99f715238773bf45438f64998ce46` | fail status omits unknown reasons |

## Gates

Not run yet. Final pytest must run detached with `-n 4` and a log outside this worktree.
