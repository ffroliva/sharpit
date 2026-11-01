# Lane D4: 2.2.0 `vulnerabilities`, `mcp-server`, and `rest-api` Drift

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D4`
- **Goal:** Bring `vulnerabilities` (`runtimeReach`, `advisorySymbols`, `advisorySymbolSource`, CVSS v4.0 fallback, MCP compaction), `mcp-server` (`supportedProtocolVersions`, `cancellations`, `progressDropped`, `_meta.progressToken`), and `rest-api` (`sampleLocations`, 2.2.0 rules `RAPI-RESP-010`, `RAPI-RESP-011`, `RAPI-VALID-006`, `RAPI-VER-007`) to BootUI 2.2.0 contract parity.
- **Spec sections:** §9 D4 (best effort), §6.1 (definition of done), §10.2 (Order 5), §10.3 (lane gate); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§7, 8, 19.
- **Worker profile:** **M**, **moderate** (touches OSV vulnerability rendering, MCP JSON-RPC protocol negotiation, and advisor rule DTOs).
- **Dependencies:** Foundation commit **F** and **D1** (for `DismissedFinding` support in advisor reports and split `tools.py`) must be merged first.
- **Files this lane MAY touch:**
  - `src/sharpit/engine/collectors/vulns/interpreter.py`, `src/sharpit/engine/collectors/vulns/cvss.py`, `src/sharpit/engine/collectors/vulns/service.py`
  - `src/sharpit/engine/mcp.py`
  - `src/sharpit/engine/advisors/rules.py`, `src/sharpit/engine/advisors/report.py`
  - `src/sharpit/engine/collectors/restapi/rules.py`, `src/sharpit/engine/collectors/restapi/service.py`
  - `src/sharpit/engine/tools.py` (or F's split MCP projection module)
  - `tests/engine/test_vulns.py`, `tests/engine/test_mcp.py`, `tests/engine/test_restapi.py`, `tests/engine/test_tools.py`, `tests/test_conformance.py`
  - `.superpowers/sdd/0.4.0/lanes/D4/*`
- **Files this lane MUST NOT touch (spec §10.3 protected files & other lanes):**
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (except lowering), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants, `uv.lock`, `pyproject.toml`, `guard.py` (D1), `capture/*` (D2), `pools.py`/`alembic.py`/`health.py`/`threads.py` (D3).

## Definition of Done Coverage (Spec §6.1)

| §6.1 Item | Satisfying Task | §6.1 Item | Satisfying Task |
|---|---|---|---|
| 1. Golden parity, `nullable.json`, `field-map.md` | Task 1, Task 2, Task 3 | 6. Ported `# ported:` tests | Task 1 (Step 1), Task 2 (Step 1), Task 3 (Step 1) |
| 2. Guard chain on all routes | Task 2 (Step 1), Task 3 (Step 4) | 7. Optional-dep & lowest-direct gates | Task 3 (Step 4) |
| 3. Masking before MCP/HTTP output | Task 1 (Step 1), Task 2 (Step 1) | 8. Overhead budgets untouched | Task 3 (Step 4) |
| 4. `no_side_effects` on GET/MCP calls | Task 1 (Step 1), Task 3 (Step 1) | 9. Quality gates (`ruff`, `pyright`, `pytest`) | Task 3 (Step 4) |
| 5. MCP & CLI parity (`get_vulnerabilities_report`) | Task 1 (Step 3), Task 2 (Step 3) | 10. Live verification (`live-verify.log`) | Task 3 (Step 4) |

## Review Focus

1. **Honest `runtimeReach` & `advisorySymbolSource` when Code Inventory is absent (`vulns/service.py`, `interpreter.py`)**: Because `code-inventory` is out of scope in 0.4.0 (spec §11), `DependenciesReport["runtimeReach"]` must emit `{"available": False, "unavailableReason": "Code Inventory panel is disabled.", "generation": None, "note": None, "incompleteReason": None}`, `DependencyDto["runtimeReach"]` must be `None`, and `Finding.to_dto()` must emit `"advisorySymbols": []`, `"advisorySymbolSource": "NONE"`, `"runtimeReach": None`. Pinned by `test_vulns_report_emits_2_2_0_runtime_reach_and_advisory_symbol_fields` in **Task 1**.
2. **MCP protocol version negotiation (`2026-07-28` and `2025-06-18` in `mcp.py:41, 218-262`)**: `McpServer` must advertise `supportedProtocolVersions: ["2026-07-28", "2025-06-18"]` (with `protocolVersion: "2025-06-18"` on `status()`), echo the client's requested version in `initialize` if it is in `SUPPORTED_PROTOCOL_VERSIONS` (falling back to `"2025-06-18"`), accept either version in the `MCP-Protocol-Version` header, and increment `cancellations` on `notifications/cancelled`. Pinned by `test_mcp_negotiates_2026_07_28_and_tracks_cancellations_and_progress_dropped` in **Task 2**.
3. **MCP `get_vulnerabilities_report` compaction (`tools.py`, `McpAgentViews.vulnerabilities`)**: Over MCP, `get_vulnerabilities_report` accepts `query` and `limit` (default `10`), filters dependencies to those with `vulnerabilityCount > 0` (unless `query` is provided), caps `advisories` to `5` per dependency (`ADVISORIES_PER_DEPENDENCY = 5`) and list items (`aliases`, `references`, `fixedVersions`) to `3`, and attaches `advisories` and `page` metadata without mutating the cached report. Pinned by `test_mcp_vulnerabilities_compacts_dependencies_and_advisories` in **Task 1**.
4. **Advisor `sampleLocations` and 2.2.0 `rest-api` rule catalog (`advisors/rules.py`, `restapi/rules.py`)**: Every `RuleResult.to_dto()` across all advisor panels must include `"sampleLocations": [...]` (`{"file", "line", "uri"}`), and `rest-api` must include the 4 new BootUI 2.2.0 rule IDs (`RAPI-RESP-010`, `RAPI-RESP-011`, `RAPI-VALID-006`, `RAPI-VER-007`) so rule counts match 2.2.0. Pinned by `test_rest_api_emits_sample_locations_and_2_2_0_rules` in **Task 3**.

---

### Task 1: `vulnerabilities` 2.2.0 DTO Keys, CVSS v4.0 Fallback, and MCP Compaction

**Files:**
- Modify: `src/sharpit/engine/collectors/vulns/interpreter.py:42-74`, `src/sharpit/engine/collectors/vulns/cvss.py:93-120`, `src/sharpit/engine/collectors/vulns/service.py:300-358`, `src/sharpit/engine/tools.py:489-499`
- Test: `tests/engine/test_vulns.py`, `tests/engine/test_tools.py`

**Interfaces:**
- Produces in `interpreter.py`: `Finding` fields `advisory_symbols: list[str]`, `advisory_symbol_source: str | None = "NONE"`, `runtime_reach: dict[str, Any] | None = None`.
- Produces in `service.py`: `DependenciesReport["runtimeReach"]` (`DependencyRuntimeReachSummaryDto`) and `DependencyDto["runtimeReach"] = None`.
- Produces in `tools.py`: `VULNERABILITIES_DEFAULT_LIMIT = 10`, `ADVISORIES_PER_DEPENDENCY = 5`, `ADVISORY_LIST_ITEMS = 3`, `_QUERY_LIMIT` schema on `get_vulnerabilities_report`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_vulns.py` and `tests/engine/test_tools.py`**
  - `# ported: VulnerabilityReportServiceTests.includesRuntimeReachAndAdvisorySymbolFields` (`test_vulns_report_emits_2_2_0_runtime_reach_and_advisory_symbol_fields`)
  - `# ported: McpAgentViewsTests.vulnerabilitiesCompactsDependenciesAndAdvisories` (`test_mcp_vulnerabilities_compacts_dependencies_and_advisories`)
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_vulns.py tests/engine/test_tools.py -k "vulns or vulnerabilities"` and verify RED**
- [ ] **Step 3: Implement `runtimeReach`, `advisorySymbols`, CVSS v4.0 fallback in `cvss.py`, and MCP `get_vulnerabilities_report` compaction**
- [ ] **Step 4: Run tests and commit** (`feat(vulns): add 2.2.0 runtimeReach/advisorySymbol DTO keys and MCP compaction`).

---

### Task 2: `mcp-server` 2.2.0 Protocol Versions (`2026-07-28`), `cancellations`, and `progressDropped`

**Files:**
- Modify: `src/sharpit/engine/mcp.py:41, 145-175, 218-262, 301-308`
- Test: `tests/engine/test_mcp.py`

**Interfaces:**
- Produces in `src/sharpit/engine/mcp.py`: `SUPPORTED_PROTOCOL_VERSIONS: Final[tuple[str, ...]] = ("2026-07-28", "2025-06-18")`; `McpServer.status()` keys `"supportedProtocolVersions": list(SUPPORTED_PROTOCOL_VERSIONS)`, `"cancellations": int`, `"progressDropped": int`; handling of `notifications/cancelled` and `_meta.progressToken`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_mcp.py`**
  - `# ported: McpProtocolTests.negotiatesSupportedProtocolVersionsAndTracksCancellations` (`test_mcp_negotiates_2026_07_28_and_tracks_cancellations_and_progress_dropped`)
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_mcp.py` and verify RED**
- [ ] **Step 3: Implement `SUPPORTED_PROTOCOL_VERSIONS`, header/initialize negotiation, `notifications/cancelled` counter, and `status()` fields**
- [ ] **Step 4: Run `uv run pytest -q tests/engine/test_mcp.py` and commit** (`feat(mcp): support 2026-07-28 protocol version and 2.2.0 status counters`).

---

### Task 3: Advisor `sampleLocations` and `rest-api` 2.2.0 Rules (`RAPI-RESP-010/011`, `RAPI-VALID-006`, `RAPI-VER-007`)

**Files:**
- Modify: `src/sharpit/engine/advisors/rules.py:32-66`, `src/sharpit/engine/advisors/report.py:40-65`
- Modify: `src/sharpit/engine/collectors/restapi/rules.py:34-279`, `src/sharpit/engine/collectors/restapi/service.py:55-95`
- Test: `tests/engine/test_restapi.py`, `tests/test_conformance.py`

**Interfaces:**
- Produces in `src/sharpit/engine/advisors/rules.py`: `RuleResult.sample_locations: tuple[dict[str, Any], ...] = ()` serialized as `"sampleLocations": list(self.sample_locations)` in `RuleResult.to_dto()`.
- Produces in `src/sharpit/engine/collectors/restapi/rules.py`: `RAPI-RESP-011` (`"Map an empty Optional read to an explicit status"`, `RESPONSES`, `LOW` — evaluates GET handlers returning `T | None` with default 200 status), `RAPI-VER-007` (`"Bodyless handlers must not require a Content-Type"`, `VERSIONING`, `MEDIUM`), plus `RAPI-RESP-010` and `RAPI-VALID-006` in `SKIPPED_RULES` (`applicable=False` for FastAPI).

- [ ] **Step 1: Write failing tests in `tests/engine/test_restapi.py`**
  - `# ported: RestApiAdvisorServiceTests.emitsSampleLocationsAnd220Rules` (`test_rest_api_emits_sample_locations_and_2_2_0_rules`: verifies `sampleLocations` on `RuleResult.to_dto()`, `RAPI-RESP-011` fires on `def get_item() -> Item | None` with 200 status, and `RAPI-RESP-010`/`RAPI-VALID-006`/`RAPI-VER-007` are present).
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_restapi.py` and verify RED**
- [ ] **Step 3: Implement `sampleLocations` on `RuleResult` and the 4 BootUI 2.2.0 rules in `restapi/rules.py`**
- [ ] **Step 4: Run full verification gates (`ruff`, `pyright`, `pytest`, `lowest-direct.log`, `no-sqlalchemy.log`, `live-verify.log`) and commit** (`feat(rest-api): add AdvisorRule sampleLocations and BootUI 2.2.0 RAPI rules`).

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3)

`.superpowers/sdd/0.4.0/lanes/D4/` MUST contain:
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `vulnerabilities`, `mcp-server`, and `rest-api` mapped to Python source or `nullable.json`.
- [ ] `findings.md` — `finding → test → red` table with all rows `fixed` or `parked`.
- [ ] `checklist.md` — Spec §6.1 items 1–10 with `lowest-direct.log`, `no-sqlalchemy.log`, and `live-verify.log` naming the head SHA.
- [ ] `handoff.md` — Last green command, next step, open findings.
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
