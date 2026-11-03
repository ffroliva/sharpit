# BENCH-0.4.0 handoff

Implementer: Claude subagent (claude-opus-5-5)

Status: DONE (all four tasks); branch `lane/0.5.0-BENCH-0.4.0`, base 834c83b (release/0.5.0).

## Done

| Task | Commits | Result |
|---|---|---|
| 1 U1/U2 D13 | red 3b40c2043858440319c69b3c5bfd91e8d7b8d988, fix 5ea93745aae983c3381509c098685adbb8dc3b39 | a swallowed PEP 249 error (by class name) gates HIGH; root cause in findings.md |
| 2 U6 lazy-load location | red 04e1942595584a8e59a73510cc3c0074fe1a8c6d, fix 7c66d49c89c207d601e8ca2ea8894fa1806a4374 | no app frame on the stack -> `first lazy load outside application code (X.y declared at path:line)`; paired budget in findings.md |
| 3 U8 batches | pin 614e7152670e496c799acc846d81cc5aed2012c4 | passes on the base; two mutations recorded |
| 4 U7 spike | a24fc73 | `docs/superpowers/spikes/2026-11-04-pytest-plugin-overhead.md`: fix proposed as its own lane (sink mask memo) |

## Must-cover

| Test | Exists | Passes at head |
|---|---|---|
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_db_error_swallow_twin_fails_the_gate | yes | yes |
| tests/pytest_plugin/test_plugin_bench_pins.py::test_lazy_load_n_plus_one_names_the_first_app_frame | yes | yes |
| tests/pytest_plugin/test_plugin_bench_pins.py::test_selectinload_and_in_batch_never_count_as_n_plus_one | yes | yes |

## Decisions (for the coordinator)

1. Task 1: the brief's suspect (a library log counted as handling) is not the cause; the 0.4.0 F1 gate only fails
   programming-error types. The fix widens that list with PEP 249 database errors. This changes the 0.4.0 §5.5 F1
   rule: confirm with the owner. Name match only (shortcut comment in `gates.py`); `programmingError` in the report
   stays false for these.
2. Task 2: the bench's five "unknown" cases are lazy loads inside FastAPI response serialization (pydantic, worker
   thread): there is no application frame to name. The fallback names the relationship's declaration line. The
   "test file" exclusion in the plan was not implemented: the bench never hit it (all five were None, not a test
   file), and the walk is shared with other sites.
3. Task 3: a repeated `IN` statement (>= 5 in one test) is still counted as N+1 by design; exempting `IN` would hide
   per-parent `IN` loops. Noted, not changed.
4. Task 4: verdict is a follow-up lane, not "declined": masking the fingerprint on every statement is ~57% of the
   profiled per-statement overhead.

## Files outside May-touch

None. The constant `LAZY_LOAD_OUTSIDE_APP` lives in `gates.py` (facts.py would create an import cycle).

## How to resume

Nothing open. Gates and full-suite logs: `C:/development/github/sharpit-wt/0.5.0-integration/.superpowers/sdd/0.5.0/logs/BENCH-0.4.0-*.log`.

## Gates at head (before this docs commit: a24fc73)

| Gate | Status |
|---|---|
| ruff check, ruff format --check, pyright | clean (0 errors) |
| full suite `pytest -q -n 4` | 5260 passed, 24 skipped, 2 failed (below) |
| `tests/fastapi/test_security_api.py::test_mcp_tools_list_has_only_get` | fails on the base 834c83b too (tool order/extra `get_security_logs` from the B-security-logs merge); not this lane's, not touched |
| `tests/engine/test_n_plus_one_overhead.py` | failed once under `-n 4` load (37.4 µs, noise 25.2, "overshoot within the noise"); passes alone at head, 9 of 9 isolated runs green (findings.md); budget unchanged |
