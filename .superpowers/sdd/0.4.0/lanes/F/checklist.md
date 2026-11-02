# Lane F checklist (spec §6.1, items in order)

1. Golden parity (Task 3 infrastructure only, no panel parity claim): `tests/golden.py`, `tests/test_golden.py`, `tests/test_golden_shapes.py`, `tests/fixtures/bootui/2.2.0/ids.json`; `tests/test_report_schema.py` is the existing green schema-copies control.
2. Ported behaviour tests: N/A — F ports no BootUI panel behaviour.
3. Safety and masking (inert registration; unimplemented panels absent and 404): `tests/fastapi/test_unimplemented_panel_surface.py`, `tests/test_foundation_round2.py`, `tests/test_foundation_extension_slots.py`, `tests/test_safety_matrix.py`; `tests/safety/` and `tests/masking/` are deferred to F-rest.
4. Gatekeeper: `tests/engine/test_import_boundary.py` (pytest under every `sharpit/pytest_plugin/` module, `opentelemetry` only in `sharpit/engine/otel.py`); `add_connection_listener` keeps SQLAlchemy in `src/sharpit/engine/sqla.py`.
5. Hot-path overhead: N/A — the only hot-path addition is one status comparison in `CaptureMiddleware.__call__`; `tests/fastapi/test_capture_overhead.py` keeps its budget unchanged.
6. MCP read-only surface (unimplemented tools absent): `tests/test_foundation_round2.py`, `tests/test_surface_follows_flags.py`, `src/sharpit/engine/panels04/__init__.py`.
7. Svelte view (flag-gated placeholders): `ui/tests/component/panels04.test.ts`, `ui/src/App.svelte`, `ui/tests/unit/nav.test.ts`; `npm --prefix ui run check` and vitest green.
8. Four gates, lowest-direct and no-SQLAlchemy: N/A — coordinator gate logs (integration worktree `gate/`); the implementer's own ruff, format, pyright and full-suite results are in `.superpowers/sdd/0.4.0/lanes/F/handoff.md` §Verification.
9. Live check: N/A — no panel implementation in F; the `examples/fastapi_sqla` wiring is covered by `tests/test_example_app.py`.
10. Handoff: `.superpowers/sdd/0.4.0/lanes/F/handoff.md` (current).
