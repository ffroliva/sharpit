# Lane D1 checklist (spec §6.1, in order)

1. **Golden parity**: `field-map.md`; `tests/engine/test_overview.py::test_overview_golden_parity` (skips until G0a's
   2.2.0 overview capture exists; no lane `nullable.json` needed, see field-map).
2. **Ported tests cite BootUI**: `tests/engine/advisors/test_dismissals.py` (`DismissedFindingsStoreTests.*`),
   `tests/fastapi/test_dismissed_findings_api.py` (`DismissedFindingsControllerTests.*`), `tests/engine/test_guard.py`,
   `tests/engine/test_tools.py` (`McpAgentViewsTests.configDropsOnlyThePropertySuggestions`).
3. **Safety & masking**: `tests/safety/test_d1_safety.py` (`no_side_effects` on `GET /dismissed-findings`, guard floor,
   inactive 404), `tests/masking/test_d1_masking.py` (note never echoed, no MCP/CLI binding); guard chain order
   unchanged (`src/sharpit/engine/guard.py` diff is one dict entry); `predict-council.md`.
4. **Gatekeeper / import boundary**: `tests/engine/test_import_boundary.py` green (only stdlib `base64`/`binascii` added).
5. **Overhead budget**: N/A for changes (no hot path touched; `GuardMiddleware.send_with_headers` gains one
   membership check per header); `tests/fastapi/test_capture_overhead.py` and `test_sql_trace_overhead.py` green in
   the full run.
6. **MCP read-only**: no tool added; `get_config` drops `propertySuggestions` (`tests/engine/test_tools.py`); the
   default-limit part needs `tool_dispatch.py` (handoff "Needs from coordinator").
7. **Svelte 5 view**: N/A — envelope/drift lane; no UI file in the May-touch list (nav group label in
   `ui/src/lib/nav.ts` is O4-owned).
8. **Four gates**: `handoff.md` "Verification" (ruff check, ruff format --check, pyright, full pytest -n 4);
   lowest-direct / no-SQLAlchemy logs are the coordinator's `gate/`.
9. **Live check**: N/A in the lane — the coordinator records `live-verify.md` in the integration worktree.
10. **Handoff**: `.superpowers/sdd/0.4.0/lanes/D1/handoff.md`.
