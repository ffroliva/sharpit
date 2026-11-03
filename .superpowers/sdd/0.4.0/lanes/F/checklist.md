# Definition of done checklist (0.4.0 spec §6.1)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane; `.superpowers/sdd/0.4.0/lanes/F/field-map.md` |
| 2. BootUI port citations | N/A — merge-gate tooling, no BootUI behaviour ported |
| 3. Safety, no side effects, masking | N/A — no runtime code changed; the gate's own protections: `tests/scripts/test_lane_gate.py` (`test_existing_protections_still_refuse`) |
| 4. Optional dependency gatekeeper | N/A — no new import; gate tables in `scripts/dev/lane_gate.py` |
| 5. Overhead budget | N/A — no hot-path code |
| 6. MCP read-only | N/A — no MCP tool |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — no sample app surface; `tests/scripts/test_lane_gate.py` drives the gate on throwaway repos |
| 10. Current handoff | `.superpowers/sdd/0.4.0/lanes/F/handoff.md` |
