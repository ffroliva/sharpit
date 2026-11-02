# Lane A-traces checklist (spec §6.1)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity | `tests/fastapi/test_traces_api.py` (`test_golden_parity` against `tests/fixtures/bootui/2.2.0/traces/captured.json`), `tests/fixtures/bootui/2.2.0/traces/nullable.json`, `.superpowers/sdd/0.4.0/lanes/A-traces/field-map.md` |
| 2 | `# ported:` citations | `tests/engine/capture/test_traces.py`, `tests/fastapi/test_traces_api.py` |
| 3 | Safety and masking | `tests/safety/test_a_traces_safety.py`, `tests/masking/test_a_traces_masking.py` |
| 4 | Gatekeeper | `src/sharpit/engine/otel.py` (reads `sys.modules`, never imports OpenTelemetry); `tests/engine/test_otel.py`, `tests/engine/test_import_boundary.py` green |
| 5 | Overhead budget | `tests/fastapi/test_traces_overhead.py` (`BUDGET_NS = 20_000` per ended span) |
| 6 | MCP read tools only | `tests/fastapi/test_traces_api.py` (`test_mcp_read_tool_only`) |
| 7 | Svelte view | `ui/src/views/Traces.svelte`, `ui/tests/component/traces.test.ts` |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs (implementer results in `.superpowers/sdd/0.4.0/lanes/A-traces/handoff.md`) |
| 9 | Live check | `.superpowers/sdd/0.4.0/lanes/A-traces/handoff.md` (section Live check: real SDK, in-process; it found and fixed a SQL-literal leak) |
| 10 | Handoff current | `.superpowers/sdd/0.4.0/lanes/A-traces/handoff.md` |
