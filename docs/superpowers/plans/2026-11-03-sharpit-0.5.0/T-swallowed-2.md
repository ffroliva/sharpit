# Lane T-swallowed-2: swallowed errors U1/U19 (pin what 0.4.0 does, fix only proven edges)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development. One task at a time,
> `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `T-swallowed-2` (worktree `C:\development\github\sharpit-wt\0.5.0-T-swallowed-2`, branch `lane/0.5.0-T-swallowed-2`) |
| **Goal** | The benchmark's swallowed-error cases (D12–D15, Java D13, the U17 loop case) produce the right findings under `pytest --sharpit`, pinned by tests; the two suspected AST edges are probed and fixed if red. |
| **Spec** | §7.2 |
| **Source** | upstream tracker U1, U2, U17, U19; 0.4.0 lane `T-swallowed-exceptions` (merged, `3ddeaea`) |
| **Worker** | Claude subagent; reviewer codex |
| **Council** | not required |
| **Depends on** | none (its files are disjoint from P-0.4.1's; council M10). Branches from `main`, like P |
| **May touch** | `src/sharpit/engine/testsession/swallowed.py` (AST rule only, behind a red), `tests/engine/testsession/test_swallowed.py`, `tests/pytest_plugin/test_plugin_swallowed_bench.py` (new), `tests/fixtures/apps/swallow_twins/` (new), the lane folder |
| **Must NOT touch** | the `sys.monitoring` hook and its tool-id logic, budgets, `gates.py` |

Red rule: PLAN.md §Red rule. Task 2's probes are run first; only a probe that fails becomes a red commit, the others
are recorded as pins with their mutation.

## Must-cover

`test_library_warn_does_not_hide_app_swallow`, `test_swallow_in_loop_is_one_finding`, `test_db_error_swallow_found`,
`test_logged_handler_is_not_a_finding`.

## What 0.4.0 already does

A broad clause (bare, `Exception`, `BaseException`) swallows when its **own body** neither raises nor calls a logger
or `warnings` (`swallowed.py:3`, `_LOG_CALLS` at `:26`). So a framework's WARN underneath does not count (U19), and
the fact is cached per handler and type, so a swallow in a loop is one finding (U17's 16-catch limit does not apply).

## Tasks

### Task 1: pins
- [ ] Twin fixtures from the bench cases. Tests:
  `test_library_warn_does_not_hide_app_swallow` (SQLAlchemy logs WARN on a missing table, the app's
  `except Exception: return 0` → finding at the app handler), `test_swallow_in_loop_is_one_finding` (200 iterations →
  one finding, count in evidence), `test_db_error_swallow_found` (U2, D13 Python twin), `test_logged_handler_is_not_a_finding`.
  Each mutation-proven if it passes first time (`findings.md`). Commit `test: pin swallowed-error bench cases`.

### Task 2: probe the edges (red first or nothing)
- [ ] `test_helper_that_logs_is_not_a_swallow` — `except Exception as e: self._report(e)` where `_report` logs:
  today a finding (false positive)? Decide by running. If red: count a call that passes the bound exception name as
  "handled" (`_report(e)`), logged in spec §14; if green, record.
- [ ] `test_non_logger_error_call_is_not_logging` — `except Exception: response.error("x")` (an object that is not a
  logger) counted as logging today (false negative)? If red: restrict `_LOG_CALLS` to receivers named `log`, `logger`,
  `_log`, `_logger`, `LOG`, `LOGGER`, `logging`, or a module-level name assigned from `logging.getLogger(...)`,
  `structlog.get_logger(...)` or `loguru.logger`; logged in §14.
- [ ] Commit per fix `fix: swallowed rule <edge>`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/T-swallowed-2/`: `handoff.md`, `findings.md`, `checklist.md`; a note to the bench
tracker owner: U1/U19 status with the test names.
