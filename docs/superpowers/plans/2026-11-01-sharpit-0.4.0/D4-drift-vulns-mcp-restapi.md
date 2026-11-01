# Lane D4: 2.2.0 `vulnerabilities`, `mcp-server`, and `rest-api` Drift

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D4`
- **Evidence folder:** `.superpowers/sdd/0.4.0/lanes/D4/`
- **Goal:** Bring `vulnerabilities` (`runtimeReach`, `advisorySymbols`, `advisorySymbolSource`, CVSS v4.0 fallback, MCP compaction), `mcp-server` (`supportedProtocolVersions`, `cancellations`, `progressDropped`, `_meta.progressToken`), and `rest-api` (`sampleLocations`, 2.2.0 rules `RAPI-RESP-010`, `RAPI-RESP-011`, `RAPI-VALID-006`, `RAPI-VER-007`) to BootUI 2.2.0 contract parity.
- **Spec sections:** §9 D4 (best effort 13), §6.1 (definition of done), §10.2, §10.3 (lane gate); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§7, 8, 19.
- **Worker profile:** **M**, **moderate** (touches OSV vulnerability rendering, MCP JSON-RPC protocol negotiation, and advisor rule DTOs; default worker in `PLAN.md`: `codex`).
- **Depends on:** `D1, G1G2` (`PLAN.md` line 93; per R1/R8/R13, `D1` implements `DismissalStore.dismissed_pairs(self) -> set[tuple[str, str]]` and `G1G2` updates `src/sharpit/engine/collectors/restapi/service.py` `_run`/`_scan` and `src/sharpit/engine/advisors/report.py::apply_dismissals` for per-finding dismissal matching). **Rule R0 (no intersecting May-touch in flight):** two lanes whose May-touch lists intersect never run at the same time; known serial chains are `D2 → D3 → D4` (`src/sharpit/engine/tools.py`, `tests/engine/test_tools.py`) and `T-swallowed-exceptions → D4` (`src/sharpit/engine/collectors/restapi/rules.py`).
- **Foundation interfaces consumed (`F-foundation.md` §"Foundation consumer interface table"):**
  - `sharpit.fastapi.routes.<id>` (`vulns`, `mcp`, `rest_api`) and `sharpit.fastapi.adapter`
  - `sharpit.engine.advisors.report.apply_dismissals` (`apply_dismissals(report: Mapping[str, Any], dismissed: Collection[str], occurrences: Mapping[str, Sequence[tuple[str, str, str]]] | None = None, dismissed_pairs: Collection[tuple[str, str]] = ()) -> dict[str, Any>`; `G1G2` matches `(rule_id, identity or target)` against pairs per R1/R13; each occurrence is `(fingerprint, message, identity_or_target)`; `sampleLocations` data comes from `_Evaluation.findings`, not by widening the occurrence tuple)
  - `sharpit.engine.collectors.restapi.service._evaluate`, `_run`, `assess` (`_evaluate(model: ApiModel, masker: Masker) -> _Evaluation`, `_run(done: _Evaluation, dismissed: Collection[str], fail_on: Severity, app: str | None, dismissed_pairs: Collection[tuple[str, str]] = ()) -> AdvisorRun`, `assess(model: ApiModel, masker: Masker, *, fail_on: Severity = DEFAULT_FAIL_ON, app: str | None = None, dismissed: Collection[str] = (), dismissed_pairs: Collection[tuple[str, str]] = ()) -> AdvisorRun` per R1/R8/R13)
  - `sharpit.engine.tools` discovery (compatibility facade `src/sharpit/engine/tools.py`; `F` discovers `sharpit/engine/tools04/<id_underscored>.py` for 0.4 panels per R3, while `D4` updates existing `get_vulnerabilities_report` in `src/sharpit/engine/tools.py`)
  - `tests.golden.assert_parity` (`assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None`, reads `<sharpit-id>/captured.json` or `<name>.captured.json`, else `provisional.json` marked unverified, plus `nullable.json` per R9)
  - `scripts/dev/lane_gate.py` (`lane_gate.py <lane-id> [--worktree PATH] [--sha SHA] [--integration PATH]`)
- **Files this lane MAY touch:**
  - `src/sharpit/engine/collectors/vulns/interpreter.py`, `src/sharpit/engine/collectors/vulns/cvss.py`, `src/sharpit/engine/collectors/vulns/service.py`
  - `src/sharpit/engine/mcp.py`
  - `src/sharpit/engine/advisors/rules.py`, `src/sharpit/engine/advisors/report.py`
  - `src/sharpit/engine/collectors/restapi/rules.py`, `src/sharpit/engine/collectors/restapi/service.py`
  - `src/sharpit/engine/tools.py`
  - `tests/fixtures/restapi/rest_api_check_ids.txt`
  - `tests/engine/vulns/test_interpreter.py`, `tests/engine/vulns/test_cvss.py`, `tests/engine/vulns/test_service.py`, `tests/engine/test_mcp.py`, `tests/engine/advisors/test_advisor_rules.py`, `tests/engine/restapi/test_restapi_rules.py`, `tests/engine/restapi/test_restapi_registry.py`, `tests/engine/restapi/test_restapi_report.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_vulns_api.py`, `tests/fastapi/test_mcp_api.py`, `tests/fastapi/test_rest_api_api.py`, `tests/safety/test_d4_safety.py` (new standalone file; `tests/safety/` package is deferred to `F-rest` per R3), `tests/masking/test_d4_masking.py` (new standalone file; `tests/masking/` package is deferred to `F-rest` per R3)
  - `tests/fixtures/bootui/2.2.0/{vulnerabilities,mcp-server,rest-api}/nullable.json` (O2/R9: panel lanes own only `nullable.json`)
  - `.superpowers/sdd/0.4.0/lanes/D4/{handoff.md,findings.md,field-map.md,checklist.md,docs.md}` (O3: any user-facing text goes in `docs.md`)
- **Files this lane MUST NOT touch (spec §10.3, conventions C2/C5, ownership rules O1–O4, and R9):**
  - `src/sharpit/engine/sqla.py` (O1: owned by `A-postgresql`; `F` creates `add_connection_listener`).
  - `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json`), `tests/fixtures/bootui/2.2.0/meta.json`, and `tests/fixtures/bootui/2.2.0/<sharpit-id>/provisional.json` (O2/R9: `G0a`'s worker writes `captured.json` and, on the coordinator's request, `provisional.json`, never the panel lane's worker; panel lanes own only `nullable.json`).
  - `README.md`, `skills/sharpit/SKILL.md`, `examples/fastapi_sqla/`, `tests/test_example_app.py` (O3: write user-facing docs only to `.superpowers/sdd/0.4.0/lanes/D4/docs.md`).
  - `src/sharpit/engine/panels04/*`, `ui/src/lib/panels04/*`, `src/sharpit/engine/panels.py` (`PANELS`), and `ui/src/lib/nav.ts` (O4).
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (unless every touched value strictly decreases or an entry is removed), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants, `uv.lock`, `pyproject.toml`, `guard.py` (`D1`), `capture/*` (`D2`), `pools.py`/`alembic.py`/`health.py`/`threads.py` (`D3`).
  - `tests/test_safety_matrix.py` and `tests/test_masking_corpus.py` (C5: add D4 rows only in `tests/safety/test_d4_safety.py` and `tests/masking/test_d4_masking.py`).
  - `.superpowers/sdd/0.4.0/lanes/*/review.md` and `.superpowers/sdd/0.4.0/lanes/*/gate/*` or `live-verify.md` (C2: written only by the coordinator/reviewer in the integration worktree; `lane_gate.py` refuses lane diffs touching them).

## Definition of Done Coverage (Spec §6.1 — C8 Order)

| # | Spec §6.1 Item (in spec order) | Satisfying Task |
|---|---|---|
| 1 | **Golden parity:** `tests/golden.py::assert_parity` against `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json`, else `provisional.json` marked unverified per O2/R9) + `nullable.json` (owned by D4 per O2/R9), and `field-map.md` | Task 1 (Step 3), Task 2 (Step 3), Task 3 (Step 3) |
| 2 | **Ported tests:** each ported behaviour test cites `# ported: <BootUI class>.<method>` | Task 1 (Step 1), Task 2 (Step 1), Task 3 (Step 1) |
| 3 | **Safety & masking:** `no_side_effects` on every GET/MCP call; panel in `PANELS` with `actionCapable` and `SHARPIT_PANELS_<ID>_ENABLED/_READ_ONLY`; guard chain unchanged; `tests/safety/test_d4_safety.py` & `tests/masking/test_d4_masking.py` | Task 1 (Step 1), Task 2 (Step 1), Task 3 (Step 1) |
| 4 | **Gatekeeper / import boundary:** network access restricted to `osv_client.py` and `epss_client.py` (§6.3); `tests/engine/test_import_boundary.py` green | Task 3 (Step 4) |
| 5 | **Overhead budget:** `N/A — no capture middleware or SQL listener hot path modified; existing overhead budget tests pass` | Task 3 (Step 4) |
| 6 | **MCP read-only:** MCP exposes read tools only (`get_vulnerabilities_report` compacted view, `get_rest_api_report`, `get_rest_api_rule_violations`); scan actions remain POST/CLI-only | Task 1 (Steps 1, 3), Task 2 (Steps 1, 3) |
| 7 | **Svelte 5 view:** `N/A — 2.2.0 DTO/protocol/rule drift lane on existing panels` | N/A |
| 8 | **Four gates + lowest-direct + no-SQLAlchemy:** `ruff check`, `ruff format --check`, `pyright`, `pytest` green in lane worktree; coordinator records `gate/*.log` in integration worktree | Task 3 (Step 4) |
| 9 | **Live check:** coordinator records `live-verify.md` in integration worktree against `examples/fastapi_sqla` | Task 3 (Step 4) |
| 10 | **Handoff:** `.superpowers/sdd/0.4.0/lanes/D4/handoff.md` current (§10.3, recording red commit SHAs per R2) | Task 3 (Step 4) |

## Review Focus

1. **Honest `runtimeReach` & `advisorySymbolSource` when Code Inventory is absent (`src/sharpit/engine/collectors/vulns/service.py:285-337`, `src/sharpit/engine/collectors/vulns/interpreter.py:42-74`)**: Because `code-inventory` is out of scope in 0.4.0 (spec §11), `DependenciesReport["runtimeReach"]` must emit `{"available": False, "unavailableReason": "Code Inventory panel is disabled.", "generation": None, "note": None, "incompleteReason": None}`, `DependencyDto["runtimeReach"]` must be `None`, and `Finding.to_dto()` must emit `"advisorySymbols": []`, `"advisorySymbolSource": "NONE"`, `"runtimeReach": None`. Pinned by `test_vulns_report_emits_2_2_0_runtime_reach_and_advisory_symbol_fields` in **Task 1**.
2. **MCP protocol version negotiation (`2026-07-28` and `2025-06-18` in `src/sharpit/engine/mcp.py:41, 207-336`)**: `McpServer` must advertise `supportedProtocolVersions: ["2026-07-28", "2025-06-18"]` (with `protocolVersion: "2025-06-18"` on `status()`), echo the client's requested version in `initialize` if it is in `SUPPORTED_PROTOCOL_VERSIONS` (falling back to `"2025-06-18"`), accept either version in the `MCP-Protocol-Version` header, and increment `cancellations` on `notifications/cancelled`. Pinned by `test_mcp_negotiates_2026_07_28_and_tracks_cancellations_and_progress_dropped` in **Task 2**.
3. **MCP `get_vulnerabilities_report` compaction (`src/sharpit/engine/tools.py:489-499`, `McpAgentViews.vulnerabilities`)**: Over MCP, `get_vulnerabilities_report` accepts `query` and `limit` (default `10`), filters dependencies to those with `vulnerabilityCount > 0` (unless `query` is provided), caps `advisories` to `5` per dependency (`ADVISORIES_PER_DEPENDENCY = 5`) and list items (`aliases`, `references`, `fixedVersions`) to `3`, and attaches `advisories` and `page` metadata without mutating the cached report. Pinned by `test_mcp_vulnerabilities_compacts_dependencies_and_advisories` in **Task 1**.
4. **Advisor `sampleLocations` and 2.2.0 `rest-api` rule catalog (`src/sharpit/engine/advisors/rules.py:32-66`, `src/sharpit/engine/advisors/report.py:28-66`, `src/sharpit/engine/collectors/restapi/rules.py:34-279, 702-754`, `src/sharpit/engine/collectors/restapi/service.py:53-99, 145-177`, `tests/fixtures/restapi/rest_api_check_ids.txt`, `tests/engine/restapi/test_restapi_registry.py`)**: Every `RuleResult.to_dto()` across all advisor panels must include `"sampleLocations": [...]` (`{"file", "line", "uri"}`), refilled in `advisors/report.py::_mark` alongside `sampleViolations` when `apply_dismissals(report, dismissed, occurrences, dismissed_pairs=...)` filters dismissed occurrences, and `rest-api` must include the 4 new BootUI 2.2.0 rule IDs (`RAPI-RESP-010`, `RAPI-RESP-011`, `RAPI-VALID-006`, `RAPI-VER-007`) in `rules.py`, `tests/fixtures/restapi/rest_api_check_ids.txt`, and `tests/engine/restapi/test_restapi_registry.py` (`PORTED` + severity calibration) while preserving `G1G2`'s `apply_dismissals` (`report.py:28-66`) and `RestApiService._scan` / `_run` (`service.py:83-87, 145-177`) per-finding dismissal matching (R1, R8, R13). Pinned by `test_rest_api_emits_sample_locations_and_2_2_0_rules` in **Task 3**.

---

### Task 1: `vulnerabilities` 2.2.0 DTO Keys, CVSS v4.0 Fallback, and MCP Compaction

**Files:**
- Modify: `src/sharpit/engine/collectors/vulns/interpreter.py:42-74`, `src/sharpit/engine/collectors/vulns/cvss.py:93-120`, `src/sharpit/engine/collectors/vulns/service.py:285-337`, `src/sharpit/engine/tools.py:489-499`
- Test: `tests/engine/vulns/test_interpreter.py`, `tests/engine/vulns/test_cvss.py`, `tests/engine/vulns/test_service.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_vulns_api.py`, `tests/safety/test_d4_safety.py` (new), `tests/masking/test_d4_masking.py` (new)

**Interfaces:**
- Produces in `src/sharpit/engine/collectors/vulns/interpreter.py`: `Finding` fields `advisory_symbols: tuple[str, ...] = ()`, `advisory_symbol_source: str | None = "NONE"`, `runtime_reach: dict[str, Any] | None = None`.
- Produces in `src/sharpit/engine/collectors/vulns/service.py`: `DependenciesReport["runtimeReach"]` (`DependencyRuntimeReachSummaryDto`) and `DependencyDto["runtimeReach"] = None`.
- Produces in `src/sharpit/engine/tools.py`: `VULNERABILITIES_DEFAULT_LIMIT: Final[int] = 10`, `ADVISORIES_PER_DEPENDENCY: Final[int] = 5`, `ADVISORY_LIST_ITEMS: Final[int] = 3`, `_QUERY_LIMIT` schema on `get_vulnerabilities_report`.

- [ ] **Step 1: Write failing tests in `tests/engine/vulns/test_interpreter.py`, `tests/engine/vulns/test_cvss.py`, `tests/engine/vulns/test_service.py`, `tests/engine/test_tools.py`, `tests/safety/test_d4_safety.py`, and `tests/masking/test_d4_masking.py` (C4, R2)**
  - `# ported: VulnerabilityReportServiceTests.includesRuntimeReachAndAdvisorySymbolFields` (`test_vulns_report_emits_2_2_0_runtime_reach_and_advisory_symbol_fields`)
  - `# ported: McpAgentViewsTests.vulnerabilitiesCompactsDependenciesAndAdvisories` (`test_mcp_vulnerabilities_compacts_dependencies_and_advisories`)
  - Safety/masking rows in `tests/safety/test_d4_safety.py` (`no_side_effects` on `GET /sharpit/api/vulnerabilities` and MCP `get_vulnerabilities_report`) and `tests/masking/test_d4_masking.py`.
- [ ] **Step 2: Verify RED and create the `test:` red commit (R2)**
  - Run `uv run pytest -q tests/engine/vulns/test_interpreter.py tests/engine/vulns/test_cvss.py tests/engine/vulns/test_service.py tests/engine/test_tools.py tests/safety/test_d4_safety.py tests/masking/test_d4_masking.py -k "vulns or vulnerabilities"` and confirm each new test fails with `AssertionError` (never `ImportError` or `NotImplementedError`). Commit as `test(vulns): add red tests for 2.2.0 runtimeReach/advisorySymbol DTO keys and MCP compaction` and record the red commit SHA per test in `findings.md` and `handoff.md` (R2).
- [ ] **Step 3: Implement `runtimeReach`, `advisorySymbols`, CVSS v4.0 fallback in `cvss.py`, and MCP `get_vulnerabilities_report` compaction**
- [ ] **Step 4: Run tests and commit** (`feat(vulns): add 2.2.0 runtimeReach/advisorySymbol DTO keys and MCP compaction`).

---

### Task 2: `mcp-server` 2.2.0 Protocol Versions (`2026-07-28`), `cancellations`, and `progressDropped`

**Files:**
- Modify: `src/sharpit/engine/mcp.py:41, 207-336`
- Test: `tests/engine/test_mcp.py`, `tests/fastapi/test_mcp_api.py`

**Interfaces:**
- Produces in `src/sharpit/engine/mcp.py`: `SUPPORTED_PROTOCOL_VERSIONS: Final[tuple[str, ...]] = ("2026-07-28", "2025-06-18")`; `McpServer.status()` keys `"supportedProtocolVersions": list(SUPPORTED_PROTOCOL_VERSIONS)`, `"cancellations": int`, `"progressDropped": int`; handling of `notifications/cancelled` and `_meta.progressToken`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_mcp.py` and `tests/fastapi/test_mcp_api.py` (C4, R2)**
  - `# ported: McpProtocolTests.negotiatesSupportedProtocolVersionsAndTracksCancellations` (`test_mcp_negotiates_2026_07_28_and_tracks_cancellations_and_progress_dropped`)
- [ ] **Step 2: Verify RED and create the `test:` red commit (R2)**
  - Run `uv run pytest -q tests/engine/test_mcp.py tests/fastapi/test_mcp_api.py` and confirm `test_mcp_negotiates_2026_07_28_and_tracks_cancellations_and_progress_dropped` fails with `AssertionError`. Commit as `test(mcp): add red tests for 2026-07-28 protocol negotiation and 2.2.0 status counters` and record the red commit SHA in `findings.md` and `handoff.md` (R2).
- [ ] **Step 3: Implement `SUPPORTED_PROTOCOL_VERSIONS`, header/initialize negotiation, `notifications/cancelled` counter, and `status()` fields**
- [ ] **Step 4: Run `uv run pytest -q tests/engine/test_mcp.py tests/fastapi/test_mcp_api.py` and commit** (`feat(mcp): support 2026-07-28 protocol version and 2.2.0 status counters`).

---

### Task 3: Advisor `sampleLocations` and `rest-api` 2.2.0 Rules (`RAPI-RESP-010/011`, `RAPI-VALID-006`, `RAPI-VER-007`)

**Files:**
- Modify: `src/sharpit/engine/advisors/rules.py:32-66`, `src/sharpit/engine/advisors/report.py:28-66`
- Modify: `src/sharpit/engine/collectors/restapi/rules.py:34-279, 702-754`, `src/sharpit/engine/collectors/restapi/service.py:53-99, 145-177`, `tests/fixtures/restapi/rest_api_check_ids.txt`
- Test: `tests/engine/advisors/test_advisor_rules.py`, `tests/engine/restapi/test_restapi_rules.py`, `tests/engine/restapi/test_restapi_registry.py`, `tests/engine/restapi/test_restapi_report.py`, `tests/fastapi/test_rest_api_api.py`

**Interfaces:**
- Consumes: `tests.golden.assert_parity` (`assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` from `F`, reading `captured.json` or `<name>.captured.json`, else `provisional.json` marked unverified, plus `nullable.json` per O2/R9); `sharpit.engine.advisors.report.apply_dismissals` (`apply_dismissals(report: Mapping[str, Any], dismissed: Collection[str], occurrences: Mapping[str, Sequence[tuple[str, str, str]]] | None = None, dismissed_pairs: Collection[tuple[str, str]] = ()) -> dict[str, Any>`) and `sharpit.engine.collectors.restapi.service._run` (`_run(done: _Evaluation, dismissed: Collection[str], fail_on: Severity, app: str | None, dismissed_pairs: Collection[tuple[str, str]] = ()) -> AdvisorRun`) per R13.
- Produces in `src/sharpit/engine/advisors/rules.py`: `RuleResult.sample_locations: tuple[dict[str, Any], ...] = ()` serialized as `"sampleLocations": list(self.sample_locations)` in `RuleResult.to_dto()`.
- Produces in `src/sharpit/engine/collectors/restapi/rules.py`: `RAPI-RESP-011` (`"Map an empty Optional read to an explicit status"`, `RESPONSES`, `LOW` — evaluates GET handlers returning `T | None` with default 200 status), `RAPI-VER-007` (`"Bodyless handlers must not require a Content-Type"`, `VERSIONING`, `HIGH`), plus `RAPI-RESP-010` and `RAPI-VALID-006` in `SKIPPED_RULES` (`applicable=False` for FastAPI).

- [ ] **Step 1: Write failing tests in `tests/engine/advisors/test_advisor_rules.py`, `tests/engine/restapi/test_restapi_rules.py`, `tests/engine/restapi/test_restapi_registry.py`, and `tests/engine/restapi/test_restapi_report.py` (C4, R2)**
  - `# ported: RestApiAdvisorServiceTests.emitsSampleLocationsAnd220Rules` (`test_rest_api_emits_sample_locations_and_2_2_0_rules`: verifies `sampleLocations` on `RuleResult.to_dto()`, `RAPI-RESP-011` fires on `def get_item() -> Item | None` with 200 status, `RAPI-RESP-010`/`RAPI-VALID-006`/`RAPI-VER-007` are present and registered in `rest_api_check_ids.txt` / `test_restapi_registry.py`, and `assert_parity` passes for `vulnerabilities`, `mcp-server`, and `rest-api`).
- [ ] **Step 2: Verify RED and create the `test:` red commit (R2)**
  - Run `uv run pytest -q tests/engine/advisors/test_advisor_rules.py tests/engine/restapi/test_restapi_rules.py tests/engine/restapi/test_restapi_registry.py tests/engine/restapi/test_restapi_report.py` and confirm `test_rest_api_emits_sample_locations_and_2_2_0_rules` fails with `AssertionError`. Commit as `test(rest-api): add red tests for AdvisorRule sampleLocations and BootUI 2.2.0 RAPI rules` and record the red commit SHA in `findings.md` and `handoff.md` (R2).
- [ ] **Step 3: Implement `sampleLocations` on `RuleResult`, the 4 BootUI 2.2.0 rules in `restapi/rules.py`, and update `tests/fixtures/restapi/rest_api_check_ids.txt` + `tests/engine/restapi/test_restapi_registry.py`**
- [ ] **Step 4: Run verification gates in the lane worktree (`ruff check`, `ruff format --check`, `pyright`, `pytest`), update implementer evidence in `.superpowers/sdd/0.4.0/lanes/D4/` (recording red commit SHAs per R2), and commit** (`feat(rest-api): add AdvisorRule sampleLocations and BootUI 2.2.0 RAPI rules`).

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3, C2, & R2)

**Written by the implementer in the lane worktree (`.superpowers/sdd/0.4.0/lanes/D4/`):**
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `vulnerabilities`, `mcp-server`, and `rest-api` mapped to Python source or `tests/fixtures/bootui/2.2.0/<sharpit-id>/nullable.json`.
- [ ] `findings.md` — `finding → test → red SHA` table; every task red test and review-finding red test records its `test:` red commit SHA (or fix parent SHA for review findings) so `lane_gate.py` replays each named test at its red SHA with `--junitxml` requiring a `<failure>` starting with `AssertionError` and verifies it passes at the lane head (R2).
- [ ] `checklist.md` — Spec §6.1's 10 items in spec §6.1's exact order (1 golden parity … 10 handoff), each with an evidence path or `N/A` + reason.
- [ ] `handoff.md` — Base/head SHA, red commit SHAs per red test (R2), last green command, next step (`ready-for-review`), open findings (`none`).

**Written by the coordinator/reviewer in the integration worktree ONLY (never touched by the lane's diff; `lane_gate.py` refuses it):**
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
- [ ] `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log` and `live-verify.md`.
