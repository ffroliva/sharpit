# D4 field map (BootUI 2.2.0 keys added by the drift -> sharpit source)

| Panel | BootUI key | sharpit source | Note |
|---|---|---|---|
| vulnerabilities | `runtimeReach` (report) | `src/sharpit/engine/collectors/vulns/service.py` `RUNTIME_REACH_UNAVAILABLE` | `available: false`, "Code Inventory panel is disabled." |
| vulnerabilities | `dependencies[].runtimeReach` | `vulns/service.py::_render` | always `null` |
| vulnerabilities | `dependencies[].vulnerabilities[].advisorySymbols` | `vulns/interpreter.py::Finding.to_dto` | `[]` (PyPI OSV records name no symbols) |
| vulnerabilities | `...vulnerabilities[].advisorySymbolSource` | `Finding.to_dto` | `"NONE"` |
| vulnerabilities | `...vulnerabilities[].runtimeReach` | `Finding.to_dto` | `null` |
| vulnerabilities | `coverage.archivesFirstParty`, `firstPartyArchives`, `firstPartyArchivesTruncated` | `vulns/service.py::_render` | `0`, `[]`, `false` |
| vulnerabilities | `scan.scannedAt` null before a scan | `tests/fixtures/bootui/2.2.0/vulnerabilities/nullable.json` | contract §8 |
| vulnerabilities | `score` CVSS v4.0 selection | not done | see handoff, parked |
| mcp-server | `supportedProtocolVersions` | `src/sharpit/engine/mcp.py` `SUPPORTED_PROTOCOL_VERSIONS` | `["2026-07-28", "2025-06-18"]` |
| mcp-server | `cancellations` | `McpServer.cancellations` | counts `notifications/cancelled` |
| mcp-server | `progressDropped` | `McpServer.status` | always `0`: no progress notification is sent |
| rest-api | `results[].sampleLocations` | `src/sharpit/engine/advisors/rules.py` (F5a-core) | `[]`: sharpit keeps no source locations (handoff) |
| rest-api | rules `RAPI-RESP-011` | `src/sharpit/engine/collectors/restapi/rules.py` | ported (LOW, responses) |
| rest-api | rules `RAPI-RESP-010`, `RAPI-VALID-006`, `RAPI-VER-007` | `restapi/rules.py::SKIPPED_RULES` | no FastAPI counterpart |
| MCP tool | `get_vulnerabilities_report` QUERY_LIMIT, compaction | `src/sharpit/engine/tools.py::_vulnerabilities_view` | default 10, 5 advisories, 3 list items, `page`, `advisories` |
| MCP tool | `get_threads` default limit 25 | `tools.py` `INVENTORY_DEFAULT_LIMIT`, `tool_dispatch.py::_normalized_arguments` | `Tool.default_limit` |
