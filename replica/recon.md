# Recon: BootUI MVP slice (Replica method, REA evidence)

Target: BootUI 1.17.0 (github.com/jdubois/boot-ui, Apache-2.0), Spring Boot sample app, captured 2026-10-30.
Slice: the inner-loop core: activation and safety, panel registry, overview, config, mappings, loggers, beans and
dependency graph, vulnerabilities, MCP, CLI. Who for: Python/FastAPI developers on their own machine, plus the AI
agents they use. Size: **M**.

Replica's "no source, no network logs" rule exists for proprietary apps. BootUI is open source under Apache-2.0, so
this recon reads its source and records its runtime traffic on our own machine; sharpit credits it in `NOTICE`.

## Sources

| Source | What it gave | Where |
|---|---|---|
| BootUI source (DTOs, engine, Vue client, conformance catalog) | exact contract | `docs/reference/BOOTUI-CONTRACT-MVP.md` |
| Runtime capture of the sample app (Playwright HAR, UI walk) | real payloads, call order | `replica/evidence/` (gitignored, raw) |
| REA `inspect-web-network-capture` over the HAR | evidence bundle, id `ev_39c29f8c…` | `replica/evidence/rea-har-evidence/` |
| BootUI docs (features, properties) | intent, defaults | `C:\development\github\boot-ui\docs` |
| Screenshots of each panel | reference only, never shipped | `replica/evidence/S-*.png` |

Runtime findings that the docs alone would have missed:
1. With no active profile, Spring's fallback `default` profile `dev` does **not** activate BootUI: every path,
   including the API, returns 404. Activation reads *active* profiles only (fail closed confirmed).
2. The UI fetches `GET /api/mappings/flat`, not `/api/mappings`.
3. On load the UI calls `overview` and `panels` first, then each visible panel's GET. No POST happens on render.
4. `GET /api/mcp` answers 405: MCP is POST-only JSON-RPC.
5. Response sizes on a mid-sized app: config 344 KB, beans 247 KB, loggers 135 KB, mappings 119 KB. Paging
   (`limit`, default page 200 in the UI) matters.

## Screens (S) and flows (F)

| ID | Screen | Route | Key components | States |
|---|---|---|---|---|
| S00 | Shell / navigation | `/sharpit` | panel rail from registry, header with app name + activation | loading, panel unavailable, read-only |
| S01 | Overview | `#/overview` | identity cards, activation reason and warnings | enabled, warnings |
| S02 | Configuration | `#/config` | source filter, search, property table, masked badge | empty search, masked, METADATA_ONLY |
| S03 | Mappings | `#/mappings` | search, paged table | empty |
| S04 | Loggers | `#/loggers` | search, level selector per logger | change pending, 400 invalid level, read-only |
| S05 | Beans | `#/beans` | search, list, dependency graph toggle | graph focus |
| S06 | Vulnerabilities | `#/vulnerabilities` | inventory, scan button, findings by severity, dismiss | never scanned, scanning (409 busy), OSV failure, results, dismissed |
| S07 | MCP server | `#/mcp-server` | status, tool list, enabled/disabled | disabled (default) |

- F01 Developer understands where a config value comes from: S00 → S02, search, read source and masked state.
- F02 Developer raises a logger to DEBUG while reproducing a bug: S04, search, set level, see effective level change.
- F03 Developer checks dependencies for known CVEs: S06, Scan, read findings, dismiss a false positive.
- F04 Agent asks the same questions through MCP: `tools/list`, `get_config`, `get_vulnerabilities_report`.
- F05 Developer uses the CLI: `sharpit config --query db`, `sharpit vulnerabilities scan`.

## Data model

The contract DTOs are the data model: `PanelsReport`, `OverviewDto`, `ConfigReport`, `MappingsFlat`, `LoggersReport`,
`BeansReport`, `DependenciesReport` and MCP/CLI status. Field-level detail is in the contract file. Confidence: high (source + runtime agree).

## What cannot be ported (skip rows in features.csv)

JVM-only: conditions, DevTools classpath activation, free-on-idle, XSRF cookie priming, Maven version ordering.
Deferred for the MVP: config overrides (file writes), health, profile diff, every other panel.

## Hardest parts

1. Config provenance in Python. There is no single Environment, so sources must be assembled.
2. A faithful dev-server signal (the DevTools equivalent) that never fires in production, e.g. telling uvicorn's
   reload subprocess apart from multi-worker mode.
3. A new UI that is better than BootUI's while keeping its flows and states.
