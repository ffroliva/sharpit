# MCP for AI agents

The MCP endpoint is **off by default**. Enable it with `SHARPIT_MCP_ENABLED=ON` (or `install(app, mcp_enabled="ON")`,
or the switch in the MCP Server panel), then point a streamable-HTTP MCP client at
`http://127.0.0.1:8000/sharpit/api/mcp` (POST only). It exposes 18 read-only tools: `get_overview`, `get_config`,
`get_mappings`, `get_loggers`, `get_beans`, `get_http_exchanges`, `get_log_tail`, `get_exceptions`,
`get_exception_detail`, `get_sql_traces`, `get_live_activity`, `get_alembic_migrations`, `get_health`,
`get_database_connection_pools`, `get_threads`, `get_vulnerabilities_report`, `get_rest_api_report`, and
`get_rest_api_rule_violations`. There is no action tool, so an agent cannot change a logger or start a scan through
MCP. The same guard chain and masking apply to it as to the UI.

An agent skill that teaches an AI assistant to install and use sharpit is in
[`skills/sharpit`](https://github.com/ffroliva/sharpit/tree/main/skills/sharpit). The `sharpit` command-line client
is planned and not shipped; the `/sharpit/api/cli/tools/<tool>` HTTP endpoint is.
