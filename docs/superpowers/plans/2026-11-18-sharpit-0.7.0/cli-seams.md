# CLI cross-task review fixes

| Scenario | Expected behaviour |
|---|---|
| Token appears in rendered payload or JSON data | Redact string values before truncation; preserve JSON scalar types and keys |
| Server returns its own text or a listed tool returns 404 | Keep server text verbatim and follow BootUI's unknown-tool description |
| Server error contains terminal controls | Escape controls before writing stderr |
| User input includes token-like options | Redact only actual token values and token-flag values |
| Fail-on, timeout, message, and argument edge cases | Match BootUI exits and avoid duplicated validation or mapping |
| CLI documentation describes refused actions | Tool actions use exit 2; refused MCP toggles use exit 1 |

- [x] **Step 1:** Add regression tests for all reported CLI seams and see each fail by assertion.
- [x] **Step 2:** Port the corresponding BootUI 2.4.0 behavior through the existing CLI path; remove duplicate transforms and validation.
- [x] **Step 3:** Update matrix fragments, docs, plugin copy, and changelog where behavior changes.
- [x] **Step 4:** Run the lane and common gates, lint, format, and type checks; review the final diff and commit tests separately from fixes.
