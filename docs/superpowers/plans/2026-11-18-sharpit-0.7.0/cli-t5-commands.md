# CLI Task 5 command behavior

| Scenario | Expected behaviour |
|---|---|
| Default client sends a tool call | The response is parsed and emitted; no injected factory is required. |
| Transport, application and usage errors | Errors return the documented exit code, preserve useful causes in verbose mode, and redact tokens. |
| Help and argument validation | Environment guidance and required metavars match the command contract. |
| Concurrent invocations | Each invocation writes only to its own streams. |
| Fractional and millisecond timeouts | Positive durations parse and timeout messages retain readable precision. |

- [x] **Step 1:** Add assertion-level regressions and verify each against the current implementation.
- [x] **Step 2:** Port the BootUI 2.4.0 command guidance, redaction, timeout and parser behavior in the existing CLI path.
- [x] **Step 3:** Run CLI, import-boundary, common, lint, formatting and type gates; review the final diff.

Production path: `sharpit.cli.commands.run`, `sharpit.cli.client.Client`, and `sharpit.cli.options.positive_seconds`.
