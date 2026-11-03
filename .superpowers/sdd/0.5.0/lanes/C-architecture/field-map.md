# Field map: `ArchitectureReport` (`GET /sharpit/api/architecture`, `POST /sharpit/api/architecture/scan`)

Source: `src/sharpit/engine/collectors/architecture/report.py` over `ArchitectureService` and the shared advisor scan core.
Contract: `BOOTUI-CONTRACT-0.4-WAVE-B.md` §1, §6; golden `tests/fixtures/bootui/2.2.0/architecture/captured.json`.

| Key | Source / value |
|---|---|
| localOnly | `true`: always local-only |
| disclaimer | `ArchitectureService.spec.disclaimer` |
| basePackages | detected top-level application packages from `appsource.resolve_package_root` |
| classesAnalyzed | module count analyzed in the application package |
| rulesEvaluated | rule definitions count evaluated in the scan |
| violationsFound | count of distinct active rules with `status == "VIOLATION"` |
| severityCounts | count of occurrences per severity level (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`) |
| scan.analyzer | `"BootUI ArchUnit hygiene"` |
| scan.status | `NOT_SCANNED` \| `SCANNED` \| `PARTIAL` \| `ERROR` \| `DISABLED` |
| scan.message | scan completion or status message |
| scan.scannedAt | epoch timestamp ms when scan completed; `null` before scan (`nullable.json`) |
| scan.rulesEvaluated | rule count evaluated in the scan |
| scan.classesAnalyzed | module count analyzed in the scan |
| scan.violationsFound | count of active violating rules |
| results[].id | rule identifier (e.g. `ARCH-PKG-001`) |
| results[].name | rule title |
| results[].category | rule category (`Package structure`, `Coding practices`, `Layering`) |
| results[].severity | severity enum (`HIGH`, `MEDIUM`, `LOW`, `INFO`) |
| results[].description | rule description |
| results[].status | rule status (`VIOLATION`, `PASS`, `SKIPPED`, `ERROR`) |
| results[].violationCount | occurrences count for this rule |
| results[].sampleViolations | up to 10 sample violation message strings |
| results[].recommendation | rule remediation guidance |
| results[].learnMoreUrl | reference link |
| results[].dismissed | whether the rule has been dismissed |
| results[].sampleLocations | violation file locations `{path, line}` |
| analysisErrors | rule results with status `ERROR`, sorted by id |
| evidence.usable | boolean usability flag |
| evidence.coverageComplete | boolean completeness flag |
| evidence.limitations | sanitized limitation strings |
| violationDetails.scanId | scan run UUID string; `null` before scan (`nullable.json`) |
| violationDetails.total | total violations count across all rules |
| violationDetails.retained | count of violations retained within memory limits |
| violationDetails.retentionLimit | max retention limit |
| violationDetails.truncated | boolean whether retention truncated |
| violationDetails.locationNotes | location notes list |
| violationDetails.changes | baseline changes object; `null` when untracked (`nullable.json`) |
