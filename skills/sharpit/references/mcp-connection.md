# Connect an agent to the MCP server

Set this up only when the user asks to connect an agent or MCP client to sharpit. If sharpit MCP tools are already in
your tool list, just call them — there is nothing to configure. For a one-off diagnostic, use the CLI instead. The full
guide is at `https://ffroliva.github.io/sharpit/ai-agents/`.

The MCP server is opt-in. Enable it with `SHARPIT_MCP_ENABLED=ON` or the MCP Server panel toggle, then configure the
agent with the application's actual port. VS Code uses a `servers` block:

```json
{
  "servers": {
    "sharpit": {
      "type": "http",
      "url": "http://127.0.0.1:8000/sharpit/api/mcp"
    }
  }
}
```

Claude Code, Cursor, and most other clients use `mcpServers` instead, and Claude Code can register the server directly
with `claude mcp add --transport http sharpit http://127.0.0.1:8000/sharpit/api/mcp`.

Prefer `127.0.0.1` and replace `8000` when needed. Loopback peers, configured trusted proxy ranges, and trusted container
gateways need no credentials. Any other peer allowed through `SHARPIT_ALLOW_NON_LOCALHOST=true` must send sharpit's token
as `Authorization: Bearer <token>` on every call or receive `401`; the token is `SHARPIT_AUTHENTICATION_TOKEN`, or the
value sharpit generated and logged once at startup. Verify `GET /sharpit/api/mcp` or `sharpit mcp status` before
debugging the client; it reports enabled state and advertised tools. Tools are availability-driven, so do not assume
every application exposes every tool.

When sharpit MCP tools are available:

1. Establish context with `get_overview` and supplied or prior health evidence. `get_health` executes live indicators
   that may query databases or services; obtain approval when behavior is unknown or that work is outside scope.
2. Use targeted diagnostic reads such as `get_live_activity`, `get_request_profile` (a correlated breakdown for one
   retained request, with its SQL timing, statements, and exceptions), `get_agent_status` (reports `NOT_ATTACHED` in
   this version as no bytecode agent sensors are shipped), `get_exceptions`, `get_exception_detail`, `get_sql_traces`,
   `get_traces`, `get_log_tail`, `get_http_exchanges`, `get_http_routes` (per-route request counts, status classes, and
   p50/p95/p99 latency over the retained window), `get_sqlalchemy_statistics`, and `get_beans`. Their buffers are
   bounded: before concluding that a request, statement, or call never happened, check for retention evictions.
   For what a run did across requests, use `get_runtime_insights`, `get_runtime_insight`, and `get_profile_diff`.
3. Run only the advisor relevant to the task and within the approved scan scope, such as `architecture_scan`,
   `fastapi_scan`, `database_advisor_scan`, `security_scan`, `vulnerabilities_scan`, or `rest_api_scan`.
4. Use identifiers returned by summary tools to request detail rather than repeatedly fetching broad result sets.
5. After making and testing a fix, rerun the same tool and compare results.

Read tools honor panel enablement. Scan tools also honor panel and global read-only settings (`SHARPIT_READ_ONLY=true`).
Results are masked and paginated reads are capped. Large reads (SQL traces, startup timeline, log tail, sessions, the
vulnerabilities report, activity, exchanges, configuration, beans, metrics, threads) return a short first page without
`limit`; when `page.hasMore` is true, narrow `query` or raise `limit` instead of assuming you saw everything. Log and
exception messages have secret-like assignments and authorization credentials masked, and are omitted under
`SHARPIT_EXPOSE_VALUES=METADATA_ONLY`.
