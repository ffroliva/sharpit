# Lane G4 checklist (spec §6.1, items in order)

| Item | Description | Evidence / Status |
|---|---|---|
| 1 | Golden parity | N/A — procurement hygiene lane, not a panel lane. |
| 2 | Ported behavior tests | N/A — no BootUI panel behavior is ported. |
| 3 | Safety and masking | N/A — no panel data source or new secret source. |
| 4 | Gatekeeper | N/A — no library import change; `tests/engine/test_import_boundary.py` unchanged. |
| 5 | Hot-path overhead | N/A — no hot-path code change. |
| 6 | MCP read-only surface | N/A — no MCP surface change. |
| 7 | Svelte view | N/A — no panel view. |
| 8 | Four gates | Task 5: ruff check, ruff format --check, pyright strict, full pytest green in lane worktree. Log: `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\G4-pytest.log`. |
| 9 | Live check | N/A — no panel implementation; integration reviewer owns live verification. |
| 10 | Handoff | Task 5: current handoff and review findings in `.superpowers/sdd/0.4.0/lanes/G4/handoff.md`. |
