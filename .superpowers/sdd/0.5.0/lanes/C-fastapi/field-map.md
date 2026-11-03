# Field map: `fastapi` (BootUI `spring`, `SpringReport` 2.2.0; WAVE-B §1, §7)

Golden: `tests/fixtures/bootui/2.2.0/fastapi/captured.json` (pre-scan). Shape built by `engine/advisors/scan.py`
(`build_report`); fastapi hooks in `src/sharpit/engine/collectors/fastapi_advisor/report.py` (`_scope`, `_extra`,
`evaluate`).

| BootUI key | sharpit source |
|---|---|
| `localOnly` | core: always `true` |
| `disclaimer` | `report.DISCLAIMER` (BootUI text re-cut for FastAPI: "Bounded FastAPI route and source checks ...") |
| `inspected` | `evaluate`: "Routes: n; handlers analysed: k; source parsed, never executed.", the configuration caveat, "Unevaluated rules ...: k.", then each limitation (BootUI order) |
| `componentsAnalyzed` | number of route handlers analysed (plain functions in the app package) |
| `rulesEvaluated` | core: rules that ran (2 runtime rules without source; 10 with) |
| `violationsFound` | core: violating, undismissed rules |
| `severityCounts[]` | core: occurrences per severity, zeros included |
| `scan.analyzer` | `"sharpit FastAPI Advisor"` (BootUI → sharpit, Spring → FastAPI) |
| `scan.status` | `NOT_SCANNED` before a scan; `SCANNED` after (BootUI: always SCANNED after a successful inspection; completeness in `evidence`) |
| `scan.message` | `NOT_SCANNED_MESSAGE` / "FastAPI Advisor completed against n route handler(s); see unevaluated observations and analysis errors." |
| `scan.scannedAt` | core: epoch ms, `null` before a scan |
| `scan.rulesEvaluated`, `scan.componentsAnalyzed`, `scan.violationsFound` | core: same values as the top level |
| `results[]` | core `RuleResult.to_dto()` (+ `sampleLocations: []`, F5a-core) |
| `analysisErrors` | always `[]`: no rule reports ERROR; a rule without its evidence is not evaluated |
| `evidence.usable` / `coverageComplete` / `limitations` | `evidence(True, not notes, notes)`; notes = resolver reasons, index limitations, skipped handlers |
| `violationDetails.*` | core retention details; `locationNotes: []`, `changes: null` |

No key is `null` where the golden has a non-null value, so no `nullable.json` is needed (not created).
