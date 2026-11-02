# Definition of done checklist

| # | §6.1 item | Evidence |
|---:|---|---|
| 1 | Golden parity | N/A — no panel DTO or golden fixture changed. |
| 2 | Ported behaviour tests | N/A — this is a pytest execution-mode change, not a BootUI behavior port. |
| 3 | Safety matrix | N/A — no route, panel, MCP tool, or secret source changed. |
| 4 | Gatekeeper boundary | N/A — no product import boundary or dependency gate changed. |
| 5 | Hot-path budget | N/A — no product hot-path code changed. |
| 6 | MCP surface | N/A — no MCP tool changed. |
| 7 | Svelte view | N/A — no UI files changed. |
| 8 | Four gates and platform jobs | `docs/reports/2026-11-02-speed-pytester-inprocess-handoff.md` records passing ruff, format, pyright, and full suite; lowest-direct/no-SQLAlchemy special jobs were not run because no dependency or plugin was added and no PR is being opened. |
| 9 | Live verification | N/A — no user-facing application behavior changed. |
| 10 | Lane handoff | `.superpowers/sdd/0.4.0/lanes/speed-pytester-inprocess/handoff.md`. |
