# Definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/fastapi/test_sql_trace_insights_api.py` (`test_insights_golden_parity`); `tests/fixtures/bootui/2.2.0/sql-trace/nullable.json`; `.superpowers/sdd/0.5.0/lanes/A-sqltrace-insights/field-map.md` |
| 2. BootUI port citations | `tests/engine/capture/test_sqlinsights.py` (`# ported: SqlTraceInsightsServiceTests.*`) |
| 3. Safety, no side effects, masking | `tests/safety/test_a_sqltrace_insights_safety.py`; `tests/masking/test_a_sqltrace_insights_masking.py` |
| 4. Optional dependency gatekeeper | N/A — no library imported (`sqlinsights.py` uses the stdlib and sharpit capture modules) |
| 5. Overhead budget | N/A — no hot path: computed on GET, bounded by the ring size |
| 6. MCP read-only | `tests/fastapi/test_sql_trace_insights_api.py` (`test_mcp_tools_list_has_only_get`) |
| 7. Svelte view | `ui/src/views/SqlTrace.svelte`; `ui/tests/component/sqlTraceInsights.test.ts` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/A-sqltrace-insights/handoff.md` |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/A-sqltrace-insights/handoff.md` (§Live check) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/A-sqltrace-insights/handoff.md` |
