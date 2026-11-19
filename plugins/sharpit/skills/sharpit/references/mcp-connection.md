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
value sharpit generated and logged once at startup. Verify `GET /sharpit/api/mcp-server` or `sharpit mcp status` before
debugging the client; it reports enabled state and advertised tools. Tools are availability-driven, so do not assume
every application exposes every tool.

When sharpit MCP tools are available:

1. Establish context with `get_overview` and supplied or prior health evidence. `get_health` returns a cached health tree; UNKNOWN means not run yet.
2. Use targeted diagnostic reads such as `get_live_activity`, `get_request_profile` (a correlated breakdown for one
   retained request, with its SQL timing, statements, and exceptions), `get_agent_status` (reports `NOT_ATTACHED` in
   this version as no bytecode agent sensors are shipped), `get_exceptions`, `get_exception_detail`, `get_sql_traces`,
   `get_traces`, `get_log_tail`, `get_http_exchanges`, `get_http_routes` (per-route request counts, status classes, and
   p50/p95/p99 latency over the retained window), `get_sqlalchemy_statistics`, and `get_beans`. Their buffers are
   bounded: before concluding that a request, statement, or call never happened, check for retention evictions.
   For query-specific evidence use `get_runtime_insights` and `get_runtime_insight`. `get_profile_diff` compares configuration across active profiles, not runs. sharpit has no previous-run comparison.
3. Actions are CLI only. Name the exact `sharpit` command (for example `sharpit db scan`) and get user approval before running any scan or action; MCP cannot run actions.
4. Use identifiers returned by summary tools to request detail rather than repeatedly fetching broad result sets.
5. After making and testing a fix, rerun the same tool and compare results.

Read tools honor panel enablement. Scan tools also honor panel and global read-only settings (`SHARPIT_READ_ONLY=true`).
Results are masked and paginated reads are capped. Large reads (SQL traces, startup timeline, log tail, sessions, the
vulnerabilities report, activity, exchanges, configuration, beans, metrics, threads) return a short first page without
`limit`; when `page.hasMore` is true, narrow `query` or raise `limit` instead of assuming you saw everything. Log and
exception messages have secret-like assignments and authorization credentials masked, and are omitted under
`SHARPIT_EXPOSE_VALUES=METADATA_ONLY`.
