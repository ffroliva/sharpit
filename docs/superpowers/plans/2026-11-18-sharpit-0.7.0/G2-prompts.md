# G2 — MCP prompt guidance

| Scenario | Expected behaviour |
|---|---|
| List prompts | Advertises all four BootUI prompts and their optional arguments in order. |
| Get prompt with context | Renders only declared nonblank values, masked and bounded to 500 characters. |
| Get prompt with unknown context key | Returns invalid params without rendering a prompt. |
| Read MCP prompts | Remains side-effect free. |
| Guidance tool references | Every cited tool exists in `sharpit.engine.tools.TOOLS`. |

Production path: `src/sharpit/engine/mcp.py:Prompt`, `McpServer._dispatch`, `_get_prompt`; tests exercise the existing MCP endpoint.

- [x] **Step 1:** Read BootUI 2.4.0 prompt, dispatcher, and conformance sources; map unavailable tools to the sharpit catalog.
- [ ] **Step 2:** Port prompt tests and observe assertion failures on the current implementation.
- [ ] **Step 3:** Add ordered argument metadata, rendering, masking, truncation, and adapted BootUI prompt text.
- [ ] **Step 4:** Record every text adaptation in the G2 matrix fragment and update the changelog.
- [ ] **Step 5:** Run red check, lane gates, common gates, ruff, format, and pyright; commit the feature.
