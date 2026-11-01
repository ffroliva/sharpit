# Lane F checklist (spec §6.1, items in order)

1. Golden parity: Task 3 infrastructure only, no panel parity claim. Evidence: `tests/golden.py`,
   `tests/fixtures/bootui/2.2.0/ids.json`, `tests/test_golden.py`; `tests/test_report_schema.py::test_schema_copies_identical`
   (existing green control).
2. Ported behaviour tests: N/A — F ports no BootUI panel behaviour.
3. Safety and masking: inert registration; unimplemented panels are absent and 404. Evidence:
   `tests/fastapi/test_unimplemented_panel_surface.py`, `tests/test_foundation_extension_slots.py`,
   `tests/test_safety_matrix.py` (scoped to implemented panels). `tests/safety/` and `tests/masking/` are deferred to F-rest.
4. Gatekeeper: `tests/engine/test_import_boundary.py` (pytest under every `sharpit/pytest_plugin/` module;
   `opentelemetry` only in `sharpit/engine/otel.py`); `add_connection_listener` keeps SQLAlchemy in `engine/sqla.py`.
5. Hot-path overhead: N/A — the only hot-path addition is one status comparison in `CaptureMiddleware.__call__`;
   `tests/fastapi/test_capture_overhead.py` stays green with its budget unchanged.
6. MCP read-only surface: unimplemented tools absent. Evidence: `src/sharpit/engine/panels04/__init__.py::tool_definitions`,
   `tests/fastapi/test_unimplemented_panel_surface.py`.
7. Svelte view: flag-gated placeholders. Evidence: `ui/src/views/*.svelte` (12 placeholders), `ui/src/App.svelte`,
   `ui/tests/component/panels04.test.ts`, `ui/tests/unit/nav.test.ts`; `npm --prefix ui run check` and vitest green.
8. Four gates: ruff check, ruff format --check, pyright, full pytest green at the lane head (see `handoff.md`
   §Verification); the coordinator writes the gate logs.
9. Live check: N/A — no panel implementation in F; `examples/fastapi_sqla` wiring is covered by `tests/test_example_app.py`.
10. Handoff: `.superpowers/sdd/0.4.0/lanes/F/handoff.md` (current).
