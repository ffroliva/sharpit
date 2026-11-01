# Deviations from BootUI

sharpit follows BootUI's JSON contract and keeps its guard and masking rules, with deliberate differences (a stricter
cross-site check, Python-specific activation, a new UI, deferred features). The original design logs are in
the [MVP design spec](https://github.com/ffroliva/sharpit/blob/main/docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md)
and the [0.2.0 design spec](https://github.com/ffroliva/sharpit/blob/main/docs/superpowers/specs/2026-10-31-sharpit-0.2.0-design.md).

## 0.3.0 deviations

| BootUI | sharpit | Reason |
|---|---|---|
| One JDBC choke point (proxy `DataSource`) | **one SQL source per driver** (SQLAlchemy class events; a `sqlite3.connect` swap), feeding one recorder through `engine/sources/dispatch.py`; SQLite through SQLAlchemy is counted by the SQLAlchemy source only | Python has no common driver layer; the swap is the only patch point for the immutable `sqlite3.Connection` |
| `bootui <panel> scan --json`, one typed report per panel, exit codes 0/1/2/3 | `pytest --sharpit` writes one `sharpit-report/1` JSON for the whole run; pytest's exit codes, with a gate failure raising 0 to 1 | test-time use; a single report a CI job can read |
| Rule-based reports call the list `results`, pentesting calls it `findings` | panel DTOs keep `results` (parity); the report has one flat `findings` list with a common shape | #18: one name, one shape |
| Dismissal per rule id, plus per vulnerability+package (`id::package`) in the same `dismissedRules:` list | the same list, which now also accepts a finding fingerprint (`<advisor>:<rule>:<hash>`) for any advisor | BootUI's per-vulnerability dismissal, generalised to every advisor |
| `AdvisorEvidenceDto` plus panel-specific statuses (`PARTIAL`) | the same evidence, plus a derived `PASSED`/`FAILED`/`UNKNOWN` per advisor run, `unknown` failing a CI run by default | "unknown, not pass" |
| BootUI's CI recipe (`CLI.md`) treats a disabled or read-only panel (exit 2) as a skip | in `pytest --sharpit`, an advisor that could not assess makes the run `unknown`, which fails unless `--sharpit-allow-unknown` | a gate the user turned on must not pass on missing evidence |
| `severityCounts` per panel | the same form and `SeverityOrder.DEFAULT`, over all non-dismissed findings of the run | a BootUI `jq` gate still works |
| N+1 groups on whitespace-collapsed SQL with literals kept, case-sensitive (`SqlTraceGrouping`, deliberately not the normaliser) | groups on the 0.2.0 normalised key (literals folded, `IN` lists collapsed, case ignored), in the console (0.2.0) and the gate | literals are values and must be masked; `id=41` and `id=42` are the same N+1 |
| SQL trace records every statement, PRAGMA and schema reads included; only BootUI's own queries suppressed | the same in the console; the **test-session sink only** filters PRAGMA, schema-table reads, migration tables (`alembic_version`, `schema_migrations`, ...) and transaction control from gating (counted, listed) | each SQLite connection runs PRAGMAs and migration checks that would trip per-test budgets |
| JDBC batch recorded once, classified by its first statement | `executemany` and `executescript` recorded once each, category from the first statement, no new category | the same rule for the Python batch calls |
| Exception group fingerprint, triage per group | the gate's exception finding target = nodeid + the 0.2.0 group fingerprint | one finding per distinct exception per test |
| Exit code 3 "reserved for a future severity threshold" | `--sharpit-fail-on=SEV` (default `HIGH`) | the threshold BootUI reserved |
| No test-time capture | test-id contextvar, unattributed bucket, phase split, xdist merge | sharpit-only feature (#6) |
| Settings are Spring properties | plugin options are pytest options (CLI > ini); shared settings stay `SHARPIT_*` | a pytest plugin is configured the pytest way |
| (none) | `SHARPIT_SQL_TRACE_SQLITE3_ENABLED` | no sqlite3 in Java |
| A dismissed rule is marked `dismissed`; a dismissed vulnerability key removes that occurrence | a dismissed fingerprint removes that occurrence from its rule's `violationCount`, `sampleViolations` and `severityCounts`; a rule with every occurrence dismissed stays `dismissed: false` with `violationCount` 0 (only a dismissed rule id marks it `dismissed: true`) | the per-vulnerability behaviour, applied to every advisor |
| `AdvisorRuleViolationsDto` has `violations` only | a REST API violations page also carries `fingerprints`, parallel to `violations` (same window); retention without fingerprints omits the key | the console UI dismisses one finding by fingerprint (§5.6) |
| `SecretValueDetector` patterns (JWT, PEM, AWS, URL userinfo, ...) | the same plus vendor token prefixes (§9 A4) | positional SQL parameters have no key name to mask by |
| Report output follows the console's exposure setting (no BootUI equivalent) | report writers always use the default `MASKED` policy and warn when the env asks for more | a report leaves the machine as a CI artifact |
| (none) | `tests[].findings` of a non-deciding rerun attempt may reference fingerprints absent from the flat `findings` list | only the last attempt decides; earlier attempts are history |
