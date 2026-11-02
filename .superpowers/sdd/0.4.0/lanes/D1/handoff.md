# Lane D1 handoff

Status: DONE_WITH_CONCERNS. Tasks 0–3 implemented except the MCP default limit (needs `tool_dispatch.py`). Review
round 1 (`review.md`/`ponytail-review.md` @ 0619594, coordinator rulings R-D1a/b/c) fixed: see "Review round 1" below.
Next step: `ready-for-review`.

## How to resume

- Worktree `C:\development\github\sharpit-wt\0.4.0-D1`, branch `lane/0.4.0-D1`, base `d37c6f2` (lane F head, coordinator
  ruling 00:15). Prefix every `uv` command with `UV_LINK_MODE=copy`. Pytest logs go to
  `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\D1-*.log`.
- Evidence: `predict-council.md`, `findings.md` (red table), `field-map.md`, `checklist.md`, `docs.md` in this folder.

## Done (commits)

| Task | Red | Fix |
|---|---|---|
| 0 predict (CAUTION 7/10, three mitigations, all applied) | — | `predict-council.md` |
| 1 `dismissedFindings` store + `dismissed_pairs()` | `fbaf74e409e3537f5c5f1fb0b3238fb3235c83bd` | `2123b370068802f41a283b31c47485a6b1df9c85` |
| 2 guard subject, routes, header dedup, `Scorecard` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `57fc15a40e300daafbf90433c0d5ccaece64f0d2` |
| 3 overview `run`, MCP `get_config` view | `82b7f1957192b30847b88334244cfa5f70180fd2` | `f662993dd85b8f22e6b4dee57bf747933cdb3b82` |
| regression: route order (`test_foundation_suite_equivalence`) | full run at `f662993` | `b99a3eb48e090ee4511c37ec54da90aedd61820f` |

Red table (test id | red SHA | assertion message): `findings.md`.

## Decisions and deviations

- **Store port follows BootUI 2.2.0 `DismissedRulesStore`** (one read of both sections, `ignored` lines kept verbatim,
  Base64URL no-pad notes with a canonical re-encode check, `MAX_FINDINGS=1000` → 409, `MAX_NOTE_LENGTH=200` → 400,
  blank note → none, note stored untrimmed as BootUI). `dismissedRules:` is now written only when non-empty or already
  present (BootUI), so a findings-only file has no empty rules node; existing rule tests unchanged and green.
- **Validation (sharpit deviation, logged in the module docstring):** BootUI's `[A-Z]…` rule ids and `v<n>:` identities
  do not fit sharpit ids (`sharpit.max-queries`, node ids). Finding rule id: `[A-Za-z0-9._:-]{1,200}` (as rule ids),
  owned by an advisor, never a full fingerprint (`<advisor>:...`); identity (R-D1a): the rest of the line, ≤ 512 chars,
  inner spaces allowed, no edge whitespace, line break, C0/C1 control or lone surrogate, and its last word may not be
  `n=...` (it would read back as a note). BootUI's messages verbatim.
- **Errors reuse `AdvisorViolationError(status, message)`** (BootUI `AdvisorViolationException`) instead of the plan's
  `DismissalValidationError`/`DismissalCapError`/`DismissalStorageError`: same HTTP result, no new types. OS write
  errors propagate as for `/dismissed-rules` (500).
- **No 503:** `state_dir` is always a `str` (default `.sharpit`); BootUI's no-store case has no sharpit counterpart.
- **415 body** is `{"error": "Unsupported Media Type"}` (as `mcp.py`); body cap 64 KiB → 413 `Request payload exceeds limit`.
- **Routes registration:** `routes/__init__.py` is not in the May-touch list, so `adapter._routes` appends
  `routes/dismissed_findings.build_routes` after `build_routes`. When the coordinator merges, moving that line into
  `build_routes` is optional.
- **Header dedup (predict mitigation):** a response that already has a CSP keeps its whole header set (assets keep no
  `Pragma`); otherwise each baseline header is added only if absent.
- **Guard policy — deviation from BootUI (R-D1b):** BootUI gates finding mutations with the global read-only only.
  sharpit adds the owning-panel gate after the route parses `ruleId`: `guard.owning_panel_access(rule_id, settings,
  "dismissed-findings")` (the `/dismissed-rules` helper, made public with a `subject`), so a disabled owner panel →
  403 `disabled_reason`, a read-only one → 403 `read_only_reason`, panel field `dismissed-findings`. Safety favours the
  stricter gate. Test-runtime (panel-less) rule ids → 400 `NO_PANEL_MESSAGE`, for POST and DELETE. Chain order
  unchanged.
