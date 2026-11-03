# Lane C-fastapi: the `fastapi` advisor (BootUI `spring`)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `C-fastapi` (worktree `C:\development\github\sharpit-wt\0.5.0-C-fastapi`, branch `lane/0.5.0-C-fastapi`) |
| **Goal** | BootUI's Spring advisor re-cut for FastAPI: ~13 rules over the app's route handlers and source, on F5a's advisor core. |
| **Spec** | §5, §5.6 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §1, §7 (`SPRING-*` ids kept where the concept maps, `FASTAPI-*` new); golden `fastapi/captured.json` (pre-scan; scope keys `inspected`, `componentsAnalyzed`) + G0's post-scan files if present |
| **Worker** | agy-sergio, Gemini 4 Argon (after C-architecture, same AST idioms); reviewer Opus |
| **Council** | not required |
| **Depends on** | F5a-source, F5a-core; C-architecture (worker only, no shared file). No introspector edit: handlers come from the existing `FastApiIntrospector.api_model()` (`introspector.py:195`) |
| **May touch** | `src/sharpit/engine/collectors/fastapi_advisor/` (new: `handlers.py`, `rules_async.py`, `rules_models.py`, `rules_app.py`, `report.py`), `src/sharpit/fastapi/routes/fastapi.py`, `src/sharpit/engine/panels04/fastapi.py`, `ui/src/lib/panels04/fastapi.ts`, `src/sharpit/engine/tools04/fastapi.py`, `ui/src/views/Fastapi.svelte`, `ui/tests/component/Fastapi.test.ts`, `docs/fastapi-advisor-checks.md`, `tests/engine/collectors/fastapi_advisor/`, `tests/fastapi/test_fastapi_advisor_api.py`, `tests/fastapi/trap_surfaces_fastapi.py`, `tests/safety/test_c_fastapi_safety.py` (declares `fastapi_scan`), `tests/test_fastapi_docs_table.py`, `tests/fixtures/bootui/2.2.0/fastapi/nullable.json`, the lane folder |
| **Must NOT touch** | `fastapi/introspector.py`, `engine/testsession/swallowed.py` (imported: the broad-except rule calls `swallowing_lines`), `engine/appsource.py`, `engine/advisors/*`, `settings.py` |

**Architecture:** for each operation in `api_model()`, the endpoint object is read with `inspect.getattr_static`; a
handler is analysed only when `type(fn) is types.FunctionType` after unwrapping `vars(fn).get("__wrapped__")` up to
depth 8 and `functools.partial` through `vars(partial_obj)["func"]`; callable instances, builtins and anything whose
`co_filename` is outside the `appsource` root are skipped with a limitation. Its source tree comes from `appsource` by
`co_filename`/`co_firstlineno` (read via `getattr_static(fn, "__code__")`). Rules are AST visitors over that function.

**Contract surface:** `GET {api}/fastapi`, `POST {api}/fastapi/scan`, `GET {api}/fastapi/rules/{id}/violations`; MCP
`get_fastapi_report`, `get_fastapi_rule_violations`; `fastapi_scan` CLI-only (§14).

## Must-cover

`test_post_scan_golden_parity` (asserts `scanned.captured.json`/`violations.captured.json` with `assert_parity` and
`assert_enum_values`; skips with reason `post-scan golden absent` until G0 lands, which the gate reports as
`unverified`),
`test_report_golden_parity`, `test_decorated_handler_resolved_to_inner_function`,
`test_callable_instance_endpoint_skipped_without_getattr`, `test_partial_and_library_handlers_skipped_with_limitation`,
`test_trap_route_untouched_by_every_introspecting_surface` (via `trap_surfaces_fastapi.py`),
`test_sync_endpoint_doing_io_flagged`, `test_blocking_call_in_async_flagged`, `test_sync_endpoint_without_io_not_flagged`,
`test_violation_never_contains_literal_secret`, `test_scan_reads_only_app_package`, `test_get_after_scan_opens_no_source_file`,
`test_read_only_blocks_scan`, `test_inactive_fastapi_paths_404`, `test_fastapi_get_no_side_effects`,
`test_mcp_tools_list_has_only_get`, `test_docs_table_matches_registry`.

## Tasks

### Task 1: contract and catalogue
- [ ] `test_report_golden_parity` (pre-scan pin; post-scan red if G0), `test_docs_table_matches_registry` (red on
  missing catalogue ids), `nullable.json`; catalogue from WAVE-B §7.

### Task 2: handler index
- [ ] Red commit (skeleton `resolve_handler` returns `None`): `test_decorated_handler_resolved_to_inner_function`
  (`@functools.wraps` decorator: resolved `co_filename` is the app module, not the decorator's), `test_callable_instance_endpoint_skipped_without_getattr`
  (an instance with a `__call__` and a counting `__getattr__`: counter 0, limitation present),
  `test_partial_and_library_handlers_skipped_with_limitation`. Implement. Commit `feat: static route handler index`.

### Task 3: rules (one commit per file)
- [ ] Red commits, one test per rule (`# ported: SpringScannerTests.<method>` where it maps, e.g.
  `singleFlightRejectsOverlappingScanAndReleasesAdmission` is F5a's core):
  - async: `test_blocking_call_in_async_flagged`, `test_sync_endpoint_doing_io_flagged`,
    `test_sync_endpoint_without_io_not_flagged`, `test_await_asyncio_sleep_not_flagged`.
  - models: `test_pydantic_v1_config_class_flagged`, `test_orm_mode_flagged`, `test_missing_response_model_on_dict_return`.
  - app: `test_on_event_instead_of_lifespan`, `test_background_task_heavy_work`, `test_broad_except_in_handler`.
  - each category: `test_violation_never_contains_literal_secret`.
  Commits `feat: fastapi advisor <category> rules`.

### Task 4: adapter, routes, MCP, safety
- [ ] Red commit: `test_scan_reads_only_app_package`, `test_get_after_scan_opens_no_source_file`,
  `test_read_only_blocks_scan`, `test_inactive_fastapi_paths_404`, `test_fastapi_get_no_side_effects`,
  `test_mcp_tools_list_has_only_get`. Flag on. Commit `feat: fastapi advisor panel`.

### Task 5: view and live check
- [ ] Svelte view (reference `views/Spring.vue`), vitest; live check. Commit `feat: fastapi advisor view`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/C-fastapi/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
