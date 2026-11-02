# A-transactions §6.1 checklist

| # | Requirement | Evidence |
|---|---|---|
| 1 | Golden parity, nullable keys, field map | `N/A — G0a captured.json is absent from this worktree; transaction parity needs the coordinator fixture`; `tests/fixtures/bootui/2.2.0/transactions/nullable.json`; `.superpowers/sdd/0.4.0/lanes/A-transactions/field-map.md` |
| 2 | BootUI port citations | `tests/engine/capture/test_transactions.py`; `tests/fastapi/test_transactions_api.py` |
| 3 | Safety, panel flag, read-only, masking | `tests/safety/test_a_transactions_safety.py`; `tests/masking/test_a_transactions_masking.py`; `tests/fastapi/test_transactions_api.py` |
| 4 | Gatekeeper / no SQLAlchemy import in listener | `src/sharpit/engine/capture/transactions.py`; `tests/engine/capture/test_transactions.py` |
| 5 | Listener overhead budget | `tests/fastapi/test_transactions_overhead.py` — measured 14.507 µs overhead, 13.519 µs noise, 30 µs budget. A temporary 100 µs `tx_begin` delay failed at 643.573 µs; it was removed. Logs are under integration `.superpowers/sdd/0.4.0/logs/`. |
| 6 | MCP read-only | `src/sharpit/engine/tools04/transactions.py`; `tests/fastapi/test_transactions_api.py` |
| 7 | Svelte view | `ui/src/views/Transactions.svelte`; `ui/tests/component/Transactions.test.ts` |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | `N/A — coordinator gate logs` |
| 9 | Live check | `N/A — shared example is outside this lane's May-touch list; coordinator must run the live check` |
| 10 | Current handoff | `.superpowers/sdd/0.4.0/lanes/A-transactions/handoff.md` |
