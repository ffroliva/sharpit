# Lane R-fastapi-security: resume `fastapi-security` from `lane/0.4.0-B-fastapi-security` @ `12a67b5`

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `R-fastapi-security` (worktree `C:\development\github\sharpit-wt\0.5.0-R-fastapi-security`, branch `lane/0.5.0-R-fastapi-security`, rebased from `lane/0.4.0-B-fastapi-security` @ `12a67b5`) |
| **Goal** | BootUI's three Spring Security views for a FastAPI app, read statically, merged at golden parity with the 0.4.0 review closed. |
| **Spec** | §5, §5.2; 0.4.0 lane plan `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/B-fastapi-security.md` (interfaces, field map) governs; lane decisions 1–7 in its `handoff.md` stand |
| **Review to close** | `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\lanes\B-fastapi-security\review.md` (@ `49c755d`: blocker 1, majors 2–3) |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §3; goldens `fastapi-security/captured.json`, `endpoints.captured.json` |
| **Worker** | claude-flavio (Opus); reviewer codex |
| **Council** | **required** (`council.md` is Task 0; it was the missing 0.4.0 prerequisite) |
| **Depends on** | F5 |
| **May touch** | the 0.4.0 lane's May-touch list (`engine/collectors/appsecurity.py`, `engine/spi.py` append-only, `fastapi/introspector.py`, `fastapi/routes/fastapi_security.py`, the flag files, `engine/tools04/fastapi_security.py`, `ui/src/views/FastapiSecurity.svelte` + test, `tests/engine/test_appsecurity.py`, `tests/fastapi/test_introspector_security.py`, `tests/fastapi/test_fastapi_security_api.py`, `tests/safety/test_b_fastapi_security_safety.py`, `tests/masking/test_b_fastapi_security_masking.py`, `fastapi-security/nullable.json`); the lane folder |
| **Must NOT touch** | `pytest_plugin/` and `tests/pytest_plugin/` (a fix there is a finding for the coordinator, not this lane); guard, activation, masking engine; `settings.py` |

## Review Focus

1. No `getattr` on an unknown route class; a trap property is never evaluated.
2. Routes of an opaque or plain-Starlette sub-app are `unknown` + `bestEffort`.
3. `test_live_engine_driver_counts_as_covered` is green at the lane head.

## Task 0: council and rebase

- [ ] **Step 1:** `/sharpit:llm-council --tier high` on the lane plan + lane decisions 1–7 → `council.md`. A council
  change to the design is a new task here before Task 2.
- [ ] **Step 2:** Rebase onto `release/0.5.0`. Run
  `tests/pytest_plugin/test_plugin_reports.py::test_live_engine_driver_counts_as_covered` alone (background). It passes
  on `origin/main` @ `f5a7681` (planning session, 1 passed in 8.2 s); the 0.4.0 lane diff touches no
  `pytest_plugin` file.
  - Green → record it, done.
  - Red → `superpowers:systematic-debugging`: run it at the rebased base (green expected) and at the head; bisect the
    lane commits; root cause in `introspector.py` (the plugin's live-engine path walks the app through it). The fix
    stays in this lane's files; if the cause is outside them, stop and hand it to the coordinator in `handoff.md`.

## Task 1: blocker and major (review 1, 2)

**Files:** `src/sharpit/fastapi/introspector.py`, `tests/fastapi/test_introspector_security.py`,
`tests/fastapi/test_fastapi_security_api.py`.

- [ ] **Step 1:** Red commit `test: introspection never calls custom route code; Starlette sub-app routes unknown`:
  - `test_introspection_never_reads_or_calls_custom_route_attributes` — a custom `BaseRoute` subclass whose
    `effective_candidates` property and `matches` method increment a counter; GET report, endpoints and explain;
    assert the counter is 0 (expected failure: 1) and the route is `unknown` + `bestEffort`.
  - `test_plain_starlette_subapp_routes_are_unknown_best_effort` — `app.mount("/sub", Starlette(routes=[...],
    middleware=[auth]))`; `/sub/secret` is `rule: "unknown"`, `bestEffort: true` in endpoints and explain (expected
    failure: `unsecured`, `false`).
- [ ] **Step 2:** Read `vars(route)` only for `APIRoute`, `Route`, `Mount`, `WebSocketRoute`, `Host`, `Router` (exact
  `type(...) in` check, not `isinstance`, so a subclass is unknown); never descend into a sub-app that is not a
  `FastAPI` instance for dependency classification.
- [ ] **Step 3:** Green; the 0.4.0 lane tests green. Commit `fix: static-only route reads in the security model`.

## Task 2: finish the panel

- [ ] **Step 1:** Golden parity on both goldens; extra keys logged in spec §14 (done there).
  `test_inactive_fastapi_security_paths_404`, `test_fastapi_security_get_no_side_effects`,
  `test_mcp_tools_list_has_only_get`, lowest-direct leg (FastAPI 0.115 `security_scopes`) green.
- [ ] **Step 2:** `IMPLEMENTED = True` (both flag files). Commit `feat: fastapi-security panel enabled`.
- [ ] **Step 3:** `/sharpit:live-verify` on `examples/fastapi_sqla`; requests in `handoff.md`.

## Interface for B-security and C-fastapi

`FastApiIntrospector.security_model() -> SecurityModel` and the `SecurityModel` dataclasses in `engine/spi.py` are
frozen at this lane's merge. B-security consumes them read-only; a needed addition is an append in B-security's own
May-touch (R0 chain).

## Evidence

`.superpowers/sdd/0.5.0/lanes/R-fastapi-security/`: `council.md`, `handoff.md` (Task 0 outcome with the command and
output), `findings.md` (review rows 1–3), `field-map.md` (from 0.4.0), `checklist.md`.
