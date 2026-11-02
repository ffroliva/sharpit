# Lane G6 — Checklist (spec §6.1, items 1–10 in order)

| # | Item | Status / evidence |
|---|---|---|
| 1 | Golden parity | N/A — gate-defaults lane, not a panel lane. |
| 2 | Ported behavior tests | N/A — no BootUI panel behavior is ported (sharpit-only pytest plugin behavior). |
| 3 | Safety and masking | N/A — no panel source or new secret source. Autodetect reads `vars()` of exact `ModuleType` modules only: `tests/pytest_plugin/test_plugin_gate_defaults.py::test_autodetect_never_imports`. |
| 4 | Gatekeeper | N/A — no new library import (FastAPI/Starlette matched by MRO name, never imported). |
| 5 | Hot-path overhead | N/A — session-finish and terminal code only; no capture/SQL hot path touched. |
| 6 | MCP read-only surface | N/A — no MCP surface change. |
| 7 | Svelte view | N/A — no panel view. |
| 8 | Four gates | Task 3: see `handoff.md` → Verification Gates (ruff check, ruff format --check, pyright, pytest -n 4; log `0.4.0-integration/.superpowers/sdd/0.4.0/logs/G6-pytest.log`). |
| 9 | Live check | N/A — no panel implementation; integration reviewer owns live verification. |
| 10 | Handoff | `.superpowers/sdd/0.4.0/lanes/G6/handoff.md` (current after Task 3). |
