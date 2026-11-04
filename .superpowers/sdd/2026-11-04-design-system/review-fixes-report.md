# Design system review fixes

| Finding | Regression check | Red evidence / result |
|---|---|---|
| 1. HTTP Exchanges reload ticks | `ui/tests/component/httpExchanges.test.ts` verifies first-load and error ticks, then Retry | Old behavior: 2 failures, each expected 1 request and got 2. Fixed behavior: 7 component tests pass. |
| 2. PanelShell header order/right alignment | `ui/tests/e2e/layout.spec.ts` checks controls and rightmost count; MySQL/PostgreSQL assert count is absent | First run used the old “control itself is flush right” assertion and failed; updated for the specified controls-then-count order. Corrected run pending. |
| 3. Facts and Vulnerabilities spacing | Layout checks for ServerStatus facts and the summary section/padding | Initial summary check depended on a completed vulnerability scan; changed to inspect the same CSS with a fixture element. Corrected run pending. |
| 4. Mono heading size | Layout check inspects `h2.mono` at 13px | Initial selector expected a child `.mono`; fixed to test heading class/style directly. Corrected run pending. |
| 5. HTTP Probe result heading | Layout check asserts zero top/left margins | Corrected run pending. |
| 6. FastAPI Security and SQLAlchemy insets | Layout check compares content and heading left edges | Both checks passed in light and dark during the first run. |
| 7. SQLAlchemy values/status alignment | Layout check verifies numeric alignment, compact label/value spacing, and left-aligned status | First assertion compared computed pixel tracks to the CSS keyword; changed to measure rendered spacing. Corrected run pending. |
| 8. Retry focus | Component tests cover Overview and AdvisorPanel focus; Loggers verifies filter focus | First retry tests showed `scrollable` had removed `tabindex`; explicitly restore it before focusing. Focused tests: 21 passed. |
| 9. Missing Retry actions | Shared AdvisorPanel, PanelShell, ServerStatus and BeanGraph error states now retry; ServerStatus retry test added | Focused component suites passed. Existing Activity and other panel tests remain part of the full run. |
| 10. Docs Material color variants | `tests/design/test_tokens.py` checks variant mappings; browser contrast measurement pending | Docs strict build completed; browser measurement pending. |
| 11. Light/Dark table values | `test_doc_theme_values_match_tokens` compares both columns to tokens | `tests/design`: 22 passed. |
| 12. DESIGN.md type-token references | `test_type_scale_does_not_reference_nonexistent_tokens` | Included in the 22 passing design tests. |
| 13. Delete one-off screenshot comparator | Deleted script and test; checked shard weights and remaining references | No shard-weight entry. Plan left unchanged because no test depends on its file map. |
| 14. Remove no-op code | Removed Health class, Data CSS rule and decode/encode round-trip; inspected `App.svelte` | `current` is already derived once; no duplicate removed there. |

## Final verification

Pending corrected full UI tests, corrected layout e2e run, final UI build/static sync, and browser contrast measurements.

## Final verification update

- Full UI suite: 322 passed; focused retry suite: 21 passed.
- Python design/shard/layout checks: 57 passed; Ruff check and format check passed; strict MkDocs build completed.
- Full `npm run e2e:layout`: 71 passed, 2 failed only in the synthetic Vulnerabilities spacing fixture (the synthetic nodes lacked Svelte scope classes). The fixture now copies those scope classes; targeted rerun is in progress. The other new layout checks passed in both themes.
- Browser check at 720px: `.md-nav__source` contrast was 15.52:1 light and 14.63:1 dark; search placeholder against header was 15.52:1 light and 14.63:1 dark.
