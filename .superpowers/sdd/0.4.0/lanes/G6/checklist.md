# Lane G6 — Checklist (spec §6.1, items 1–10 in order)

| # | Item | Evidence |
|---|---|---|
| 1 | Golden parity | N/A — gate-defaults lane, not a panel lane |
| 2 | Ported behavior tests | N/A — no BootUI panel behavior is ported |
| 3 | Safety and masking | `tests/pytest_plugin/test_plugin_gate_defaults.py` |
| 4 | Gatekeeper | N/A — no new library import; FastAPI/Starlette classes are read from sys.modules, never imported |
| 5 | Hot-path overhead | N/A — session-finish and terminal code only; no capture or SQL hot path touched |
| 6 | MCP read-only surface | N/A — no MCP surface change |
| 7 | Svelte view | N/A — no panel view |
| 8 | Four gates | N/A — coordinator gate logs |
| 9 | Live check | N/A — no panel implementation; integration reviewer owns live verification |
| 10 | Handoff | `.superpowers/sdd/0.4.0/lanes/G6/handoff.md` |
