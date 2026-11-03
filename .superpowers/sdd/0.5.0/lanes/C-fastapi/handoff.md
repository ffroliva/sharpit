# Handoff: lane C-fastapi (sharpit 0.5.0)

Implementer: Claude Code subagent / Claude Opus 5.5 (claude-opus-5-5)
Branch `lane/0.5.0-C-fastapi`, from `release/0.5.0` @ cd05632. Plan: `docs/superpowers/plans/2026-11-03-sharpit-0.5.0/C-fastapi.md`. Spec §5, §5.6; contract WAVE-B §1, §7.

## Status

DONE_WITH_CONCERNS: Tasks 1-5 done. Eight shared tests outside May-touch fail once the `fastapi` flag is on (Q1, Q2);
they need a coordinator fix commit on `release/0.5.0`.

| Task | Red | Fix |
|---|---|---|
| 1 catalogue + docs table + goldens | da8318e739329286869571edfe751b7f28755fef | f61b005 |
| 2 static handler index | d712ab1417e8e6b0cd2435b606dcf31ee931c70c | 5050893 |
| 3 async rules | 3239b0c6513dc13ae17d9197d91785300725a9e9 | 72e6504 |
| 3 models rules | 7987b7dca1895549cb6b00db4273b3c4379ddc22 | a021e42 |
| 3 app rules + secret | f25403ea337e81801ec43d506d67ff595da941bb | 9c9af9f |
| 4 routes, MCP/CLI, safety, flag on | d3e2768762ece15fc6e746782fe8034c672c44a6 | 8b70c7b |
| 5 Svelte view (vitest red) | bbc8d9f435defd68902bde772f84126ee9be52a5 | e25f112 (view + rebuilt static bundle) |

Red tables, pins and mutations: `findings.md`.

## Must-cover

