# Lane D1 checklist (spec §6.1, in order)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity | `.superpowers/sdd/0.4.0/lanes/D1/field-map.md`; `tests/engine/test_overview.py` (`test_overview_golden_parity` skips until G0a's 2.2.0 overview capture exists; no lane `nullable.json` needed, see field-map) |
| 2 | Ported tests cite BootUI | `tests/engine/advisors/test_dismissals.py` (`DismissedFindingsStoreTests.*`), `tests/fastapi/test_dismissed_findings_api.py` (`DismissedFindingsControllerTests.*`), `tests/engine/test_guard.py`, `tests/engine/test_tools.py` (`McpAgentViewsTests.configDropsOnlyThePropertySuggestions`) |
| 3 | Safety & masking | `tests/safety/test_d1_safety.py` (`no_side_effects` on `GET /dismissed-findings`, guard floor, inactive 404), `tests/masking/test_d1_masking.py` (note never echoed, no MCP/CLI binding), `tests/fastapi/test_dismissed_findings_api.py` (owning-panel gate, R-D1b); guard chain order unchanged in `src/sharpit/engine/guard.py`; `.superpowers/sdd/0.4.0/lanes/D1/predict-council.md` |
| 4 | Gatekeeper / import boundary | `tests/engine/test_import_boundary.py` green (only stdlib `base64`/`binascii` added) |
| 5 | Overhead budget | `tests/fastapi/test_capture_overhead.py`, `tests/fastapi/test_sql_trace_overhead.py` (no hot path touched; both pass alone, see handoff "Verification, review round 1") |
| 6 | MCP read-only | `tests/engine/test_tools.py` (no tool added; `get_config` drops `propertySuggestions`; the default limit needs `tool_dispatch.py`, handoff "Needs from coordinator") |
| 7 | Svelte 5 view | `ui/src/views/Overview.svelte` (h1 renamed to Scorecard only, R-D1c; `src/sharpit/ui/static/` rebuild is the coordinator's) |
| 8 | Four gates | N/A — coordinator gate logs |
| 9 | Live check | N/A — the coordinator records `live-verify.md` in the integration worktree |
| 10 | Handoff | `.superpowers/sdd/0.4.0/lanes/D1/handoff.md` |
