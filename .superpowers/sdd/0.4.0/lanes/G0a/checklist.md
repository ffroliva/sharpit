# G0a checklist (spec §6.1)

1. Golden parity: `tests/fixtures/bootui/2.2.0/<id>/captured.json` (+ `<name>.captured.json`) and `meta.json`; `tests/test_conformance.py::test_conformance_2_2_0_goldens_and_ids_mapping`.
2. Ported tests: N/A — golden capture and sanitiser lane.
3. Safety and masking: `tests/test_sanitize_golden.py` (`test_golden_2_2_0_fixtures_hold_no_secrets`) (`find_secrets == []` on every fixture) and the sanitiser aborts on a leak.
4. Import boundary: `src/sharpit/` untouched; `tests/engine/test_import_boundary.py` in the full run (see handoff.md for counts).
5. Overhead budget: N/A — fixtures and script only.
6. MCP read-only: N/A — no MCP or CLI change.
7. Svelte 5 view: N/A — no UI change.
8. Four gates: N/A — coordinator gate logs (integration worktree lanes/G0a/gate/).
9. Live check: live capture against tiny-ledger-bootui-ref, log `.superpowers/sdd/0.4.0/logs/G0a-capture.log` (integration worktree).
10. Handoff: `.superpowers/sdd/0.4.0/lanes/G0a/handoff.md`.
