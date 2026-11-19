# CLI Task 3 — outcomes and refusal confirmation

Production path: `sharpit.cli.outcomes.confirm_answered` interprets the `ToolResult` returned by `Client.invoke`.

| Scenario | Expected behaviour |
|---|---|
| Invalid or foreign catalog | Refusal is an error; catalog error and HTTP status remain visible |
| Sharpit catalog disabled after 503 | Endpoint disabled, exit 2 |
| Sharpit outage after 503 | Server error, exit 1 |
| Read-only panel 403 | Refusal reason is retained, exit 2 |
| Other HTTP statuses | Match BootUI `ToolOutcome` and `ToolResult.errorMessage` |
| Server echoes token in an error | Outcome text redacts token |

- [ ] **Step 1:** Add regression assertions for round 1 findings and see them fail by assertion.
- [ ] **Step 2:** Validate catalogs in `Client.catalog`; use its validation and message helpers in refusal confirmation.
- [ ] **Step 3:** Port BootUI outcome classification and `ToolResult.errorMessage`; run lane and common gates.
- [ ] **Step 4:** Record adaptations in `docs/reference/matrix-updates/cli-t3.tsv` and commit the changes.
