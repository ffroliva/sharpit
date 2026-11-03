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

## Fix round 1 (council: `council-claude.md`, `council-gemini.md`)

Merged `release/0.5.0` first (`b274482`; no duplicated top-level defs in the merged files).

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Gemini high: an opaque sub-app behind mount middleware reported as framework code (`opaque=False`, chain 0) | tests/fastapi/test_introspector_security.py::test_opaque_sub_app_behind_middleware_is_unknown_on_its_own_chain[mount-middleware] and [wrapped-starlette-app] | 0243173bd5449ae4f33cd8086c3cd48460ce41bd | `[('/legacy/{path}', False, 0)] == [('/legacy/{path}', True, 1)]` | Fixed in `83e9a11` |
| Same fix: an opaque mount row carried no enclosing mounts, so explain stopped at it inside a sub-app | tests/fastapi/test_introspector_security.py::test_opaque_mount_inside_sub_app_is_explained | 0243173bd5449ae4f33cd8086c3cd48460ce41bd | `assert None == '/admin/legacy/{path}'` | Fixed in `83e9a11` |
| Claude #1: `vars()` ran a user `__getattribute__`/`__getattr__` (app, route subclass) | tests/fastapi/test_introspector_routes.py::test_user_getattribute_never_runs_on_any_surface | 0243173bd5449ae4f33cd8086c3cd48460ce41bd | `['app.router', ...31 more] == []` | Fixed in `83e9a11` |
| Claude #1: a raising hook broke the introspector | tests/fastapi/test_introspector_routes.py::test_user_getattribute_that_raises_degrades, ::test_slotted_app_with_raising_getattr_has_no_routes | 0243173bd5449ae4f33cd8086c3cd48460ce41bd | `isinstance('raised RuntimeError: router', FastApiIntrospector)` | Fixed in `83e9a11` |
| Claude #2: the 3.12 class-line fallback ran a class-level proxy (`__func__`, `__class__`) | tests/fastapi/test_introspection_trap.py::test_class_provider_line_never_touches_class_attributes (type()-built class: no `__firstlineno__`, the 3.12 path on every Python) | 0243173bd5449ae4f33cd8086c3cd48460ce41bd | `['__func__', '__class__'] == []` | Fixed in `83e9a11` |
| Claude #4 (low): `hasattr(obj, "__qualname__")` ran an instance's `__getattr__` | tests/fastapi/test_introspection_trap.py::test_callable_instance_provider_hook_never_runs | 0243173bd5449ae4f33cd8086c3cd48460ce41bd | `'...:_Checker' in 'raised RuntimeError: __qualname__'` | Fixed in `83e9a11` |
| Claude #5 (low): `isinstance(self.app, FastAPI)` read a user `__class__` | tests/fastapi/test_introspector_security.py::test_object_posing_as_fastapi_is_not_present | 0243173bd5449ae4f33cd8086c3cd48460ce41bd | `assert True is False` (`present`) | Fixed in `83e9a11` |
| Found in this round: explain matched every mount pattern against the full path, so a route two mounts deep was a confident "unmatched" | tests/fastapi/test_introspector_security.py::test_route_two_mounts_deep_is_explained | 5e718e4979793eda87e7540014695f52cd61c230 | `assert None == '/a/b/c'` | Fixed in `0b1f608` |

`red_check.py` said RED for all ten at their red SHA (assertion under `tests/`). Claude #6 (low, app-level `getattr`)
is fixed by the same commit (`_attrs(self.app)` for router, title, docs_url, exception_handlers, dependency_overrides,
user_middleware): `test_user_getattribute_never_runs_on_any_surface` covers it.

### Pin (Claude #3)

| Test | Mutation (reverted) | Failure under the mutation |
|---|---|---|
| tests/fastapi/test_introspection_trap.py::test_class_provider_resource_is_its_definition_line | `_first_line`: `if not inspect.isclass(target):` → `if True:` (no line for any class) | `'...test_introspection_trap.py' == '...test_introspection_trap.py:178'` (also fails `test_class_provider_line_never_touches_class_attributes`) |

## Fix round 2 (council round 2: `council-claude.md` "## Round 2")

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Claude #7: a mount adding no middleware took the chain appended last (a sibling's), so its routes and opaque/StaticFiles rows showed the sibling's filters | tests/fastapi/test_introspector_security.py::test_mount_without_middleware_keeps_its_parent_chain | ece3654d28f30adb57c1be9624d6b1531b1ef9d1 | `[('/api/ping', 1), ('/static/{path}', 1)] == [('/api/ping', 0), ('/static/{path}', 0)]` | Fixed in `564a09a` |

`red_check.py`: RED (assertion under `tests/`). Claude #8 (low, a hand-written ASGI wrapper around `StaticFiles` is
"served as is"): accepted as the reviewer suggests, a deviation-log note for the coordinator (it under-claims security;
the wrapper is listed in the chain's filters).

## Fix round 3 (council round 3)

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Claude #9: `_chains` stopped at a mount's middleware wrapper, so mounts nested in it fell to chain 0 without its middleware | tests/fastapi/test_introspector_security.py::test_mount_nested_in_a_middleware_mount_keeps_that_middleware | 6983a761c5be1b30fc1bc42aa5ace695b488220e | `() == ('starlette.middleware.gzip.GZipMiddleware',)` | Fixed in `9c8a664` |

`red_check.py`: RED (assertion under `tests/`).