| Test | Exists | Passes at head |
|---|---|---|
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_report.py::test_post_scan_golden_parity | yes | skips `post-scan golden absent` (G0) |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_report.py::test_report_golden_parity | yes | yes (pin) |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_handlers.py::test_decorated_handler_resolved_to_inner_function | yes | yes |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_handlers.py::test_callable_instance_endpoint_skipped_without_getattr | yes | yes |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_handlers.py::test_partial_and_library_handlers_skipped_with_limitation | yes | yes |
| tests/fastapi/test_introspection_trap.py::test_trap_route_untouched_by_every_introspecting_surface | NOT in this base (R-fastapi-security's file, unmerged); this lane ships `tests/fastapi/trap_surfaces_fastapi.py` (GET `/sharpit/api/fastapi`, MCP reads, CLI `fastapi_scan`) | unverified until R-fastapi-security merges (Q3) |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_sync_endpoint_doing_io_flagged | yes | yes |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_blocking_call_in_async_flagged | yes | yes |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_async.py::test_sync_endpoint_without_io_not_flagged | yes | yes (pin) |
| tests/engine/collectors/fastapi_advisor/test_fastapi_advisor_rules_app.py::test_violation_never_contains_literal_secret | yes | yes |
| tests/fastapi/test_fastapi_advisor_api.py::test_scan_reads_only_app_package | yes | yes |
| tests/fastapi/test_fastapi_advisor_api.py::test_get_after_scan_opens_no_source_file | yes | yes |
| tests/fastapi/test_fastapi_advisor_api.py::test_read_only_blocks_scan | yes | yes |
| tests/fastapi/test_fastapi_advisor_api.py::test_inactive_fastapi_paths_404 | yes | yes (pin) |
| tests/fastapi/test_fastapi_advisor_api.py::test_fastapi_get_no_side_effects | yes | yes |
| tests/fastapi/test_fastapi_advisor_api.py::test_mcp_tools_list_has_only_get | yes | yes |
| tests/test_fastapi_docs_table.py::test_docs_table_matches_registry | yes | yes |

The resolver: `tests/fastapi/test_fastapi_advisor_api.py::test_scan_uses_the_one_resolver` asserts the scan calls
`appsource.resolve_package_root` once with the app (F5a-source's request).

## Decisions (nobody to ask; recorded here)

1. **Handler objects come from the introspector's walk, not `api_model()`.** `ApiRouteInfo` holds only the
   `module:qualname` string; resolving it from module globals fails for every factory app (`create_app.<locals>.x`).
   `handlers.route_endpoints` duck-types `introspector._entries()` (the walk `api_model()` is built on, as
   `tools.rest_api_service` duck-types `api_model`) and reads `endpoint`/`response_model` with
   `inspect.getattr_static` only. No introspector edit. The walk itself still uses `getattr` on routes until
   R-fastapi-security lands (its fix covers this surface too).
2. **`functools.partial` endpoints are skipped**, not unwrapped: `partial.func` is a C slot, absent from
   `vars(partial)` and returned by `getattr_static` as a descriptor, so the plan's `vars(p)["func"]` cannot work
   without `getattr`. Test name `test_partial_and_library_handlers_skipped_with_limitation` agrees.
3. **`fn.__code__` is read directly** after `type(fn) is FunctionType` (the plan says `getattr_static`, which returns
   the getset descriptor, not the code object); a plain function's `__code__` runs no user code.
4. **Rules shipped (10):** FASTAPI-ASYNC-001/002, FASTAPI-HTTP-001, FASTAPI-BG-001, FASTAPI-PYD-001,
   FASTAPI-RESP-001, FASTAPI-EVT-001, FASTAPI-EXC-001, SPRING-WEB-004, SPRING-CONFIG-004. Parked as `C-fastapi-2`
   (listed "Not yet" in `docs/fastapi-advisor-checks.md`): FASTAPI-ASYNC-003, FASTAPI-ASYNC-004, FASTAPI-DEP-001,
   SPRING-WEB-001, SPRING-CONFIG-002, SPRING-DATA-001.
5. **One finding per handler (or per module) per rule**, the message listing every call with its line, so the
   fingerprint (rule + target) survives line moves. Messages name calls and lines only, never arguments.
6. **Broad except reuses `swallowing_lines`** (`engine/testsession/swallowed.py`, unchanged): it reads source text
   and the index keeps trees, so the module is `ast.unparse`d once and both the check and the function spans read
   that same text.
7. **No root → still SCANNED**: the two runtime rules (debug, title) run; source rules are unevaluated and the
   resolver's reason is a limitation. A factory app no module holds needs `SHARPIT_APP_PACKAGE`.
8. **Status always `SCANNED`** after a scan (BootUI `SpringScanner.doScan` has no PARTIAL path); completeness is in
   `evidence`.
9. **Settings reused:** `architecture_max_files` / `architecture_max_file_bytes` bound the index (F5a-source
   handoff); no new setting (settings.py is Must-NOT-touch).
10. `nullable.json` not created: no payload null where the golden has a value.
11. The rebuilt `src/sharpit/ui/static/` bundle is committed per the brief (not in the plan's May-touch list).
12. Engine `registry` `assess` path is `sharpit.engine.collectors.fastapi.service`; this package is
    `fastapi_advisor` (plan), so the pytest plugin skips the fastapi advisor (missing module is skipped by design).

## Questions for the coordinator

- **Q1 (protected `tests/test_safety_matrix.py`):** with the flag on, 4 rows fail:
  `test_every_get_no_side_effects[/sharpit/api/fastapi/rules/FASTAPI-ASYNC-002/violations-{plain,sqla}]` (400
  "Advisor scan ID must not be blank." is the contract answer without `scanId`; only rest-api's path is special-cased
  at line 678) and `test_every_mcp_tool_no_side_effects[get_fastapi_rule_violations-{plain,sqla}]` (`_tool_arguments`
  seeds only `get_rest_api_rule_violations`). Proposed generic fix (other advisor lanes need it too): line 678
  `expected = (400,) if "/rules/" in path and path.endswith("/violations") else (200, 307, 404)`; in
  `_tool_arguments`, for `get_fastapi_rule_violations` scan with `tools04.fastapi.fastapi_service(handle.context)`
  and return `{"id": results[0]["id"], "scanId": ...}` (the sample app yields 4 violating rules).
  Same cause in `tests/engine/test_tools.py::test_mcp_tools_no_side_effects[get_fastapi_rule_violations]` (outside
  May-touch): it seeds arguments only for `get_rest_api_rule_violations`; it needs a fastapi branch (seed
  `ctx.lazy("fastapi-advisor", ...)` with a `FastapiAdvisor` over a fixed `Evaluation`, as the rest-api branch does).
- **Q2 (outside May-touch):** 4 tests use `SPRING-WEB-001` as an id nobody owns; F5a-core's registry gives every
  `SPRING-*` id to `fastapi`, so they fail once the flag is on: `tests/engine/advisors/test_dismissals.py::test_owning_panel[SPRING-WEB-001-None]`,
  `::test_unknown_owner_refused_before_the_file_is_touched`, `tests/engine/advisors/test_registry.py::test_registry_owns_today_ids`,
  `tests/fastapi/test_dismissed_rules_api.py::test_unknown_owner_400[SPRING-WEB-001]`. Fix: replace the id with one
  no prefix owns (e.g. `QUARKUS-WEB-001`).
- **Q3:** the must-cover trap test lives in R-fastapi-security's unmerged `test_introspection_trap.py`; run it after
  that merge (it collects `trap_surfaces_fastapi.py`).

## Live check (in-process, no port bound)

`examples/fastapi_sqla` `create_app(app_package="examples", ...)` through `TestClient`:
GET `/sharpit/api/fastapi` 200 NOT_SCANNED; POST `/scan` 200 SCANNED, 10 handlers, 10 rules evaluated, results
FASTAPI-EXC-001 (`/slow` swallows `except Exception`), FASTAPI-RESP-001 x5, FASTAPI-BG-001 (`/background` schedules
`_background_sql_task`), FASTAPI-ASYNC-001 (`/slow` `time.sleep`); all true positives on reading the source. GET
violations 200 (1 of 1); MCP `get_fastapi_report` isError false; CLI `fastapi_scan` 200.

## Gates (head, see Status for the evidence commit)

- `ruff check`: all passed; `ruff format --check`: 574 files formatted; `pyright`: 0 errors.
- UI: `npm run check` clean; vitest 37 files / 285 tests passed; `npm run build` committed (e25f112).
- Lane tests: `pytest tests/engine/collectors/fastapi_advisor tests/fastapi/test_fastapi_advisor_api.py tests/test_fastapi_docs_table.py`: all pass (1 skip: post-scan golden absent).
- Full suite (`-n 4`, log `0.5.0-integration/.superpowers/sdd/0.5.0/logs/C-fastapi-full.log`): 4750 passed, 10 skipped,
  10 failed, 1 error:
  - 9 failures are Q1 (5: safety matrix x4, test_tools x1) and Q2 (4): shared tests outside May-touch that assume
    the fastapi panel is off.
  - `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget`: budget under
    load (the message itself says "overshoot within the noise: suspect a busy machine"); passes alone (65 passed with
    test_osv.py); this lane touches no hot path. Parked: budget under load.
  - `tests/engine/vulns/test_osv.py::test_initial_failure_raises[envelope]` (setup error): passes alone; not this lane.

## How to resume

Nothing open in the lane besides Q1-Q3 (coordinator). Next lane C-fastapi-2: the six parked rules.