- **Restore of an unowned rule (review #8):** `restore_finding` checks syntax only; it removes the matching stored line
  even when it sits in `ignored` because no advisor owns its rule any more. Dismissing still needs an owner.
- **Comments (review #6):** `#` lines (any indent) inside a managed section are kept, re-emitted right after the
  section key, and never counted as ignored.
- **`get_config` MCP/CLI view:** `propertySuggestions` is emitted as `[]` (BootUI `McpAgentViews.config` returns
  `List.of()`; every key emitted), for MCP and CLI alike (BootUI's CLI shares the dispatcher). The plan said "omitted";
  the oracle wins.
- `tests/engine/test_overview.py::test_overview_every_key_and_values` now expects the MVP keys plus `run`.
- `test_overview_golden_parity` skips until G0a's `tests/fixtures/bootui/2.2.0/overview/` capture exists.
- llm-council `--tier high` reviews a diff; it was not run at Task 0 (no diff). See below.

## Needs from coordinator

1. **MCP inventory default limit (Task 3, not done):** BootUI applies `INVENTORY_DEFAULT_LIMIT = 25` to `get_config`
   and `get_beans` (also `get_http_exchanges`, `get_threads`) when the call has no `limit`, in the shared dispatcher
   (`McpArguments.normalize`, MCP and CLI). sharpit's equivalent line is
   `src/sharpit/engine/tool_dispatch.py:181` (`limit = … else max_results`), outside D1's May-touch list. Patch:
   `DEFAULT_LIMITS = {"get_config": 25, "get_beans": 25, "get_http_exchanges": 25, "get_threads": 25}` and
   `else min(DEFAULT_LIMITS.get(tool.name, max_results), max_results)`, with a red test calling `call_tool(..., "get_beans", {}, via="mcp")`
   on > 25 rows. Assign to whichever lane owns `tool_dispatch.py` (none today).
2. **High-tier llm-council** (`skills/llm-council`, Claude + Codex + Antigravity) on this lane's diff before merge,
   recorded in the coordinator's `review.md` (guard.py touched).
3. G1G2 consumes `DismissalStore.dismissed_pairs()`; it now returns real pairs, no wiring needed from D1.

4. **Done in review round 1 (R-D1c), commit `bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2`.** The conformance patch below
   was wrong (`DEVIATIONS` are value-only and must exist on both sides); the test got a separate `NEWER_THAN_GOLDEN`
   map instead, which asserts the five `run` keys are present and then excludes them. The original notes:
   - `tests/test_safety_matrix.py::test_get_route_table_is_complete`: add to `ROWS`
     `("dismissed-findings", "GET", "/sharpit/api/dismissed-findings", 200, True),` (beside the `dismissed-rules` row).
   - `tests/test_safety_matrix.py::test_write_route_table_is_complete`: add `"/api/dismissed-findings"` to
     `_NOT_PANEL_WRITES` (global-flag subject like dismissed-rules; covered by
     `tests/fastapi/test_dismissed_findings_api.py::test_mvc_global_read_only_blocks_the_mutations_but_not_the_list`
     and `tests/safety/test_d1_safety.py`). C5 forbids D1 from editing this file.
   - `tests/test_conformance.py::test_shape_matches_golden[overview]` (G0a's file): add to `DEVIATIONS["overview"]`
     `"run"`, `"run.instanceId"`, `"run.runId"`, `"run.ordinal"`, `"run.startedAt"` with reason
     "BootUI 2.2.0 OverviewDto.run; the 1.17.0 golden predates it".
   - `tests/fastapi/test_install.py::test_overview_shape_matches_golden_keys` (line 94): `set(golden("overview")) | {"run"}`.

## Verification (head `b99a3eb48e090ee4511c37ec54da90aedd61820f`)

- `uv run ruff check`: all checks passed. `uv run ruff format --check`: 411 files already formatted.
  `uv run pyright`: 0 errors, 0 warnings.
- Full suite `uv run pytest -q -n 4`: **3587 passed, 6 skipped, 5 failed** (log
  `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\D1-pytest2.log`; F's base: 3567 passed, 5 skipped). Failures:
  the four tests in "Needs from coordinator" 4 (expected, out-of-list files), plus
  `tests/fastapi/test_sql_trace_overhead.py::test_statement_overhead_budget`, a load flake: it passed in the first full
  run (`D1-pytest.log`) and 3/3 alone; D1 touches no capture or SQL path. The first run also caught
  `tests/test_foundation_suite_equivalence.py` (route order: `/api/cli` must stay last), fixed in `b99a3eb` by splicing
  the new routes after the dismissed-rules routes.
- Plan's targeted set (Task 3 Step 5, plus `test_conformance.py`): 391 passed, 1 skipped, 1 failed (conformance, above).

## Review round 1 (rulings R-D1a/b/c, base head 0619594)

| # | Finding | Test id | Red SHA | Fix SHA |
|---|---|---|---|---|
| 1 | R-D1a: a REST API target (inner spaces) cannot be dismissed | `tests/engine/advisors/test_dismissals.py::test_dismissed_pairs_accepts_a_real_rest_api_target` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 2 | R-D1b: no owning-panel gate on finding mutations | `tests/fastapi/test_dismissed_findings_api.py::test_finding_mutations_need_the_owning_panel_enabled_and_writable` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 2 | R-D1b: test-runtime rule ids accepted | `tests/fastapi/test_dismissed_findings_api.py::test_test_runtime_findings_are_refused_with_the_no_panel_message` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 3 | lone surrogate / C1 / U+2028 identity → 500 or accepted | `tests/fastapi/test_dismissed_findings_api.py::test_non_encodable_and_control_identities_are_refused_with_400_never_500` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 4 | `_save` stamps after `os.replace`, hiding another store's write | `tests/engine/advisors/test_dismissals.py::test_two_stores_sharing_a_state_dir_keep_each_others_dismissals` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 5 | finding rule id capped at 64 | `tests/engine/advisors/test_dismissals.py::test_a_finding_rule_id_may_be_as_long_as_a_rule_id` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 6 | comments in managed sections dropped / counted | `tests/engine/advisors/test_dismissals.py::test_comments_inside_the_managed_sections_are_kept_and_not_counted` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 7 | a full fingerprint accepted as ruleId | `tests/fastapi/test_dismissed_findings_api.py::test_a_full_fingerprint_is_not_a_finding_rule_id` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 8 | restoring an unowned rule's finding → 400, line stays | `tests/fastapi/test_dismissed_findings_api.py::test_restoring_a_finding_whose_rule_no_advisor_owns_still_removes_its_line` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |
| 9 | route splice `max()` crashes install without the anchor | `tests/fastapi/test_dismissed_findings_api.py::test_finding_routes_are_appended_when_the_dismissed_rules_anchor_is_absent` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `96ca0d59546beab020685032ebd4cdf40d140141` |

Assertion messages: `findings.md`.

- **Red tests edited after their red commit (forced by R-D1a; coordinator ruling: moved to "Superseded reds" in `findings.md`, header `Historical SHA`, not replayed).** Inner spaces are now valid, so
  four earlier red-committed tests that used a space as *the* invalid character now use a tab, in `96ca0d5`:
  `test_dismissals.py::test_dismissed_findings_note_and_cap_validation` (one tuple),
  `test_dismissals.py::test_malformed_finding_lines_are_ignored_counted_and_kept` (two fixture lines),
  `test_dismissed_findings_api.py::test_mvc_refuses_bad_bodies_with_a_fixed_message_that_never_quotes_the_note` (one
  body), `tests/masking/test_d1_masking.py::test_a_secret_note_is_never_echoed_by_an_error` (one body). Every assertion
  is unchanged; each still refuses or ignores the same inputs count.
- **UI (R-D1c), `8f9300db9d1c67b03f1ddab0907c96a1b5e8f701`:** e2e `support.ts` and `acceptance.spec.ts` expect the rail
  link and the view heading `Scorecard`; `ui/src/views/Overview.svelte` h1 and region label are `Scorecard` (BootUI
  2.2.0 `BootUiPanels` title and its e2e `openView('scorecard', 'Scorecard')`). The nav *group* stays `Overview`
  (`nav.ts` is O4). **Needs from coordinator: rebuild `src/sharpit/ui/static/`** (D1 may not run `npm run build`; no
  `ui/node_modules` in this worktree, so `npm run check` was not run either); until then the UI drift job and the e2e
  heading check see the old bundle.
- **Open minors (skipped by ruling):** `run.instanceId` under `--reload` (each reload starts a new process, so a new id;
  BootUI's instance spans devtools restarts; semantics differ, noted only); note length counts code points, BootUI
  counts UTF-16 units (astral characters differ); MCP inventory default limit 25 (`tool_dispatch.py`, not D1's file;
  "Needs from coordinator" 1).
- Seen, not D1's: a lone surrogate in a request body logs `sharpit capture hook request start failed
  (UnicodeEncodeError); capture continues` from `engine/capture` (D2's area); the request itself is answered 400.

## Verification, review round 1 (head `8f9300db9d1c67b03f1ddab0907c96a1b5e8f701` + evidence)

- `uv run ruff check`: all checks passed. `uv run ruff format --check`: 411 files already formatted. `uv run pyright`:
  0 errors, 0 warnings.
- Full suite `uv run pytest -q -n 4`: **3623 passed, 6 skipped, 2 failed** (log
  `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\D1-pytest3.log`). The two failures are load flakes in overhead
  budgets (`test_capture_overhead.py::test_request_overhead_budget`, `test_sql_trace_overhead.py::test_statement_overhead_budget`):
  both pass alone (2 passed in 8.02s). D1 touches no capture or SQL path. The four earlier out-of-list failures are
  fixed.
