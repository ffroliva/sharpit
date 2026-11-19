# AI agents

sharpit can expose its advisor findings and runtime diagnostics to a local AI coding agent, so the agent can consult
your running FastAPI application before proposing a fix and verify the fix afterwards. It works with any client that
speaks the [Model Context Protocol](https://modelcontextprotocol.io) (MCP) or runs shell commands through the CLI.

This page covers choosing between the MCP server and the command-line client (CLI), installing the agent skill,
installing the plugin (`plugins/sharpit`), the improvement playbooks, connecting an agent to the MCP server, and
runtime investigation recipes.

## Why use sharpit from an agent

An agent reading source code can only guess at runtime behavior. sharpit provides machine-readable context from the
running application:

- **Advisor scans** — architecture, REST API, FastAPI, database, security, and package vulnerabilities. The agent
  receives prioritized, severity-ranked findings with rule IDs and remediation hints.
- **Runtime diagnostics** — a correlated live activity feed (recent HTTP requests, SQL statements, and exceptions
  grouped by request ID), full exception detail (tracebacks, cause chain, occurrences), SQL traces with execution
  timings, distributed traces, log tail, HTTP exchanges, and thread/asyncio event-loop task inspection.
- **Core context** — application overview, health, effective configuration (secrets masked), FastAPI beans (dependencies
  and lifespan), and request mappings.

Every tool reuses the same services and immutable DTO contracts as the browser console, returning masked, bounded
evidence rather than raw internals.

## MCP server or CLI?

Both surfaces give the agent identical data: the same tool registry, the same panel policy, and the same masked DTOs.
The CLI can neither offer a diagnostic the MCP server lacks nor miss one it has, because its command tree is generated
from the tool catalog.

Use the [MCP server](#connect-an-agent-to-the-sharpit-mcp-server) when your agent or IDE speaks MCP natively. The agent
discovers tools, schemas, and descriptions automatically and calls them as native tool calls, with no shell commands
or JSON parsing glue.

Use the command-line client (`sharpit`) when the agent's host can only run shell commands: a sandboxed
agent with no MCP wiring, a CI job, or a terminal session. The agent skill falls back to `sharpit` commands whenever its
host does not expose sharpit's MCP tools.

Every tool in the catalog is also a `sharpit` command:

| Diagnostic | MCP tool | CLI command |
| --- | --- | --- |
| Application overview | `get_overview` | `sharpit overview --json` |
| Health tree | `get_health` | `sharpit health --json` |
| Live activity | `get_live_activity` | `sharpit activity --json` |
| Request profile | `get_request_profile` | `sharpit request-profile <id> --json` |
| Runtime insights | `get_runtime_insights` | `sharpit insights list --json` |
| Database advisor | `get_database_advisor_report` | `sharpit db report --json` |
| FastAPI advisor | `get_fastapi_report` | `sharpit fastapi report --json` |
| Architecture advisor | `get_architecture_report` | `sharpit architecture report --json` |
| Exceptions list | `get_exceptions` | `sharpit exceptions list --json` |
| Exception detail | `get_exception_detail` | `sharpit exceptions show <id> --json` |
| SQL traces | `get_sql_traces` | `sharpit sql traces --json` |
| Threads and tasks | `get_threads` | `sharpit threads --json` |
| Log tail | `get_log_tail` | `sharpit logs tail --json` |

## Install the sharpit agent skill

sharpit ships an agent skill that teaches coding agents how to inspect a running application from the command line or
MCP server, turn advisor findings into focused fixes, and verify those fixes.

Install the canonical skill in any compatible coding agent:

```bash
npx skills add https://github.com/ffroliva/sharpit/tree/main/skills/sharpit
```

The skill is also available locally under `skills/sharpit/` in the repository.

## Install the sharpit plugin

sharpit provides an agent plugin under `plugins/sharpit/` adhering to the Agent Plugins 1.0.0 specification:

- **Claude Code:** configured via `.claude-plugin/` and registered through the marketplace manifest at
  `.claude-plugin/marketplace.json`.
- **Cursor:** configured via `plugin.json` and registered through `.cursor-plugin/marketplace.json`.
- **Codex:** configured through `.agents/plugins/marketplace.json`.

The plugin configures the MCP endpoint at `http://127.0.0.1:8000/sharpit/api/mcp` and installs the `sharpit` skill.

## Application-improvement playbooks

For structured, hypothesis-driven investigations, sharpit provides six agent playbooks under
`skills/sharpit/references/playbooks/`. Each playbook follows a shared contract: declare a diagnostic budget, obtain
explicit user approval before running scans or mutations, collect baseline evidence, apply a focused fix, and verify
at runtime before reporting completion.

| Goal | Playbook |
| --- | --- |
| Assess the application; identify highest-impact fixes | [`application-checkup.md`](https://github.com/ffroliva/sharpit/blob/main/skills/sharpit/references/playbooks/application-checkup.md) |
| Reduce SQL queries, resolve N+1 patterns, check transactions | [`database-efficiency.md`](https://github.com/ffroliva/sharpit/blob/main/skills/sharpit/references/playbooks/database-efficiency.md) |
| Diagnose a slow route and separate database from handler time | [`slow-endpoint.md`](https://github.com/ffroliva/sharpit/blob/main/skills/sharpit/references/playbooks/slow-endpoint.md) |
| Investigate exceptions, 500 status codes, or hidden failures | [`errors-and-hidden-failures.md`](https://github.com/ffroliva/sharpit/blob/main/skills/sharpit/references/playbooks/errors-and-hidden-failures.md) |
| Confirm changed code ran and verified behavior improved | [`verify-my-changes.md`](https://github.com/ffroliva/sharpit/blob/main/skills/sharpit/references/playbooks/verify-my-changes.md) |
| Diagnose Python CPU, memory, thread exhaustion, or event-loop stalls | [`python-performance-and-memory.md`](https://github.com/ffroliva/sharpit/blob/main/skills/sharpit/references/playbooks/python-performance-and-memory.md) |

Load only the single playbook matching the immediate task.

## Connect an agent to the sharpit MCP server

The MCP server is disabled by default. Enable it by setting:

```bash
export SHARPIT_MCP_ENABLED=ON
```

or by toggling the switch in the web console under the MCP Server panel.

Configure your client to connect via HTTP to `/sharpit/api/mcp` on the application's port:

```json
{
  "mcpServers": {
    "sharpit": {
      "type": "http",
      "url": "http://127.0.0.1:8000/sharpit/api/mcp"
    }
  }
}
```

Verify that the endpoint responds:

```bash
curl -fsS http://127.0.0.1:8000/sharpit/api/mcp-server
```

### Low-footprint mode

When the application is placed in low-footprint mode (`sharpit low-footprint enable` or `enable_low_footprint`),
in-memory recording buffers are cleared to conserve memory. Diagnostic reads return paused evidence; only resume actions return 409. To resume collection, call `disable_low_footprint` (`sharpit low-footprint disable`).

### Investigate one request

To diagnose a specific request:

1. Query `get_live_activity` (`sharpit activity --query "<route>" --limit 20 --json`) to find recent requests matching
   the route.
2. Select the `requestId` of interest.
3. Call `get_request_profile` (`sharpit request-profile <id> --json`) using that exact request ID.
4. The profile returns the request URL, method, status code, total duration, time spent in SQL, executed SQL statements
   grouped by fingerprint, N+1 query suspects, and any correlated exceptions.

### Runtime Insights for agents

Runtime Insights evaluates background heuristics across recent traffic:

1. Call `get_runtime_insights` (`sharpit insights list --json`) to inspect high-confidence observations, evaluated
   insight kinds, and coverage statistics.
2. Use `--query all` (`sharpit insights list --query all --json`) to view all evaluated findings, including repeated
   SELECTs that are omitted from the default view.
3. Call `get_runtime_insight` (`sharpit insights show <id> --json`) with a specific observation ID to retrieve detailed
   evidence, affected route patterns, and suggested diagnostic tools.

### Did my change run?

After editing source code and reloading the development application (`fastapi dev` or `uvicorn --reload`):

1. Note on bytecode agent differences: BootUI provides a Java bytecode agent with code inventory and method
   probes. sharpit ships no Python bytecode profiler or code-path sensors in this version (`get_agent_status` reports
   `NOT_ATTACHED`).
2. Verify execution at the route level: replay the target request and inspect `get_request_profile` (`sharpit request-profile <id> --json`).
3. sharpit has no previous-run comparison. Re-read the request profile, SQL Trace, and runtime insights for the specific query after the change.
4. Run an authorized re-scan (`sharpit db scan` (CLI only, after the user's approval), `sharpit fastapi scan` (CLI only, after the user's approval), or `sharpit architecture scan` (CLI only, after the user's approval)) and verify that targeted
   violation IDs were resolved in the updated report.

### Where does the handler's time go?

To break down latency for a slow endpoint:

1. Call `get_request_profile` (`sharpit request-profile <id> --json`) for the request. Inspect `durationMs` and
   `sqlDurationMs`.
2. If `sqlDurationMs` represents most of the duration, the bottleneck is in database operations. Use
   `database-efficiency.md` to identify N+1 queries, unindexed filters, or missing eager loading.
3. If handler time (total duration minus SQL duration) dominates:
   - Check `get_threads` (`sharpit threads --json`) to inspect Python OS thread states and active asyncio event-loop
     tasks.
   - Synchronous blocking calls (such as `time.sleep()`, synchronous network clients, or CPU-bound processing) inside
     `async def` route handlers freeze the event loop for all concurrent connections.
   - Synchronous `def` handlers run in an AnyIO worker thread pool; check whether worker threads are saturated.

### Reading retained advisor violations

Advisor scans provide rule-level summaries and sample violations. To inspect all retained violations for a specific rule:

1. Obtain the `scanId` from the advisor report (e.g., `get_database_advisor_report` or `get_fastapi_report`).
2. Call the corresponding rule violations tool:
   - `get_database_advisor_rule_violations` (`sharpit db violations <id> --scan-id <scan-id> --json`)
   - `get_fastapi_rule_violations` (`sharpit fastapi violations <id> --scan-id <scan-id> --json`)
   - `get_architecture_rule_violations` (`sharpit architecture violations <id> --scan-id <scan-id> --json`)
   - `get_rest_api_rule_violations` (`sharpit rest-api violations <id> --scan-id <scan-id> --json`)
   - `get_security_rule_violations` (`sharpit security violations <id> --scan-id <scan-id> --json`)
3. Pass `id` (the rule identifier, e.g. `DB-SCHEMA-002`), `scanId`, and optional `offset` and `limit`; only `*_violations` tools accept `offset`.
4. Inspect the retained page fields `ruleId`, `scanId`, `violations`, `total`, `retained`, and `truncated`; this response does not contain source locations.

### Checking what a fix changed

After applying a code modification:

1. Run an authorized advisor re-scan: `sharpit db scan` (CLI only, after the user's approval), `sharpit fastapi scan` (CLI only, after the user's approval), or `sharpit architecture scan` (CLI only, after the user's approval).
2. Inspect the report summary and `results`: compare `violationCount` and verify that the specific finding was resolved.
3. Check `sharpit.yml` dismissals: dismissed findings are marked as suppressed and are not counted in active totals,
   but remain preserved in detail listings.

### Reading a bounded result

All collection tools return bounded, paginated results to protect memory and agent context windows:

- Only `*_violations` tools accept `offset`; other bounded reads use `limit`. Default limits include 8 for insights and 25 for metrics.
- Check `page.hasMore` in the response envelope. If `true`, advance `offset` by `page.returned` to retrieve the next
  slice.
- Never assume an initial page contains the full dataset.

### Unknown ids and unavailable capabilities

When querying entities by identifier:

- Nonexistent request IDs, exception IDs, or scan IDs return HTTP 404 or an MCP in-band error (`isError: true`).
- An unconfigured advisor or disabled panel returns an error prefixed with `Tool not available in this application:`.
- Treat unavailable capabilities as documented coverage limitations, not as application errors.

### Agent-sized defaults

sharpit applies conservative defaults designed for automated tools:

- Default page limits range from 20 to 100 entries.
- Payloads omit raw internals and excessive metadata.
- Text fields containing potential secrets (passwords, bearer tokens, private keys) are masked before output.

### Safety model

sharpit enforces strict boundaries to ensure safety in development environments:

- **Fails closed:** sharpit is disabled unless an explicit dev signal is detected (`fastapi dev`, `uvicorn --reload`, or
  a development profile). In production environments, all endpoints return 404.
- **Loopback only:** Remote connections are rejected by default. Allowing remote callers requires setting
  `SHARPIT_ALLOW_NON_LOCALHOST=true` and presenting a valid bearer token.
- **Read-only vs. Action tools:** Read tools have no side effects on the host. Action tools (such as
  `sharpit db scan` (CLI only, after the user's approval), `sharpit fastapi scan` (CLI only, after the user's approval), `sharpit architecture scan` (CLI only, after the user's approval), `sharpit security scan` (CLI only, after the user's approval), and `sharpit vulnerabilities scan` (CLI only, after the user's approval)) require
  writable permissions (`SHARPIT_READ_ONLY=false`) and explicit user approval before execution.
- **Secret masking:** Sensitive values in configuration, request headers, query parameters, SQL literals, and logs are
  masked unless explicitly configured otherwise (`SHARPIT_EXPOSE_VALUES=FULL`, which generates a startup warning).

## Assess an application and approve an action plan

The MCP server advertises an `assess_application` prompt (see the prompt for its current tool list) that coordinates a review-first evaluation:

1. **Review first:** The agent reads existing cached reports and runtime telemetry (`get_overview`, `get_health`,
   `get_runtime_insights`, `get_fastapi_report`, `get_database_advisor_report`, `get_architecture_report`).
2. **Action plan:** The agent produces a structured markdown plan with four required sections: Context, Coverage,
   Actions, and Approval.
3. **Approved execution:** The user reviews the plan and grants explicit permission for specific actions. The agent
   executes only approved actions, runs focused tests, re-scans to verify, and reports the evidence re-read after the change.

## Workshop: fix a real database finding with an agent

This walkthrough demonstrates the review, fix, and verification loop using a database advisor finding.

### 1. Run the application

Start your FastAPI application with sharpit installed:

```bash
fastapi dev app.py
```

### 2. Enable the MCP server

Set `SHARPIT_MCP_ENABLED=ON` and connect your agent to `http://127.0.0.1:8000/sharpit/api/mcp`.

### 3. Ask the agent to scan and fix

Instruct the agent:

> Inspect database advisor findings in our running application. Propose a plan to resolve any high-priority issues,
> but stop for approval before editing code.

### 4. What the agent sees

The agent reads cached findings or asks permission to run `sharpit db scan` (CLI only, after the user's approval) (`sharpit db scan --json`). The scan
identifies a missing foreign key index on the `items.order_id` column:

- Rule ID: `DB-SCHEMA-002`
- Severity: `MEDIUM`
- Target: `table:items, column:order_id`
- Remediation: Add an index on foreign key column `order_id` in SQLAlchemy model `Item`.

### 5. What the agent changes

With the user's approval, review the query plan and the foreign-key access path before proposing an index; DB-SCHEMA-002 does not prescribe `index=True`.
definition:

```python
class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
```

### 6. Verify

The agent reloads the application and, after explicit approval, runs CLI-only `sharpit db scan --json`. The updated report
is re-read for the `items.order_id` target and remaining access-path concerns.

## The same tools from a terminal

Every diagnostic tool described above can be executed directly from a terminal using the `sharpit` CLI. Run
`sharpit --help` or `sharpit <command> --help` for complete command options, global flags, and command reference.
