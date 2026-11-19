# CLI Task 3: outcomes and refusal confirmation

Production path: `src/sharpit/cli/client.py:Client.invoke` supplies `ToolResult`; the CLI command layer consumes
`confirm_answered` before mapping the outcome to an exit code.

| Scenario | Expected behaviour |
|---|---|
| Foreign target returns 403/404/503 | Exit 1 unless the CLI catalog confirms sharpit answered |
| Sharpit catalog says `enabled: false` after 503 | Endpoint disabled, exit 2 |
| Plain 503 outage | Server error, exit 1 |
| Disabled or read-only panel | Policy refusal, exit 2, with the server reason |
| Invalid, unknown, busy, timed out or server error | BootUI status mapping; exit 1 |

- [x] **Step 1:** Add fake-client tests for status classification, refusal confirmation, reasons, and token secrecy.
- [x] **Step 2:** Port `ExitCodes`, `ToolOutcome.fromStatus`, and `CliContext.confirmBootUiAnswered` to the CLI modules.
- [x] **Step 3:** Run the requested CLI, architecture, lint, format, type and common gates; commit the test and feature changes.
