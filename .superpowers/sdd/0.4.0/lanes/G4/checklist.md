# Lane G4 checklist (spec §6.1, items in order)

| Item | Description | Evidence |
|---|---|---|
| 1 | Golden parity | N/A — procurement hygiene docs lane, not a panel lane. |
| 2 | Ported behavior tests | N/A — no BootUI panel behavior is ported. |
| 3 | Safety and masking | N/A — docs lane, no panel data source or secret source. |
| 4 | Gatekeeper | N/A — no library import change. |
| 5 | Hot-path overhead | N/A — no hot-path code change. |
| 6 | MCP read-only surface | N/A — no MCP surface change. |
| 7 | Svelte view | N/A — no panel view. |
| 8 | Four gates | N/A — coordinator gate logs |
| 9 | Live check | N/A — docs lane, no panel to exercise live. |
| 10 | Handoff | `.superpowers/sdd/0.4.0/lanes/G4/handoff.md` |
