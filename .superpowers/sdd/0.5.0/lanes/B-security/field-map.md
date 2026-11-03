# Field map: BootUI `security` -> sharpit `security` (contract WAVE-B §1, §2)

Golden: `tests/fixtures/bootui/2.2.0/security/captured.json` (pre-scan; `test_report_golden_parity`). Post-scan golden
absent (G0): `test_post_scan_golden_parity` skips with `post-scan golden absent (G0)`. No `nullable.json`: every key is
filled.

| BootUI key | sharpit source |
|---|---|
| `localOnly` | always `true` (shared advisor core) |
| `disclaimer` | verbatim with "Spring Security" -> "FastAPI security", "filter chains" -> "middleware stacks" |
| `filterChains[]` | one matcher per ASGI middleware stack of `SecurityModel.chains` (`"any request"`, `"<prefix>/**"`) |
| `filterChainsAnalyzed` | `len(SecurityModel.chains)` at the last scan, 0 before |
| `rulesEvaluated` | rules that ran (27 registered; source rules skip without an app package) |
| `violationsFound` | violating rules after dismissals (`advisors/scan.py`) |
| `severityCounts[]` | five severities, dismissed rules excluded (`advisors/report.py`) |
| `scan` | `{analyzer: "sharpit FastAPI Security Advisor", status: NOT_SCANNED/DISABLED/SCANNED/PARTIAL, message, scannedAt, rulesEvaluated, filterChainsAnalyzed, violationsFound}` |
| `results[]` | `RuleResult` DTOs of violating rules (`id`, `name`, `category`, `severity`, `description`, `status`, `violationCount`, `sampleViolations`, `recommendation`, `learnMoreUrl`, `dismissed`) |
| `analysisErrors[]` | a rule that raised: `status: "ERROR"` row, message masked |
| `evidence` | `{usable, coverageComplete, limitations}`; limitations name unobserved mounts and the source-scan reason |
| `violationDetails` | `{scanId, total, retained, retentionLimit, truncated}` (shared retention) |
| `GET rules/{id}/violations` | shared page DTO: `scanId`, `ruleId`, `violationCount`, `retainedCount`, `truncated`, `violations`, `fingerprints`, `page` |
