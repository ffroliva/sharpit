# CLI Task 2 client corrections

| Scenario | Expected behaviour |
|---|---|
| A slow tool returns after the connection phase | Reads use the full request timeout and return the response. |
| A timed-out read, connection failure, or TLS failure | Each produces its own safe, redacted message. |
| Error bodies echo a token, including `BootUI` | Rewrite product text, then redact the token before displaying the outcome. |
| A foreign server returns 403 | The CLI exits with error unless the sharpit catalog confirms the refusal. |
| A response exceeds 1 MiB | Normal reads accept it, matching BootUI's unbounded reads. |
| MCP toggle and tool arguments | `post(path, body)` is public; command argument building keeps declared arguments only. |

Production paths: `sharpit.cli.client.Client`, `sharpit.cli.outcomes.confirm_answered`, and `sharpit.cli.commands.run`.

- [ ] **Step 1:** Add each regression test and verify assertion-level reds with `scripts/dev/red_check.py`.
- [ ] **Step 2:** Port BootUI v2.4.0 transport, options, outcome, and argument behavior in the existing CLI path.
- [ ] **Step 3:** Remove unneeded bounded methods and record the excluded `ci` per-call API as a deviation.
- [ ] **Step 4:** Run the CLI and common lane gates, lint, formatting, and type checks.
