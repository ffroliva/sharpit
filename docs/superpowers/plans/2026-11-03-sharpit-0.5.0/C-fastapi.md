# Lane C-fastapi: the `fastapi` advisor (BootUI `spring`)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `C-fastapi` (worktree `C:\development\github\sharpit-wt\0.5.0-C-fastapi`, branch `lane/0.5.0-C-fastapi`) |
| **Goal** | BootUI's Spring advisor re-cut for FastAPI: ~13 rules over the app's route handlers and source (sync I/O, blocking calls in `async def`, Pydantic v1 leftovers, missing `response_model`, ...), the shared advisor contract. |
| **Spec** | §5, §5.6 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §1, §7 (ids `SPRING-*` kept where the concept maps, `FASTAPI-*` new); golden `fastapi/captured.json` (pre-scan) + G0's `scanned.captured.json` if present |
| **Worker** | agy-sergio, Gemini 4 Argon (after C-architecture; same AST idioms); reviewer Opus |
| **Council** | not required |
| **Depends on** | F5; B-security merged (R0: `fastapi/introspector.py` read helper for the handler list); C-architecture (worker) |
| **May touch** | `src/sharpit/engine/collectors/fastapi_advisor/` (new: `handlers.py`, `rules_async.py`, `rules_models.py`, `rules_app.py`, `report.py`), `src/sharpit/fastapi/introspector.py` (append-only: `route_handlers()` returning `(path, methods, code object, is_coroutine)` from `vars()` of known route classes), `src/sharpit/fastapi/routes/fastapi.py` (F stub), the flag files `engine/panels04/fastapi.py` + `ui/src/lib/panels04/fastapi.ts`, `src/sharpit/engine/tools04/fastapi.py`, `ui/src/views/Fastapi.svelte` + test, `docs/fastapi-advisor-checks.md`, `tests/engine/collectors/fastapi_advisor/`, `tests/fastapi/test_fastapi_advisor_api.py`, `tests/safety/test_c_fastapi_safety.py`, `tests/test_fastapi_docs_table.py`, `tests/fixtures/bootui/2.2.0/fastapi/nullable.json`, the lane folder |
| **Must NOT touch** | `engine/testsession/swallowed.py` (imported, never edited: the broad-except rule calls `swallowing_lines`), `engine/appsource.py`, `engine/advisors/*`, `settings.py` |

**Architecture:** handler list from the introspector (static), source trees from `appsource`, matched by
`code.co_filename`/`co_firstlineno`. Rules are AST visitors over the handler's function body. A handler whose source
is not in the index (library route, `functools.partial`) is skipped with a limitation, not guessed.

## Review Focus

1. No false positive on a sync `def` endpoint with no I/O (FastAPI runs it in a thread pool; that is correct use).
2. Introspection: trap-property route never evaluated.
3. Rule ids: every BootUI `SPRING-*` rule appears in the catalogue as mapped (P), dropped ([JVM] + reason) or replaced.

## Tasks

### Task 1: contract and catalogue
- [ ] Red commit: `test_report_golden_parity`, `test_docs_table_matches_registry`, `nullable.json`; catalogue from
  WAVE-B §7.

### Task 2: handler index
- [ ] Red commit: `test_route_handlers_static_only` (incl. `test_introspection_never_reads_or_calls_custom_route_attributes`
  with the shared trap route), `test_partial_and_library_handlers_skipped_with_limitation`. Implement the
  `route_handlers()` helper. Commit `feat: static route handler index`.

### Task 3: rules (one commit per file)
- [ ] Red commits, one test per rule:
  - async: `test_blocking_call_in_async_flagged` (`time.sleep`, `requests.get`, a sync `Session.execute`),
    `test_sync_endpoint_doing_io_flagged` (sync `def` calling `requests.get` with `async def` peers: a mixed-style
    note), `test_sync_endpoint_without_io_not_flagged`, `test_await_asyncio_sleep_not_flagged`.
  - models: `test_pydantic_v1_config_class_flagged`, `test_orm_mode_flagged`, `test_missing_response_model_on_dict_return`.
  - app: `test_on_event_instead_of_lifespan`, `test_background_task_heavy_work`, `test_broad_except_in_handler`
    (via `swallowing_lines`).
  Implement. Commits `feat: fastapi advisor <category> rules`.

### Task 4: adapter, routes, MCP, safety
- [ ] Tests: `test_get_after_scan_opens_no_source_file`, `test_read_only_blocks_scan`,
  `test_inactive_fastapi_paths_404`, `test_fastapi_get_no_side_effects`, `test_mcp_tools_list_has_only_get`. Flag on.
  Commit `feat: fastapi advisor panel`.

### Task 5: view and live check
- [ ] Svelte view (reference `views/Spring.vue`), vitest; live check. Commit `feat: fastapi advisor view`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/C-fastapi/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
