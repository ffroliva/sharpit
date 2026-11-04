# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane (no route, no DTO) |
| 2. BootUI port citations | N/A — sharpit-only test infrastructure, nothing ported |
| 3. Safety, no side effects, masking | N/A — no `src/` change; `no_side_effects` untouched |
| 4. Optional dependency gatekeeper | N/A — no import added under `src/` |
| 5. Overhead budget | N/A — no budget touched |
| 6. MCP read-only | N/A — no MCP tool added |
| 7. Svelte view | N/A — no UI change |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | `.superpowers/sdd/0.5.0/lanes/T-suite-speed/findings.md` (paired A/B and worker-count table) |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/T-suite-speed/handoff.md` |
