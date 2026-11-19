# Lane A1: Incomplete-Evidence Counters and 2.4.0 Tool Descriptions (BootUI 2.4.0 #1589)

## Goal

Port the BootUI 2.4.0 incomplete-evidence counters and tool description enhancements to sharpit:
1. `insufficient` and `partial` counters in the caught-exceptions report (`CaughtExceptionsReport`, zeros in sharpit: `PLAN.md` Decision 5).
2. `insufficient` and `partial` report-wide counters in `RuntimeInsightsAgentReportDto`, covering every observation matching the query, including rows omitted by `limit`.
3. Tool descriptions for `get_exceptions`, `get_runtime_insights`, and `get_runtime_insight` adopting BootUI 2.4.0 sentences in sharpit phrasing without forbidden strings.
4. Parity tracking: move the three adopted tools from `DESCRIPTION_GAPS` to `DESCRIPTION_ADOPTED` in `tests/parity/test_tools_parity.py`, and record the matrix fragment in `docs/reference/matrix-updates/a1-counters.tsv`.

## Tool Description Ownership

BootUI 2.4.0 changed descriptions for six tools (`docs/reference/BOOTUI-2.4.0-DELTA.md`, `PLAN.md` Track A):
- **Lane A1 (this lane):** owns `get_exceptions`, `get_runtime_insights`, and `get_runtime_insight` (incomplete-evidence counters, explicit observation status, and truthful sensor-absent state).
- **Lane A2:** owns `get_transactions` (`propagation` values `NEW`, `REQUIRES_NEW`, `NESTED`, `UNKNOWN`).
- **Lane A3:** owns `get_security_report` (static-only report) and `security_scan` (static analyzer declarations).

## Production Paths Changed

- `src/sharpit/engine/capture/exceptions.py:caught_report`: add `insufficient: 0` and `partial: 0` after `findings` and before `rows`.
- `src/sharpit/engine/tools.py:exceptions_report`: keeps `caughtInCode: None` when sensor is absent, matching BootUI's `ExceptionsReport` behaviour.
- `src/sharpit/engine/collectors/insights/agent_view.py:agent_list` and `_list`: compute `insufficient` and `partial` counts across all matching observations (including those cut by `limit`), and append them last in the report dictionary; emit zeros in the unavailable branch.
- `src/sharpit/engine/tools04/runtime_insights.py:TOOLS`: adopt 2.4.0 description sentences for `get_runtime_insights` and `get_runtime_insight`.
- `src/sharpit/engine/tools.py:TOOLS`: adopt 2.4.0 description sentence for `get_exceptions`.
- `tests/parity/test_tools_parity.py`: move `get_exceptions`, `get_runtime_insights`, and `get_runtime_insight` from `DESCRIPTION_GAPS` to `DESCRIPTION_ADOPTED`.

## Scenarios

| Scenario | Expected Behaviour |
|---|---|
| Incomplete-evidence counters in `CaughtExceptionsReport` | `caught_report()` in `src/sharpit/engine/capture/exceptions.py` emits `insufficient: 0` and `partial: 0` after `findings` and before `rows`. `caughtInCode` in `store.report()` and `get_exceptions` remains `None` (`null` in JSON) when the sensor is absent, matching BootUI without an agent sensor. |
| Incomplete-evidence counters in `RuntimeInsightsAgentReportDto` | `agent_list` in `src/sharpit/engine/collectors/insights/agent_view.py` counts observations matching `query` where `status == "INSUFFICIENT"` or `status == "PARTIAL"` across all matching rows, including those omitted by `limit`. Emits `insufficient: int` and `partial: int` appended last in the report dictionary. Returns zeros when the report is unavailable. |
| 2.4.0 MCP tool description sentences | `get_runtime_insights` adds the sentence explaining that `insufficient` and `partial` counts cover all matching rows including limit omissions. `get_runtime_insight` adds the sentence stating observation status is explicit and incomplete evidence is not clean. `get_exceptions` explains that `caughtInCode` is null without an agent sensor, `insufficient` and `partial` are evidence states, and `clear_exceptions` is CLI-only (refused over MCP). |
| Parity tracking and matrix updates | In `tests/parity/test_tools_parity.py`, `get_exceptions`, `get_runtime_insights`, and `get_runtime_insight` move from `DESCRIPTION_GAPS` to `DESCRIPTION_ADOPTED`, and `get_runtime_insights` / `get_runtime_insight` move to `MATCHED_TOOLS`. Matrix updates are recorded in `docs/reference/matrix-updates/a1-counters.tsv` and `w0-pin-24.tsv`. |

## Tasks

- [x] **Step 0:** Create plan and scenario documentation in `A1-counters.md`.
- [x] **Step 1:** Red tests for `CaughtExceptionsReport` `insufficient` and `partial` fields, and `caughtInCode` parity.
- [x] **Step 2:** Implement `insufficient: 0` and `partial: 0` in `caught_report()` (`src/sharpit/engine/capture/exceptions.py`).
- [x] **Step 3:** Red tests for `RuntimeInsightsAgentReportDto` `insufficient` and `partial` counters across all matching rows including limit omissions and in unavailable reports.
- [x] **Step 4:** Implement `insufficient` and `partial` counters in `agent_list` and `_list` (`src/sharpit/engine/collectors/insights/agent_view.py`).
- [x] **Step 5:** Red tests for adopted 2.4.0 tool description sentences and moving the three tools into `DESCRIPTION_ADOPTED` in `tests/parity/test_tools_parity.py`.
- [x] **Step 6:** Update tool descriptions in `src/sharpit/engine/tools04/runtime_insights.py` and `src/sharpit/engine/tools.py`.
- [x] **Step 7:** Record matrix update rows in `docs/reference/matrix-updates/a1-counters.tsv`, update `A1-counters.md` checkboxes, and run full lane gates and verify.
- [x] **Step 8 (Fix Round 1):** Parity tracking consistency (MATCHED_TOOLS pin 38), accurate test citations, port real counter case and E2E MCP/CLI conformance assertions, truthful `get_exceptions` description, single-pass Counter in `_list`, docs/matrix gaps for CaughtExceptionsSummaryDto/CaughtExceptionRowDto, generic adoption test check, and tool description ownership documentation.

