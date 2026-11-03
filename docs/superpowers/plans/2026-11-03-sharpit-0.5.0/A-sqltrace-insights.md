# Lane A-sqltrace-insights: `GET /sql-trace/insights` (carried from 0.4.0)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `A-sqltrace-insights` (worktree `C:\development\github\sharpit-wt\0.5.0-A-sqltrace-insights`, branch `lane/0.5.0-A-sqltrace-insights`) |
| **Goal** | BootUI's `SqlTraceInsightsReport`: statement rankings by seven criteria and route attribution, computed on demand from the retained SQL Trace ring. |
| **Design** | `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/A-sqltrace-insights.md` governs |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-A.md` §8; golden `sql-trace/insights.captured.json` |
| **Worker** | agy-flavio, Gemini 3.8 (after A-mysql) or a Claude subagent; reviewer codex |
| **Council** | not required |
| **Depends on** | F5a-harness (extended `no_side_effects`); none on R0 except D2 follows it |
| **May touch** | `src/sharpit/ui/static/` (the rebuilt bundle; CI checks it matches `ui/`), `tests/fastapi/test_sql_trace_api.py` (delete `test_insights_404` only: it asserted the pre-0.5.0 stub; coordinator amendment 2026-11-03), `src/sharpit/engine/capture/sqlinsights.py` (new), `src/sharpit/fastapi/routes/sql_trace.py` (0 bytes today: the insights route), `src/sharpit/engine/tools04/sql_trace.py` (`get_sql_trace_insights` replaces `TOOLS = ()`), `ui/src/views/SqlTrace.svelte` (Insights tab only) + its `ui/tests/component/` test, `tests/engine/capture/test_sqlinsights.py`, `tests/fastapi/test_sql_trace_insights_api.py`, `tests/safety/test_a_sqltrace_insights_safety.py`, `tests/masking/test_a_sqltrace_insights_masking.py`, `tests/fixtures/bootui/2.2.0/sql-trace/nullable.json`, the lane folder `.superpowers/sdd/0.5.0/lanes/A-sqltrace-insights/` |
| **Must NOT touch** | `engine/capture/sqltrace.py` (public API only: `rows()`, `normalize`), `engine/tools.py` |

## Must-cover

`test_insights_golden_parity`, `test_insights_get_no_side_effects`, `test_insights_statement_text_masked`,
`test_mcp_tools_list_has_only_get`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/A-sqltrace-insights/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
