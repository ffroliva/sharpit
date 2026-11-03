# A-transactions §6.1 checklist

| # | Requirement | Evidence |
|---|---|---|
| 1 | Golden parity, nullable keys, field map | `tests/fixtures/bootui/2.2.0/transactions/captured.json`; `tests/fixtures/bootui/2.2.0/transactions/nullable.json`; `.superpowers/sdd/0.4.0/lanes/A-transactions/field-map.md`; `N/A — no lane report-parity assertion; coordinator must verify the merged golden` |
| 2 | BootUI port citations | `tests/engine/capture/test_transactions.py`; `tests/fastapi/test_transactions_api.py` |
| 3 | Safety, panel flag, read-only, masking | `tests/safety/test_a_transactions_safety.py`; `tests/masking/test_a_transactions_masking.py`; `tests/fastapi/test_transactions_api.py` |
| 4 | Gatekeeper / no SQLAlchemy import in listener | `src/sharpit/engine/capture/transactions.py`; `tests/engine/capture/test_transactions.py` |
| 5 | Listener overhead budget | `tests/fastapi/test_transactions_overhead.py` — detached vs attached; measured 11.820 µs overhead, 8.780 µs noise, 30 µs budget (`A-transactions-round1-overhead-measure.jsonl` outside the worktree). |
| 6 | MCP read-only | `src/sharpit/engine/tools04/transactions.py`; `tests/fastapi/test_transactions_api.py` |
| 7 | Svelte view | `ui/src/views/Transactions.svelte`; `ui/tests/component/Transactions.test.ts` |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | `N/A — coordinator gate logs` |
| 9 | Live check | `N/A — shared example is outside this lane's May-touch list; coordinator must run the live check` |
| 10 | Current handoff | `.superpowers/sdd/0.4.0/lanes/A-transactions/handoff.md` |
