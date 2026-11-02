# Lane D1 user-facing text (O3: for the coordinator to place in README / skills/sharpit)

- **Dismiss one finding, not the whole rule.** `GET/POST/DELETE /sharpit/api/dismissed-findings` keep per-finding
  dismissals in `<state_dir>/sharpit.yml` under `dismissedFindings:`, next to `dismissedRules:`. POST/DELETE take
  `{"ruleId": "...", "identity": "...", "note": "optional, ≤ 200 characters"}` as `application/json`. Notes are stored
  Base64URL-encoded and returned only by `GET` (no MCP tool or CLI command). `SHARPIT_READ_ONLY=true` refuses the
  mutations with 403; listing still works. At most 1000 dismissed findings (409 beyond).
- **Scorecard.** The Overview panel is titled "Scorecard" (BootUI 2.2.0). `GET /sharpit/api/overview` gains
  `run: {instanceId, runId, ordinal, startedAt}`: `instanceId` is fixed for the Python process, `runId`/`ordinal`
  change on each `sharpit.install()` (e.g. each `uvicorn --reload` restart), so agents can tell a restart apart.
- **MCP `get_config`** no longer returns the property-name suggestions the browser's search box completes from
  (`propertySuggestions` is `[]`); the HTTP endpoint still returns them.
