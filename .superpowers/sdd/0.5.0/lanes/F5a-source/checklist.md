# Definition of done checklist (0.4.0 spec §6.1, as 0.5.0 spec §0 adopts it)

| Item | Evidence |
|---|---|
| 1. Golden parity, nullable fixture, field map | N/A — not a panel lane; `.superpowers/sdd/0.5.0/lanes/F5a-source/field-map.md` |
| 2. BootUI port citations | N/A — engine source index and config root resolution; no BootUI behaviour ported |
| 3. Safety, no side effects, masking | `tests/engine/test_appsource.py` (no import, no symlink/junction, `S_ISREG`, bounds, `__main__`, `app_package` never imports); `tests/engine/config/test_config_report.py` (`test_config_get_no_side_effects` unchanged, green) |
| 4. Optional dependency gatekeeper | `src/sharpit/engine/appsource.py` imports stdlib only (`ast`, `io`, `os`, `stat`, `threading`, `time`, `tokenize`); `tests/engine/test_import_boundary.py` green |
| 5. Overhead budget | N/A — no hot-path code; the scan runs once, lazily, on config's first GET (0.3.0 behaviour) |
| 6. MCP read-only | N/A — no new MCP tool; config's `get_config` path unchanged apart from the resolver |
| 7. Svelte view | N/A — no UI |
| 8. Four gates, lowest-direct, no-SQLAlchemy | N/A — coordinator gate logs |
| 9. Live check | N/A — no new route or panel surface |
| 10. Current handoff | `.superpowers/sdd/0.5.0/lanes/F5a-source/handoff.md` |
