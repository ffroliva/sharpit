# Lane F-rest checklist (spec §6.1, items in order)

1. Golden parity: N/A — no panel; F-rest changes only test infrastructure and the gate's replay command.
2. Ported behaviour tests: N/A — no BootUI behaviour is ported.
3. Safety and masking: `tests/safety/__init__.py`, `tests/safety/README.md`, `tests/test_safety_lane_rows.py`, `tests/test_safety_matrix.py`; `tests/masking/` stays deferred (no lane needs it yet).
4. Gatekeeper: N/A — no new import in `src/`.
5. Hot-path overhead: N/A — no `src/` change.
6. MCP read-only surface: `tests/test_surface_follows_flags.py` (idempotent catalogue rebuild).
7. Svelte view: N/A — no UI change.
8. Four gates, lowest-direct and no-SQLAlchemy: N/A — coordinator gate logs (integration worktree `gate/`); own results in `.superpowers/sdd/0.4.0/lanes/F-rest/handoff.md`.
9. Live check: N/A — no panel implementation.
10. Handoff: `.superpowers/sdd/0.4.0/lanes/F-rest/handoff.md`.
