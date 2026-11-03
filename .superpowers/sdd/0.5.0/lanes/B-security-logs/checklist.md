# B-security-logs definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/fastapi/test_security_logs_api.py` (`test_report_golden_parity`, item-checked: the event and the `typeSummaries` item); `tests/fixtures/bootui/2.2.0/security-logs/nullable.json`; `.superpowers/sdd/0.5.0/lanes/B-security-logs/field-map.md` |
| 2. BootUI port citations | `tests/engine/capture/test_securitylogs.py` (`# ported: SecurityLogsServiceTests.*`); `tests/fastapi/test_security_logs_api.py` (`# ported: SecurityLogsControllerTests.*`) |
| 3. Safety, no side effects, masking | `tests/safety/test_b_security_logs_safety.py` (`test_security_logs_get_no_side_effects`, `test_inactive_security_logs_paths_404`); `tests/masking/test_b_security_logs_masking.py`; `tests/fastapi/test_security_logs_api.py` (`test_security_event_values_masked_everywhere`, `test_stream_guarded`) |
| 4. Optional dependency gatekeeper | N/A — the lane imports no optional or network library |
| 5. Overhead budget | `tests/fastapi/test_security_logs_overhead.py` (`BUDGET_NS = 2_000`, new constant); paired numbers in `.superpowers/sdd/0.5.0/lanes/B-security-logs/findings.md` |
| 6. MCP read-only | `tests/fastapi/test_security_logs_api.py` (`test_mcp_tools_list_has_only_get`); `src/sharpit/engine/tools04/security_logs.py` |
| 7. Svelte view | `ui/src/views/SecurityLogs.svelte`; `ui/tests/component/SecurityLogs.test.ts` (vitest 3/3, `npm run check` clean); bundle rebuilt in `src/sharpit/ui/static/index.html` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/B-security-logs/handoff.md` |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/B-security-logs/handoff.md` (§Live check) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/B-security-logs/handoff.md` |
