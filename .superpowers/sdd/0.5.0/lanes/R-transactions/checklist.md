# R-transactions definition of done checklist (§6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | `tests/fastapi/test_transactions_api.py` (`test_report_golden_parity`); `tests/fixtures/bootui/2.2.0/transactions/nullable.json`; `.superpowers/sdd/0.5.0/lanes/R-transactions/field-map.md` |
| 2. BootUI port citations | `tests/engine/capture/test_transactions.py` (`# ported: TransactionRecorderTests.*`); `tests/fastapi/test_transactions_api.py` |
| 3. Safety, no side effects, masking | `tests/safety/test_a_transactions_safety.py` (`test_transactions_get_no_side_effects`, `test_inactive_transactions_paths_404`); `tests/masking/test_a_transactions_masking.py` (`test_error_message_masked`) |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/sqla/events.py` (the only SQLAlchemy contact: `add_connection_listener` + `add_pool_listener`); `src/sharpit/engine/capture/transactions.py` imports no SQLAlchemy |
| 5. Overhead budget | `tests/fastapi/test_transactions_overhead.py` (30 µs constant unchanged; passes alone; `test_overhead_measures_production_contexts_path` proves the on side is the production path) |
| 6. MCP read-only | `tests/fastapi/test_transactions_api.py` (`test_transactions_mcp_exposes_only_the_read_tool`) |
| 7. Svelte view | `ui/src/views/Transactions.svelte`; `ui/tests/component/Transactions.test.ts` (vitest 2/2, svelte-check clean); bundle rebuilt in `src/sharpit/ui/static/index.html` |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs; lane run in `.superpowers/sdd/0.5.0/lanes/R-transactions/handoff.md` |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/R-transactions/handoff.md` (§Live check) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/R-transactions/handoff.md` |
