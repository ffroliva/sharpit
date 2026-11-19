# Verify my changes

## Goal and entry

Use before and after an application edit, or as the verification stage of another playbook. Establish that the intended
code ran and behavior improved without introducing unexplained work. Load the [shared contract](README.md).
This guide does not authorize further fixes by itself.

## Prerequisites

Inspect the actual diff and user-approved intent. Preserve unrelated work. Record a pre-change baseline when possible:
runtime/revision, relevant request and test data, finding and target identities, measurements, and exact acceptance
assertions. Include the Overview process identity (`startedAt`, active profiles) and record baseline request IDs before
reloading. If the change already happened without a baseline, report that limitation; do not invent one.

## Investigation

| MCP tool | CLI equivalent | Read for |
| --- | --- | --- |
| `get_overview` | `sharpit overview --json` | Application identity, Python version, process start time, and active profiles |
| `get_runtime_insights` | `sharpit insights list --query repeated-selects --json` | Repeated SQL and other runtime observations |
| `get_request_profile` | `sharpit request-profile <id> --json` | Correlated request profile: SQL count, timing, N+1 suspects, and exceptions |
| `get_sql_traces` | `sharpit sql traces --limit 20 --json` | Bounded retained SQL statements for replayed requests |
| `get_agent_status` | `sharpit agent status --json` | Agent sensor status (reports NOT_ATTACHED in this version) |

1. Understand capability differences from BootUI: BootUI provides a Java bytecode agent with runtime impact,
   code inventory, and side-effect diagnostics to track individual method executions and host side effects. sharpit
   ships no bytecode agent or code-inventory sensors in this version; `get_agent_status` reports `NOT_ATTACHED`.
   Verification is grounded in route execution, request profiles, SQL trace counts, advisor rescans, and test suite
   assertions. Never claim method-level bytecode execution was measured.
2. Run focused tests, reload or restart the development server (`fastapi dev` or `uvicorn --reload`), and confirm
   that the running application reflects the code edit. Generate only the authorized traffic reaching the affected
   routes.
3. Replay the agreed request and inspect `get_request_profile`:
   - Confirm the request completed with expected HTTP status and payload.
   - Verify that the statement count for repeated SQL queries decreased.
   - Verify that N+1 suspects identified in the baseline are resolved.
   - Check that no new unexpected SQL queries or exceptions were introduced.
4. sharpit has no previous-run comparison. Re-read evidence after the change: request profile, SQL Trace, and runtime insights for the specific query; state when no comparable baseline exists.
5. For advisor findings (such as Database advisor or FastAPI advisor), run an authorized re-scan (`database_advisor_scan`,
   `fastapi_scan`, or `architecture_scan`) and read the corresponding report (`get_database_advisor_report`,
   `get_fastapi_report`, `get_architecture_report`). Verify that the specific finding identities were resolved in
   the updated scan results.

## Fix and verify

Require agreed functional assertions, intended behavior under the same workload, and no unexplained performance or
error regressions. For advisor findings compare rule ID plus affected target, not score alone. An authorized re-scan
is required to refresh a stale report; a cached report cannot verify a fix.

For latency claims, use the originating playbook's controlled measurement procedure with equivalent warmup and
concurrency. Never claim a performance fix based on a single uncontrolled request. If an unexpected regression appears,
obtain approval before attempting an additional fix.

## Stop and report

Report action status and separate what was proved: tests passed, route was executed, finding was resolved, or
performance criterion was met. Missing baseline, retention buffer rollover, uninstrumented database drivers, or
incompatible runs limit the claim. A change can be partially verified at the route and SQL level without claiming
method-level execution tracking.
