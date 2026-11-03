# Lane D2: capture-panel drift to BootUI 2.2.0 (carried from 0.4.0)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `D2` (worktree `C:\development\github\sharpit-wt\0.5.0-D2`, branch `lane/0.5.0-D2`) |
| **Goal** | `activity`, `http-exchanges`, `exceptions`, `sql-trace`, `log-tail` and their tools at the 2.2.0 contract: `GET /activity/resources`, `GET /activity/journal`, `GET /http-exchanges/routes`, `GET /exceptions/caught`, `retention` metadata, `durationMicros`, `messageOmitted`, `get_http_routes` / `get_request_profile`. |
| **Design** | `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/D2-drift-capture.md` (tasks, field maps, tests) governs; this file gives the 0.5.0 deltas and the resolved paths |
| **Contract** | `BOOTUI-CONTRACT-0.4-DRIFT.md` (capture section); goldens `activity/{captured,resources.captured,journal.captured}.json`, `http-exchanges/routes.captured.json`, `exceptions/caught.captured.json`, `sql-trace/captured.json`, `log-tail/recent.captured.json` |
| **Worker** | codex gpt-6-luna; reviewer Opus |
| **Council** | not required (D1 handled the guard-touching drift) |
| **Depends on** | A-sqltrace-insights (R0: `routes/sql_trace.py`, `engine/tools.py`), B-security-logs (R0: `fastapi/capture.py`), R-transactions (R0: `fastapi/install.py`) |
| **May touch** | `tests/test_safety_matrix.py` (append the new base routes' rows to `ROWS` only: base routes are not PANEL rows; protected file, the coordinator passes it to lane_gate with `--allow-path`), `tests/safety/test_d2_safety.py` (optional: tool arguments and lane tests, no rows), `tests/surface.py` (append `get_http_routes` and `get_request_profile` to the tool and CLI-command lists only); coordinator amendment 2026-11-03; `src/sharpit/engine/capture/{exchanges,routes (new),sqltrace,logtail,activity,exceptions}.py`, `src/sharpit/engine/tools.py`, `src/sharpit/fastapi/capture.py`, `src/sharpit/fastapi/adapter.py`, `src/sharpit/fastapi/install.py`, `src/sharpit/fastapi/routes/{activity,http_exchanges,exceptions,sql_trace,log_tail}.py`, the matching `tests/engine/capture/test_*.py` and `tests/fastapi/test_*_api.py` files named in the 0.4.0 plan, `tests/fixtures/bootui/2.2.0/{activity,http-exchanges,exceptions,sql-trace,log-tail}/nullable.json`, the views `ui/src/views/{Activity,HttpExchanges,Exceptions,SqlTrace,LogTail}.svelte` + their `ui/tests/component/` tests, the lane folder `.superpowers/sdd/0.5.0/lanes/D2/` |
| **Must NOT touch** | `engine/sqla/`, `settings.py`, any 0.5.0 panel module, budget constants (the capture budget is checked, never raised) |

## Deltas from the 0.4.0 plan

1. Paths re-read on `release/0.5.0` before Task 1 (`fastapi/capture.py` and `install.py` changed in R-transactions and
   B-security-logs); record the slot lines in `handoff.md`.
2. `activity` memory keys stay `null` with a reason (U20 fills them later, only with O3); D2 builds the routes and
   every other key.
3. Every new route and tool gets the extended `no_side_effects` (F5a).

## Must-cover

`test_activity_resources_golden_parity`, `test_activity_journal_golden_parity`, `test_http_routes_golden_parity`,
`test_exceptions_caught_golden_parity`, `test_capture_drift_get_no_side_effects`, `test_new_tools_read_only`,
`test_capture_overhead_budget_unchanged`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/D2/`: `handoff.md`, `findings.md`, `field-map.md` (per drifted key), `checklist.md`.
