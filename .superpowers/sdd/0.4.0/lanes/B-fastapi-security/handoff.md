# Lane B-fastapi-security handoff

Implementer: claude-subagent-opus (lane B-fastapi-security)
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/B-fastapi-security.md`
Branch / worktree: `lane/0.4.0-B-fastapi-security` in `C:\development\github\sharpit-wt\0.4.0-B-fastapi-security`, base `34f1689`.

## Status

### Current fix-round 2 state

Fix commits: `ed98dcac8b0e8fae2ed43a59248eb31e26ed3aef` and `255e06f50d780eca302e82e8501932d8d23aea97`. Status: **DONE_WITH_CONCERNS**; B-owned regressions are fixed and the complexity refactor preserves behavior. One pytest-plugin test outside B's May-touch list remains failing.

- Focused Python lane/shared regressions after the complexity refactor: 85 passed, 1 skipped (`B-fastapi-security-r2j-focused.log`).
- Safety matrix + surface flags: 1,029 passed (`B-fastapi-security-r2-safety.log`).
- `ruff check`: passed; `ruff format --check`: 474 files already formatted after the refactor.
- `pyright src/sharpit`: 0 errors after the refactor.
- `tests/test_code_shape.py`: 3 passed; new introspector helpers bring C901 back to the single pre-existing over-limit function.
- UI `tsc --noEmit`: passed; Vitest: 35 files / 282 tests passed.
- Final full suite `pytest -q -n 4` at `255e06f`: 4,254 passed, 9 skipped, 1 failed, 45 warnings in 472.69s (`B-fastapi-security-r2-final-full.log`). The remaining failure is `tests/pytest_plugin/test_plugin_reports.py::test_live_engine_driver_counts_as_covered`; it also fails in isolation and is outside B's May-touch list. No lane-owned failures remain. SQLite overhead was load-sensitive in the prior full run; it passed in the final run.

- Task 0 predict: CAUTION 7/10 (`predict.md`, `be95ac5`); mitigations folded into the code.
- Task 1 model + classification: red `369dc4b`, fix `0d353cb`.
- Task 2 `security_model()`: red `6ca0044`, fix `3859499`, typing `2f8f203`.
- Task 3 routes, explain, MCP, safety, masking, `nullable.json`, engine flag: red `6060ab6`, fix `0460657`.
- Task 4 view + UI flag: red `eb03313`, fix `9eda51f`; evidence files (this folder).
- Red tables: `findings.md` (Python reds by SHA, UI reds under `Commit`).

## Gates (implementer, at `9eda51f` / suite at `0460657`, no Python change after)

- `uv run ruff check`, `uv run ruff format --check`: clean. `uv run pyright`: 0 errors.
- vitest: 35 files / 280 tests passed; `npm --prefix ui run check` (tsc) exit 0.
- Full pytest `-n 4` at `0460657` (log `0.4.0-integration/.superpowers/sdd/0.4.0/logs/B-fastapi-security-pytest.log`):
  4238 passed, 9 skipped, 1 failed, 2 errors. The 2 errors are `no_side_effects` teardowns that saw my own edits to
  `FastapiSecurity.svelte` / `handoff.md` during the run (not product behaviour; both green on rerun, 145 passed with
  `test_osv.py`, the safety matrix GET sweep and `test_surface_follows_flags.py`). The failure is
  `test_sql_trace_overhead.py::test_statement_overhead_budget` (50.4 µs vs 50 µs, noise 38.6 µs, loaded run; passes
  in isolation; this lane has no hot path). Budget untouched.

## Status: DONE_WITH_CONCERNS (llm-council not run; full-suite rerun on a quiet tree is the coordinator's gate)

## Live check

In-process (no server bound; COMMON forbids dev servers), `examples.fastapi_sqla.app.create_app(enabled="ON")`
through `TestClient`. The example has no OAuth2 routes (O3, example untouched), so every endpoint is `unsecured`:

- `GET /sharpit/api/fastapi-security` → 200, one chain `["GZipMiddleware"]`, `auth` lists empty, `limitations: []`.
- `GET /sharpit/api/fastapi-security/endpoints` → 200, `total: 10`, e.g. `GET /background` `unsecured`.
- `GET /sharpit/api/fastapi-security/explain?method=GET&path=/owners` → 200 `matched: true`, `rule: "unsecured"`.
- `GET /sharpit/api/fastapi-security/explain?path=nope` → 400 `{"error": "Invalid request"}`.

Request for the coordinator's `live-verify.md`: the same four requests against a running example, plus an app with an
`OAuth2PasswordBearer` route (the API tests cover that shape in-process).

## Needs from coordinator

1. `src/sharpit/ui/static/` not rebuilt (lanes never run `npm run build`).
2. The UI test lives at `ui/tests/component/fastapiSecurity.test.ts` (vitest include pattern), not beside the view.
3. No edit to `tests/conftest.py::_PATH_PARAMS` was needed (no path parameters).

## How to resume

`UV_LINK_MODE=copy` on every uv command; pytest logs under
`C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/`. `itsdangerous` is not installed:
tests use a local `SessionMiddleware` class, never Starlette's.

## Decisions (deviations from the lane plan)

1. `SecurityModel.middleware` → `chains: tuple[SecurityChain(prefix, middleware), ...]` (a chain per mounted sub-app
   with its own middleware, contract §3 Python mapping).
2. The plan's `matcher` callback is replaced by `SecuredRoute.path_regex` (Starlette `compile_path` source, built in
   the adapter); the engine runs `re.match` (engine rule 1: no Starlette import). Never `Route.matches()`.
3. One field `unknown_dependency` (the plan's `route_level_unknown` would always equal it): a route/router/app
   `dependencies=[...]` entry (`Dependant.name is None`) with no scheme in its tree.
4. Scopes read from `own_oauth_scopes` (FastAPI ≥ 0.120) or `security_scopes` (0.115), unioned along the path.
5. FastAPI's docs routes are not listed; a framework mount (StaticFiles) is `unsecured`, a user opaque mount `unknown`
   + `bestEffort` + a limitation.
6. Extra keys (pass parity): `limitations` on report and endpoints; explain adds `rule`, `roles`, `pattern`.
7. The high-tier llm-council was not run by the lane worker (brief asks for predict only); see `predict.md` §Council.

## Fix round 1 (Codex gpt-6-luna)

- Red commit: `95136a909eda60bc76c5ba01f280ca80c96f194c`.
- WIP reviewed: `0a4f22178bd9763df9b42b51ab9c8234511e84c1`.
- Current status: implementation in progress; targeted run `round1-targeted2.log` reported 16 failed / 32 passed. Failures include pre-existing assertions whose semantics conflict with the requested scheme-only `secured` rule, plus route traversal and modern FastAPI lazy-router behavior. Do not claim green until resolved.
- Fixes in progress: engine explain mount capture and best-effort propagation; custom route exact-type guard; scheme-less/optional dependency detection; cumulative middleware stacks; UI unique keys and empty-value defaults.
- Next: resolve remaining failures without changing any red test body; run UI checks, targeted tests, safety matrix, lint/format/type gates and full suite detached; commit final fix and update this handoff.

## Fix-round result (Codex gpt-6-luna)

Final status: DONE_WITH_CONCERNS; fix round is not merge-ready.
- Red: `95136a909eda60bc76c5ba01f280ca80c96f194c`.
- WIP reviewed: `0a4f22178bd9763df9b42b51ab9c8234511e84c1`.
- Fix commits: `3120361`, `4bf1302`.
- Changes made: no `effective_candidates` calls; exact-type custom-route handling; scheme-only secured classification; scheme-less/optional dependency best-effort; mount-aware explain; cumulative middleware stacks; lazy-router static expansion/limitation; UI duplicate keys and empty-input defaults.

Evidence:
- Targeted Python: 17 failed, 31 passed (`B-fastapi-security-round1-focused.log`). Several failures remain in security and shared route introspection.
- Safety matrix: `tests/safety/test_b_fastapi_security_safety.py` passed.
- Ruff check: fails only on the long line in the committed red test `tests/fastapi/test_fastapi_security_api.py:234`; red body was not changed. Format check reports this red file plus unformatted source before formatting.
- Pyright: 21 errors remain in `introspector.py`.
- UI type check passed; FastAPI Security vitest passed 7/7 after the duplicate-key change.
- Full suite at the round snapshot: 4,218 passed, 9 skipped, 37 failed (`B-fastapi-security-round1-full.log`); the remaining failures include this lane's security tests and shared introspector consumers.

Next: resolve the listed Python regressions and typing issues while keeping committed red bodies unchanged, then rerun all gates. No changes were made to review/gate files.

## Round 2 root-cause audit (Codex gpt-6-luna)

The 37 failures at `7912d36` came from these independent defects; the focused rerun now passes after the fixes in `ed98dca`.

| Failed tests | Why they failed |
|---|---|
| `tests/engine/test_appsecurity.py::test_route_level_unknown_dependency_is_custom` | Its old assertion treated an unknown custom guard as proof of security. Review requires `custom`, `bestEffort: true`, and `secured: false`; the old red is historical, with replacement assertions in `test_custom_guard_is_not_secured` and `test_route_level_unknown_dependency_is_custom_but_unsecured`. |
| `test_get_never_calls_dependencies`, `test_scheme_found_in_nested_dependency`, `test_security_scopes_read`, `test_route_level_dependency_without_scheme_is_unknown`, `test_internals_drift_degrades`, `test_custom_route_class_is_unknown`, `test_sharpit_mount_hidden`, `test_mounted_sub_app_middleware_is_its_own_chain`, `test_route_chain_is_every_enclosing_stack`, `test_unexpandable_include_router_limitation_says_so` in `tests/fastapi/test_introspector_security.py` | The walker omitted FastAPI 0.162's lazy `_IncludedRouter` routes/dependency context, misclassified `SharpitMount` and framework routes, and `_chains` accessed a nonexistent `Mount.middleware` attribute. The drift fallback also called `vars()` on a bad original router outside its exception guard. |
| `test_report_golden_parity`, `test_endpoints_rules`, `test_explain_matches_route`, `test_explain_input_edges`, `test_middleware_values_never_exposed`, `test_mcp_read_tool_only`, `test_custom_route_is_unknown_best_effort`, `test_plain_starlette_subapp_routes_are_unknown_best_effort`, `test_plain_starlette_subapp_route_explained_as_unknown`, `test_scheme_less_route_dependency_is_custom_but_not_secured`, `test_scheme_less_parameter_dependency_is_best_effort`, `test_optional_scheme_inside_enforcing_dependency_is_best_effort`, `test_explain_empty_method_defaults_to_get` in `tests/fastapi/test_fastapi_security_api.py` | The missing mount attribute made `model_of()` degrade to an empty model; the leaked `SharpitMount` opaque row also changed endpoint ordering and explain matches. Fixes restore the chain without reading middleware options, and retain custom/optional dependency best-effort status. |
| `test_scan_finds_fastapi_violations`, `test_generic_types_unwrapped`, `test_mounted_app_without_routes_is_a_limitation`, `test_violations_paging_and_errors`, `test_dismiss_restore_changes_counts`, `test_get_rest_api_report_mcp_never_scans` in `tests/fastapi/test_rest_api_api.py`; `test_router_and_app_level_dependencies_included` in `tests/fastapi/test_introspector_providers.py` | The rewrite dropped lazy included routes and dependencies, leaving REST scans empty/partial and provider discovery incomplete. The static walker now reads stored route lists plus inherited router/app dependencies. |
| `test_routes_exact_rows`, `test_row_details`, `test_endpoint_is_flat_json_and_sharpit_excluded`, `test_failing_include_router_expansion_yields_fallback_row` in `tests/fastapi/test_introspector_routes.py` | The walker missed FastAPI's `APIWebSocketRoute`, Host child routes, and lazy router routes; Sharpit's Mount subclass appeared as an opaque `(any)` row. The old include-router test required invoking `effective_candidates()`, contrary to the no-user-code rule; it is replaced with a test asserting the method is never called and `/v1/ping` remains visible. |
| `test_include_router_after_install_seen` in `tests/pytest_plugin/test_plugin_apps.py`; `test_xdist_app_seen_by_one_worker_passes` in `tests/pytest_plugin/test_plugin_xdist.py` | The plugin snapshots the adapter's route model, so the same lazy-router omission hid routes from post-install inclusion and worker advisor autodetection. Reading the live stored route list on each walk fixes both. |

### Review findings retained

- No dependency, security scheme, custom route method, middleware option, or route `matches()` call during introspection.
- Secured status is based on required security schemes; a custom guard is best effort and unsecured.
- Mount order is captured for explain; each route uses its actual mount lineage for middleware selection.
- Nested middleware wrappers and Host routes are read from stored objects; settings/secrets never enter output.
- Optional auth and scheme-less parameter dependencies remain best effort; failed FastAPI internals degrade with a limitation.
- UI report and explain keys remain stable; lint-breaking test line was superseded with a multiline identical-intent test.

## Full-suite failure isolation

The `ed98dca` full run's non-lane failures were checked separately. `test_stream_shutdown_within_lifetime`, `test_lane_gate_needs_accept_unverified_for_non_pytest_red`, `test_xdist_controller_never_imports_app_code`, and `test_sql_trace_route_module_is_mounted` passed together in isolation. `test_live_engine_driver_counts_as_covered` failed in isolation with an unknown report reason (`warning: no SQL statement was executed`); its code and test are outside B's May-touch files, so no B-lane change was made there. The SQLite overhead test reported 82.053 µs overhead against its 50 µs budget, with 137.647 µs noise, identifying a busy-machine result; it passed in the final full run.
