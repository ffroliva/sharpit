# Findings: lane R-fastapi-security (0.5.0)

Review closed: `0.4.0-integration/.superpowers/sdd/0.4.0/lanes/B-fastapi-security/review.md` @ `49c755d`, plus the
Task 0 regression found after the rebase and the Task 3 coordinator addition.

## Reds

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Review 1 / spec §5.2: a `route_class` subclass of `APIRoute` dropped from mappings, rest-api and security (exact-type check) | tests/fastapi/test_introspector_routes.py::test_custom_apiroute_subclass_still_classified | 3ffec3e06308058cb10fb11cea31b6dfeaaad400 | `assert [] == [(('GET',), '/timed', '...timed')]` | Fixed in `978e1d0` |
| Task 0: `vars()` on a slotted app object (the plugin's `AsyncEngine`) raised, failing `test_live_engine_driver_counts_as_covered` | tests/fastapi/test_introspector_routes.py::test_object_without_dict_has_no_routes | 3ffec3e06308058cb10fb11cea31b6dfeaaad400 | `assert 'raised vars() argument must have __dict__ attribute' == []` | Fixed in `978e1d0` |
| FastAPI 0.115 cumulative `security_scopes` doubled scopes vs `own_oauth_scopes` (>= 0.120) | tests/fastapi/test_introspector_security.py::test_scopes_floor_and_newest_classify_same | 3ffec3e06308058cb10fb11cea31b6dfeaaad400 | `('admin', 'admin', 'read') != ('admin', 'read')` | Fixed in `978e1d0` |
| Review 2: an `APIRoute` inside a plain Starlette sub-app classified as inspectable | tests/fastapi/test_introspector_security.py::test_apiroute_in_plain_starlette_subapp_is_unknown | 3ffec3e06308058cb10fb11cea31b6dfeaaad400 | `assert [('/sub/secret', False)] == [('/sub/secret', True)]` | Fixed in `978e1d0` |
| Task 3 / spec §14 beans row: `_resource` opened the provider's source (`inspect.getsourcelines`) | tests/fastapi/test_introspection_trap.py::test_beans_resource_never_opens_the_source_file | 24165af1ed2b50b51e34347c23e7ba2df053fe92 | `assert ['_builtin_open'] == []` | Fixed in `1b81242` |

`red_check.py` said RED for all five at their red SHA (assertion under `tests/`).

## Pins (passed on first run; mutation-proven in a scratch worktree `R-fs-base`)

| Test | Mutation (scratch tree, reverted) | Failure under the mutation |
|---|---|---|
| tests/fastapi/test_introspection_trap.py::test_trap_route_untouched_by_every_introspecting_surface | M1: `_walk` uses `isinstance(route, _KNOWN_ROUTES)` instead of `issubclass(type(route), ...)` | `assert ['TrapRoute.__class__', ...] == []` |
| same | M2: `_walk_mounted` reads `getattr(route, 'routes')` | `assert ['TrapMount.routes', ...] == []` |
| tests/fastapi/test_introspector_routes.py::test_mount_property_never_evaluated | M2 | `assert 4 == 0` |
| tests/fastapi/test_fastapi_security_api.py::test_introspection_never_reads_or_calls_custom_route_attributes | M3: unknown-route branch reads `getattr(route, 'effective_candidates', None)` | `assert 3 == 0` |
| tests/safety/test_b_fastapi_security_safety.py::test_inactive_fastapi_security_paths_404 | `adapter._not_found` raises 418 | `assert [418, 418, 418, 418] == [404, 404, 404, 404]` |
| tests/test_safety_matrix.py::test_sweep_source_read_exemptions_only_shrink (F5a-harness pin, now pinned empty) | n/a: its assertion changed with the list it pins (Task 3 plan) | — |

The beans entries leaving `SWEEP_SOURCE_READ_EXEMPT` turn the four beans sweep cases
(`test_every_get_no_side_effects[/sharpit/api/beans-*]`, `test_every_mcp_tool_no_side_effects[get_beans-*]`) red at
`24165af`, but through the `no_side_effects` teardown (`app source read: examples/fastapi_sample/app.py`), which
`red_check` rejects as a red; the lane red above carries its own spy instead.

Carried from 0.4.0 (red `95136a9`, unchanged): `test_plain_starlette_subapp_routes_are_unknown_best_effort`,
`test_plain_starlette_subapp_route_explained_as_unknown`, `test_custom_route_never_touched_by_any_get_lint_clean`.

## Every new rule removed (scratch) → failing test

| Rule (fix `978e1d0` / `1b81242`) | Failing test when removed |
|---|---|
| `issubclass(type(route), _KNOWN_ROUTES)` / `issubclass(..., APIRoute)` | `test_custom_apiroute_subclass_still_classified` (exact type) or the trap test (`isinstance`, M1) |
| `_attrs()` instead of `vars()` | `test_object_without_dict_has_no_routes` |
| `in_fastapi` per route | `test_apiroute_in_plain_starlette_subapp_is_unknown` |
| `sorted(set(scopes))` | `test_scopes_floor_and_newest_classify_same` |
| `_first_line` instead of `getsourcelines` | `test_beans_resource_never_opens_the_source_file` |

## Historical SHA

| Superseded red | Historical SHA | Reason |
|---|---|---|
| (local only, never merged) the same four Task 1 reds | e6ddeaa7094ddc7fdc4255489d6354ffc0e3cc90 | Rewritten before any fix commit: a string replace had also changed the 0.4.0 red `test_plain_starlette_subapp_route_explained_as_unknown`, and the rest-api assertion did not filter framework routes as every consumer does. Re-committed as `3ffec3e` with additions only. |
