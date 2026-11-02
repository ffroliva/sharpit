# D3 Definition of Done Checklist

| # | Spec §6.1 item | Evidence |
|---:|---|---|
| 1 | Golden parity | `tests/engine/test_threads.py::test_d3_panels_2_2_0_golden_conformance`; `tests/engine/test_pools.py::test_pools_report_parity_for_nullpool_and_unlimited_overflow`; `tests/fixtures/bootui/2.2.0/threads/captured.json`; `tests/fixtures/bootui/2.2.0/threads/nullable.json`; `tests/fixtures/bootui/2.2.0/health/captured.json`; `tests/fixtures/bootui/2.2.0/database-connection-pools/pools.captured.json`; `tests/fixtures/bootui/2.2.0/database-connection-pools/nullable.json`. Alembic 2.2.0 parity is unverified; coordinator update to `docs/reference/PARITY.md` is recorded in `handoff.md`. |
| 2 | Ported tests cite BootUI source | `tests/engine/test_pools.py` |
| 3 | Safety, flags, guard chain, and masking | `tests/safety/test_d3_safety.py` exercises one QueuePool; legacy pool routes already appear in `tests/test_safety_matrix.py`; `tests/masking/test_d3_masking.py`; `tests/test_masking_corpus.py` |
| 4 | Gatekeeper and import boundary | `tests/engine/test_import_boundary.py`; `src/sharpit/engine/sqla.py` |
| 5 | Hot-path overhead | N/A — no capture middleware, SQL listener, or other hot path changed. |
| 6 | MCP read tools only | `src/sharpit/engine/tools.py`; `tests/engine/test_tools.py`. The planned default 25 for `get_threads` is parked because its normalization code is outside D3's May-touch list. |
| 7 | Svelte 5 panel view | N/A — D3 changes existing DTO behavior and MCP defaults only; it has no new panel view. |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | N/A — integration gate logs are coordinator-owned under the integration worktree. |
| 9 | Live check | N/A — coordinator-owned `live-verify.md` in the integration worktree. |
| 10 | Current handoff | `.superpowers/sdd/0.4.0/lanes/D3/handoff.md` |
