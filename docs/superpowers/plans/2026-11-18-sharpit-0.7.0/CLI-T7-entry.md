# CLI Task 7 entry cleanup

| Scenario | Expected behaviour |
|---|---|
| A token occurs in a JSON string and adjacent plain text | Every occurrence is redacted |
| Parser construction selects all tools, one command subtree, or no tools | The same command tree and help output are built |
| Catalog rows represent disabled, read-only, action, and ready tools | Existing status text is preserved |
| Client operations fail during POST | Each exception assertion captures the same client error |

- [x] **Step 1:** Add a regression test for mixed JSON and plain-text token redaction.
- [x] **Step 2:** Extract parser and catalog work into named helpers; share the redaction marker and simplify exception tests.
- [x] **Step 3:** Run lane and common gates, review the diff, commit, and push.
