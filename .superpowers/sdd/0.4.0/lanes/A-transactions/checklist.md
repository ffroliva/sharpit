# A-transactions §6.1 checklist

| # | Requirement | Evidence |
|---|---|---|
| 1 | Golden parity, nullable keys, field map | `N/A — captured.json is absent from this lane worktree; coordinator fixture required for parity`; `.superpowers/sdd/0.4.0/lanes/A-transactions/field-map.md` |
| 2 | BootUI port citations | `N/A — implementation tests not yet written` |
| 3 | Safety, flags, guard, masking | `N/A — implementation tests not yet written` |
| 4 | Gatekeeper / no SQLAlchemy imports | `N/A — implementation not yet written` |
| 5 | Listener overhead budget | `N/A — implementation not yet measured` |
| 6 | MCP read only | `N/A — implementation not yet written` |
| 7 | Svelte view | `N/A — implementation not yet written` |
| 8 | Four gates, lowest-direct, no-SQLAlchemy | `N/A — coordinator gate logs` |
| 9 | Live check | `N/A — coordinator example is out of lane touch scope` |
| 10 | Current handoff | `.superpowers/sdd/0.4.0/lanes/A-transactions/handoff.md` |
