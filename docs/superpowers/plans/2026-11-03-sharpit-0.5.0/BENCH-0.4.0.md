# Lane BENCH-0.4.0: sharpit-bench Python round findings (U1/U2, U6, U7, U8)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development. One task at a time,
> `/sharpit:check` before every commit. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `BENCH-0.4.0` (worktree `C:\development\github\sharpit-wt\0.5.0-BENCH-0.4.0`, branch `lane/0.5.0-BENCH-0.4.0`, from `release/0.5.0`) |
| **Goal** | Close the gaps the bench found in 0.4.0 that the merged lanes' tests do not catch: a found-but-not-gated swallowed exception (U1/U2), missing first app-code location on ORM lazy-load N+1 (U6), batched loads counted as N+1 (U8), and a measured verdict on suite-level overhead (U7). |
| **Source** | sharpit-bench `main` @ 10d7cc2: `docs/python-round-0.4.0.md`, `results/sbx/py-c1/summary.json` (26 cases x 3 reps, Linux, CPython 3.14.10, `--sharpit --sharpit-report=sharpit-report.json`); tracker rows U1, U2, U6, U7, U8. Added by the coordinator 2026-11-03 at the owner's request (relayed by the bench session). |
| **Worker** | Claude subagent; reviewer another family (agy Gemini) |
| **Council** | not required |
| **Depends on** | T-swallowed-2, P-0.4.1 (both merged; this lane widens their goals) |
| **May touch** | `src/sharpit/engine/testsession/{swallowed,gates,facts}.py`, `src/sharpit/engine/sqla/orm.py` (the lazy-load first-site record only), `tests/pytest_plugin/test_plugin_swallowed_bench.py` and `tests/pytest_plugin/test_plugin_bench_pins.py` (add tests only), `tests/fixtures/apps/bench_twins/` (new twin apps), `tests/engine/testsession/test_gates.py`, `docs/superpowers/spikes/2026-11-04-pytest-plugin-overhead.md` (new), the lane folder |
| **Must NOT touch** | budget constants; `pytest_plugin/apps.py`, `options.py`; fingerprints (`advisors/findings.py`); any panel module |

## Must-cover

`tests/pytest_plugin/test_plugin_swallowed_bench.py::test_db_error_swallow_twin_fails_the_gate`,
`tests/pytest_plugin/test_plugin_bench_pins.py::test_lazy_load_n_plus_one_names_the_first_app_frame`,
`tests/pytest_plugin/test_plugin_bench_pins.py::test_selectinload_and_in_batch_never_count_as_n_plus_one`.

## Tasks

### Task 1: U1/U2 — D13 found but not gated

Bench: 0.4.0 reports `sharpit.swallowed-exception` for the D13 twin (crud.py:77) at INFO in 3/3 reps, so the run passes;
the other five swallowed cases are HIGH and fail. `test_db_error_swallow_found` checks presence only.
- [ ] Run the D13-shaped twin and record WHY it is INFO (suspect: `test_library_warn_does_not_hide_app_swallow`'s rule —
      SQLAlchemy logs on the missing table, which may be read as handling).
- [ ] Red: `test_db_error_swallow_twin_fails_the_gate` — the twin's finding is at the gating severity and the session
      status is fail.
- [ ] Fix the classification so a library's own log line never counts as the app handling its exception (the
      recognised-sink rule from T-swallowed-2 stays: only the app's raise, >=400 response, logger/warnings call,
      capture_exception, rollbar, bugsnag or a same-module helper doing one of those counts).

### Task 2: U6 — ORM lazy-load N+1 location

Bench: D01, D02, D04, D05, D06 print "first lazy load at unknown" (location 0/3 each); only D07 got `models.py:65`.
Relationship, statement and fix were present 3/3. P-0.4.1 added the location for non-relationship groups only
(`gates.py` "first at"), not for the lazy-load branch (`gates.py` "first lazy load at", `relationship_sites`).
- [ ] Red: `test_lazy_load_n_plus_one_names_the_first_app_frame` on a bench twin where the lazy load is triggered from
      app code through a helper: the message names the first application frame (not site-packages, `.venv*`, the
      test file or sharpit itself).
- [ ] Fix the lazy-load first-site record (`engine/sqla/orm.py`, recorded once per relationship group, never a stack
      walk per load: the lazy-relationship overhead budget is unchanged; run it paired against the base).

### Task 3: U8 — batched loads never count as N+1

Bench: queryspy strict false-alarms on all clean cases; sharpit must never count a batched `IN` query or a
`selectinload` load as N+1.
- [ ] `test_selectinload_and_in_batch_never_count_as_n_plus_one`: a twin using `selectinload` and an explicit
      `WHERE id IN (...)` batch produces no `sharpit.n-plus-one` finding. If it passes on the base it is a pin:
      mutation-prove it.

### Task 4: U7 — suite-level overhead (spike, verdict only)

Bench: about 1.7x wall time on a query-heavy suite with `--sharpit`.
- [ ] Measure with the perf-audit protocol (paired on/off, same box): where the time goes per query (listener, facts,
      report). Write `docs/superpowers/spikes/2026-11-04-pytest-plugin-overhead.md` with the numbers and a verdict:
      either a concrete fix (its own follow-up lane with a budget test) or "declined for 0.5.0" with the reason.
      No budget is added or raised in this lane.

## Evidence

Lane folder `.superpowers/sdd/0.5.0/lanes/BENCH-0.4.0/` (COMMON.md format). Paired budget numbers for Task 2 in findings.md.
