# Lane B-security handoff

Implementer: Claude Code (claude-opus-5-5, claude-flavio for tasks 0-3; resumed and finished by claude-opus-5-5,
claude-riskcontrol)

## Status

DONE (council skipped per the brief; it runs on the finished diff). All plan tasks committed: Task 0 catalogue, Task 1
contract, Task 2 four rule categories, Task 3 routes/MCP/CLI/safety/flag on, Task 4 Svelte view. R-fastapi-security's
two low follow-ups (a Host route behind a hand-written wrapper; a hand-written wrapper around StaticFiles) are covered
at rule level (`test_wrapped_host_and_static_files_are_never_called_permit_all`) and through the scan route (two pins
in `tests/fastapi/test_security_api.py`): classified, never crash.

## Commits

| Task | Red | Fix |
|---|---|---|
| 0 catalogue | - | `0518ed5` docs |
| 1 contract | `298faee` | `b6c29d1` |
| 2 transport | `a5d6f3b` | `eb75c3f` |
| 2 auth | `c8e019a` | `e445775` |
| 2 config | `96ebb75` | `e537f77` |
| 2 source | `fc4a915` | `442a29b` |
| 3 scan | `e030f19` | `086a6e7` |
| 3 routes/MCP/safety | `0f50d8e`, superseding `a7924ad` | `1e058a8`, `8ecefac` (complexity ratchet refactor of lane-added introspector code) |
| follow-up pins | `56022e4` (pins, mutation-proven) | - |
| 4 view | `5c5236e` (vitest) | `2f13fd1` (view + rebuilt static bundle) |

Full red table, pins and mutation proofs: `findings.md`.

## Must-cover (all exist; all pass at head unless noted)

`test_post_scan_golden_parity` (skips: post-scan golden absent, G0 → gate `unverified`),
`test_violation_never_contains_literal_secret`, `test_get_after_scan_opens_no_source_file`,
`test_scan_reads_only_app_package`, `test_trap_route_untouched_by_every_introspecting_surface`,
`test_scopes_floor_and_newest_classify_same`, `test_read_only_blocks_scan`, `test_inactive_security_paths_404`,
`test_security_get_no_side_effects`, `test_mcp_tools_list_has_only_get`, `test_docs_table_matches_registry`.

## Decisions

- 27 active rules (22 ported P, 5 new N), 27 dropped with reasons: `docs/security-advisor-checks.md`.
- Rule severities are fixed per rule; SEC-AUTHZ-001 is INFO (public routes are legitimate), as WAVE-B §2 proposes.
  SEC-CORS-006 stays LOW; the message says when credentials are on.
- Middleware options are read in the adapter (`FastApiIntrospector.security_facts`, appended) and leave only as fact
  names; `SecurityFacts`/`MiddlewareFacts`/`SchemeUrl` appended to `engine/spi.py`. Diff vs release/0.5.0 on both files
  is additions only. Only the root app's `user_middleware` options are read.
- No `service.py`: the service lives in `report.py`; the pytest plugin skips the security assessment.
- `build_inputs` uses `appsource.resolve_package_root` (asserted by `test_scan_uses_the_one_package_root_resolver`).
- "Spring Security" -> "FastAPI security", "filter chain" -> "middleware stack"; keys `filterChains` kept.
- No `nullable.json`: every key of the pre-scan golden is filled.
- `test_get_after_scan_opens_no_source_file` was rewritten in place at `a7924ad` (its must-cover name could not change);
  its red is recorded at `a7924ad` and the `0f50d8e` row is historical.
- The view reuses `AdvisorPanel` like `RestApi.svelte`; dismissals go through the shared `dismissed-rules` routes.
- The rebuilt bundle under `src/sharpit/ui/static/` is outside the plan's May-touch list; the lane brief requires
  committing it after `npm run build`.

## Live check (in-process)

`examples/fastapi_sqla` `create_app(app_package="examples.fastapi_sqla")` under TestClient: GET `NOT_SCANNED`; POST
scan 200 `SCANNED` (SEC-CONFIG-007 x2, SEC-AUTHZ-002, SEC-FAPI-001, no analysis errors); violations page 200; GET after
`SCANNED`; `/sharpit/` 200. No port bound. Observation: the resolver scans the whole top-level `examples` package (F5a
design), so `examples/fastapi_sample` literals show up.

## Gates (at `2f13fd1` + evidence)

ruff 0, format 0 (591 files), pyright 0 errors; lane + safety matrix + test_tools + code shape + import boundary:
1227 passed, 1 skipped; vitest 296 passed, `npm run check` 0. Full suite: see below.

## Open questions for the coordinator

1. The post-scan golden (G0) is absent: `test_post_scan_golden_parity` stays `unverified`.
2. `resolve_package_root` widens a dotted `app_package` to its top-level package (observation above).

## How to resume

`git log --oneline release/0.5.0..HEAD` on `lane/0.5.0-B-security`; every uv command needs `UV_LINK_MODE=copy`.
