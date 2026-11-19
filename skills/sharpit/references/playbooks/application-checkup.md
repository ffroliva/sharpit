# Application checkup

## Goal and entry

Use when the user asks "what should I fix first?" or wants a general application assessment. Triage into one focused
investigation rather than scanning every panel. Load the [shared contract](README.md) before collecting evidence.

## Prerequisites

Confirm the user's goal (otherwise general application health), application/repository identity, catalog, permissions,
and collection budget. Source code and representative traffic are needed to turn runtime findings into verified fixes.
Do not assume dependency upgrades or major framework refactors are the goal.

## Investigation

Start with existing evidence and permitted low-impact reads. `get_health` invokes live health indicators, which may
query databases or contact external services. Prefer a supplied prior health result; if indicator behavior is unknown
or its external work is outside the authorized scope, obtain approval before calling it. It is not a cached report.

| MCP tool | CLI equivalent | Read for |
| --- | --- | --- |
| `get_overview` | `sharpit overview --json` | Application identity, Python version, FastAPI runtime, and activation status |
| `get_health` | `sharpit health --json` | Live component checks, only within scope; distinguish intentionally absent local services |
| `get_runtime_insights` | `sharpit insights list --json` | Coverage, checks not run, limitations, observations, and suggested next calls |
| `get_architecture_report` | `sharpit architecture report --json` | Existing architecture structure findings |
| `get_fastapi_report` | `sharpit fastapi report --json` | FastAPI application advisor (routes, dependencies, middleware) |
| `get_database_advisor_report` | `sharpit db report --json` | Existing database/SQL advisor findings when available |

1. Select relevant cached reports from the catalog; do not call all of them. Inspect report timestamps,
   `evidence.usable`, `evidence.coverageComplete`, limitations, and scan status. Missing reports are not clean reports.
2. Read Runtime Insights coverage before observations. `requests` counts completed HTTP exchanges, not every background
   task or event-loop worker. Follow non-HTTP evidence and eviction caveats. An idle application needs an approved
   representative workload.
3. If the default observations do not explain the symptom, use query `all`, a route, or a named kind. The default list
   omits kinds including repeated SELECTs; a missing default row is not proof of absence.
4. Rank a few candidates by impact on the goal and confidence, checking source/configuration and dismissed findings.
   An unavailable capability is a coverage gap, not an installation defect to work around.
5. Hand off conditionally, preserving budget, authorization, and baseline:

| Evidence | Follow |
| --- | --- |
| Repeated SQL, transaction symptoms, database findings | [Database efficiency](database-efficiency.md) |
| One reproducibly slow route | [Slow endpoint](slow-endpoint.md) |
| Exceptions or an error behind a successful response | [Errors and hidden failures](errors-and-hidden-failures.md) |
| Memory growth, thread contention, or event loop stalls | [Python performance and memory](python-performance-and-memory.md) |

Name any proposed fresh scans (`architecture_scan`, `fastapi_scan`, `database_advisor_scan`, `security_scan`,
`vulnerabilities_scan`) and obtain the required approval first. Do not run memory, security, vulnerability, or
database metadata actions as an implicit "check everything" step.

## Fix and verify

Produce the shared Context/Coverage/Actions/Approval plan. Distinguish confirmed fixes, investigations, and optional
improvements. In review-first mode stop here. Under explicit bounded delegation, execute only covered actions through
the focused guide, then [verify the changes](verify-my-changes.md). A higher score alone is not acceptance criteria.

## Stop and report

Stop if identity or source code is unknown, traffic is insufficient, the budget expires, or a focused branch requires
new permission. Report the highest-impact supported actions and coverage gaps, not "healthy" because cached reports
are empty. An intentionally absent database or unconfigured advisor is a documented status, not a failed check.
