# sharpit plugin

Connects Claude Code or Cursor to a running FastAPI app that has sharpit installed, and gives the agent the sharpit skill.

Install:

```
/plugin marketplace add ffroliva/sharpit        # Claude Code
/plugin install sharpit@sharpit
```

Cursor, Codex and other clients that read the Agent Plugins format use the same directory: `mcp.json` holds the connection
and `skills/` the skill.

**Before the agent can connect**, the app must be running with sharpit's MCP endpoint on. It is off by default:

```bash
pip install "sharpit[fastapi]"      # and call sharpit.install(app) in your app
SHARPIT_MCP_ENABLED=ON fastapi dev app.py
```

The plugin points at `http://127.0.0.1:8000/sharpit/api/mcp`. If your app listens elsewhere, set `SHARPIT_MCP_URL`
(Claude Code) or edit the URL in your client's MCP settings. The endpoint is read-only (50 tools, no action tool) and
loopback-only; a remote agent needs sharpit's bearer token, which this plugin never stores.

Do not hand-edit `skills/sharpit/`. It is a byte-for-byte copy of the repository's `skills/sharpit/`, and a test fails
when they drift. Edit the original and copy it over:

```bash
cp -R skills/sharpit/. plugins/sharpit/skills/sharpit/
```
