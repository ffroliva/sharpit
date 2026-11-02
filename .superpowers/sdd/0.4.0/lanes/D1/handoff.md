# Lane D1 handoff

Status: DONE_WITH_CONCERNS. Tasks 0–3 implemented except the MCP default limit (needs `tool_dispatch.py`); four
out-of-list tests need one-line updates ("Needs from coordinator"). Next step: `ready-for-review`.

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
  do not fit sharpit ids (`sharpit.max-queries`, node ids). Finding rule id: `[A-Za-z0-9._:-]`, ≤ 64, owned by an
  advisor (`advisor_for`); identity: ≤ 512 chars, no whitespace/control. BootUI's messages verbatim.
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
- **Guard policy:** only the global read-only covers finding mutations (BootUI); no owning-panel gate (the guard
  cannot read the body). Chain order unchanged.
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

4. **Four tests outside the May-touch list fail because the 0.4 surface grew (one-line patches each):**
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
