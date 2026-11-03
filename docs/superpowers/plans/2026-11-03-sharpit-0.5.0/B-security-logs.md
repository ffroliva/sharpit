# Lane B-security-logs: the `security-logs` panel

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `B-security-logs` (worktree `C:\development\github\sharpit-wt\0.5.0-B-security-logs`, branch `lane/0.5.0-B-security-logs`) |
| **Goal** | BootUI's `SecurityLogsReport` from a bounded, masked audit ring fed by 401/403 exchanges and the public `sharpit.record_security_event()`, with the `update` stream. |
| **Spec** | §5, §5.3; the 0.4.0 lane plan `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/B-security-logs.md` is the design (architecture, interfaces, field map, tasks); this file lists the 0.5.0 deltas |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §4; golden `security-logs/captured.json` (one real `AUTHENTICATION_SUCCESS` event, `page` metadata) |
| **Worker** | codex gpt-6-luna; reviewer Opus |
| **Council** | **required** (Wave B rule, 0.4.0 spec §8) |
| **Depends on** | R-transactions (R0: `fastapi/capture.py`); R0 next: D2 |
| **May touch** | `tests/fastapi/test_capture_wiring.py`, `tests/fastapi/test_capture_overhead.py`, `tests/fastapi/test_transactions_api.py` (add `"security-logs"` to their all-capture-panels-off lists only: the panel needs the capture middleware), `src/sharpit/ui/static/` (rebuilt bundle); coordinator amendment 2026-11-03; `src/sharpit/engine/capture/securitylogs.py` (new), `src/sharpit/fastapi/capture.py` (one assignment of `CaptureState.security_logs` and `CaptureWiring.on_security_event` at the attach point, nothing else), `src/sharpit/__init__.py` (one export line `record_security_event`), `src/sharpit/fastapi/routes/security_logs.py`, `src/sharpit/engine/panels04/security_logs.py`, `ui/src/lib/panels04/security_logs.ts`, `src/sharpit/engine/tools04/security_logs.py`, `ui/src/views/SecurityLogs.svelte`, `ui/tests/component/SecurityLogs.test.ts`, `tests/engine/capture/test_securitylogs.py`, `tests/fastapi/test_security_logs_api.py`, `tests/fastapi/test_security_logs_overhead.py`, `tests/safety/test_b_security_logs_safety.py`, `tests/masking/test_b_security_logs_masking.py`, `tests/fixtures/bootui/2.2.0/security-logs/nullable.json`, the lane folder `.superpowers/sdd/0.5.0/lanes/B-security-logs/` |
| **Must NOT touch** | `settings.py` (`security_logs_max_logs` exists, `settings.py:93`); guard; other lanes' modules |

## Deltas from the 0.4.0 plan

1. Paths re-read against `release/0.5.0` before Task 1 (`fastapi/capture.py` changed in R-transactions); record the
   attach-point line in `handoff.md`.
2. Golden parity is **item-checked**: the golden has a real event. `test_report_golden_parity` builds one event via
   `record_security_event(type="AUTHENTICATION_SUCCESS", principal=..., data={"details": ...})` and asserts the event
   and `typeSummaries` items, not just the shape.
3. No framework source emits `AUTHENTICATION_SUCCESS`; only `record_security_event` does (spec §14).
4. Task 0: predict (lane level) + `/sharpit:llm-council --tier high` → `council.md`.

Red rule: PLAN.md §Red rule.

## Must-cover

`test_security_event_values_masked_everywhere`, `test_stream_guarded`, `test_security_logs_get_no_side_effects`,
`test_inactive_security_logs_paths_404`, `test_mcp_tools_list_has_only_get`, `test_report_golden_parity`.

Detail (scenario rows 5, 6, 20, 36):

- `test_security_event_values_masked_everywhere` — `data={"details": "Bearer eyJhbGciOi..."}` and a 401 exchange
  with `Authorization`: masked in GET, stream frame and MCP `get_security_logs`; principal unchanged.
- `test_stream_guarded` — non-loopback peer and wrong Host on `GET {api}/security-logs/stream` → rejected by the guard.
- `test_security_logs_get_no_side_effects` (GET + stream), `test_inactive_security_logs_paths_404`,
  `test_mcp_tools_list_has_only_get`, the overhead budget test (new constant in the new file).

Everything else: the 0.4.0 plan's tasks and §6.1 table.

## Evidence

`.superpowers/sdd/0.5.0/lanes/B-security-logs/`: `council.md`, `handoff.md`, `findings.md`, `field-map.md`,
`checklist.md`.
