# Lane D1 field map (BootUI 2.2.0 → sharpit)

Source of truth: `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§1–6 and the BootUI `v2.2.0` sources. No 2.2.0 capture
exists yet under `tests/fixtures/bootui/2.2.0/<id>/` (G0a writes them), so no lane-owned `nullable.json` was needed:
every key below is emitted non-null where BootUI's is non-null. `tests/engine/test_overview.py::test_overview_golden_parity`
runs `assert_parity("overview", ...)` as soon as G0a's fixture lands (skipped until then).

## dismissed-findings (`GET/POST/DELETE {api}/dismissed-findings`)

| BootUI key | Type | sharpit source |
|---|---|---|
| `dismissed` | list | `Findings.to_dto` (`src/sharpit/engine/advisors/dismissals.py`) |
| `dismissed[].ruleId` | str | `DismissedFinding.rule_id` |
| `dismissed[].identity` | str | `DismissedFinding.identity` |
| `dismissed[].note` | str\|null | `DismissedFinding.note` (null when none; GET only, no MCP/CLI binding) |
| `ignored` | int | `len(_Contents.ignored)` |
| 400 `error` | str | `INVALID_BODY` (`src/sharpit/fastapi/routes/dismissed_findings.py`) and the store's `AdvisorViolationError` messages |
| 409 `error` | str | `dismiss_finding` at `MAX_FINDINGS` |

## overview (`GET {api}/overview`, MCP `get_overview`)

| BootUI key | sharpit source |
|---|---|
| `bootUiVersion` … `openApiUrl` (15 keys) | unchanged since 0.3.0 (`src/sharpit/engine/collectors/overview.py`); MVP golden in `tests/engine/test_overview.py` |
| `run.instanceId` | `SharpitContext.instance_id` = module `_INSTANCE_ID` (`secrets.token_hex(4)`, once per process) |
| `run.runId` | `SharpitContext.run_id` (`secrets.token_hex(4)` per context) |
| `run.ordinal` | `SharpitContext.run_ordinal` (`itertools.count(1)` per process) |
| `run.startedAt` | `SharpitContext.started_at_ms` (epoch ms at context creation) |
| panel title `Scorecard` | `PANELS` row in `src/sharpit/engine/panels.py` |

## config, mappings, loggers, beans, cli

Contract §§3–6: no endpoint or DTO drift in 2.2.0 (100% similarity); the HTTP payloads are unchanged and stay covered
by `tests/test_conformance.py`. MCP/CLI projection only:

| Tool | 2.2.0 behaviour | sharpit |
|---|---|---|
| `get_config` | `McpAgentViews.config`: `propertySuggestions` → `[]`, every other key kept | `src/sharpit/engine/tools.py` handler (key still emitted, empty) |
| `get_config`, `get_beans` | default `limit` 25 (`INVENTORY_DEFAULT_LIMIT`) when the call has none | **not done here**: needs `src/sharpit/engine/tool_dispatch.py` (outside May-touch); see `handoff.md` |
| `get_mappings`, `get_loggers`, `cli` | unchanged | unchanged |
