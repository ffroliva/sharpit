# CLI Task 7 — output and entry point

Production paths: `sharpit.cli.commands.run`, `sharpit.cli.outcomes.confirm_answered`, `sharpit.cli.fail_on.evaluate`, and `sharpit.cli.client.Client`.

| Scenario | Expected behaviour |
|---|---|
| Piped output | JSON is the default; `--json` keeps the response verbatim. |
| Terminal output | Tool payloads use the BootUI text renderer; color follows `--no-color` and `NO_COLOR`. |
| Fail-on gate | The answer prints before gate evaluation; its BootUI exit code follows. |
| Tool list | The validated running catalog is authoritative over the bundled manifest. |
| MCP status and toggle | Status reads the server report; enable and disable use the guarded panel action. |
| Console encoding | Unrepresentable output is replaced rather than raising. |
| Package entry | `python -m sharpit.cli`, `sharpit.cli.main`, and the installed console script work without framework imports. |
| Request count | No update check or other unrequested request occurs. |
| JSON token redaction | Server JSON bytes stay verbatim except token occurrences; occurrences in keys and number literals are redacted, with a matching number literal emitted as the string `"[redacted]"`. |
| Terminal diagnostics | Secrets and terminal controls are escaped on every argv-derived or error-output path; newlines and tabs remain readable. |
| Tool 404 | A listed tool keeps its server message; an unlisted tool gets a static hint from local metadata. The catalog is checked at most once, without a `/panels` request. |

- [x] **Step 1:** Add assertion-level tests and see them fail for the missing Task 7 behaviour.
- [x] **Step 2:** Port BootUI 2.4.0 rendering and entry behavior through the existing CLI dispatch path.
- [x] **Step 3:** Run the lane, required common, packaging, lint, formatting and type gates; build and inspect the wheel.
- [x] **Step 4:** Record adaptations and commit the tests and implementation separately.
- [x] **Round 2:** Enforce token secrecy in JSON keys, values and number literals while preserving all other raw JSON bytes; redact rendered payloads, cover every argv usage error, preserve multiline diagnostics, escape controls in terminal JSON only, and avoid `/panels` reads for a tool 404.

