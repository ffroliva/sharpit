# Scenario: `--sharpit-app` on an app whose routes cannot be inspected

Found while investigating [#75](https://github.com/ffroliva/sharpit/issues/75) (Flask adapter). The change is in
`src/sharpit/pytest_plugin/apps.py` and `src/sharpit/fastapi/introspector.py`. Line numbers in the trace are those of
`47753e64`, the base.

## Coverage map

| Dimension | Active | Why |
|---|---|---|
| D1 Safe mode | no | activation is not touched; the pytest plugin runs with or without an active console |
| D2 Guard | no | no request path |
| D3 Masking | yes | a new reason string leaves in the JSON report, JUnit and the terminal |
| D4 Contract parity | yes | the report is a sharpit-only surface (0.3.0 spec §14), but its statuses are spec'd |
| D5 Introspection drift | yes | the fix reads `app.router.routes` and decides on it |
| D6 No side effects | yes | the loader calls host objects; the fix narrows what it calls |
| D7 OSV/EPSS | no | no network |
| D8 Host integration | yes | hand-wrapped middleware, routers, factories |
| D9 Scale | no | one object is judged once per run |
| D10 MCP/CLI parity | no | the option exists only in the pytest plugin |

## Worst-case trace

Input: `pytest --sharpit --sharpit-app pkg:create_app`, where `create_app()` returns a Flask app (any object with no
stored route list). The suite is clean.

1. `apps.py:209` `_models_to_assess`: `state.options.app` is set, so `_configured_models` runs.
2. `apps.py:163` `load_app`: `create_app` is callable and has no `router` attribute, so it is called. The Flask app
   comes back.
3. `apps.py:175`: `FastApiIntrospector(app).api_model()`.
4. `introspector.py:468` `_entries` → `introspector.py:371-379` `_route_list`: the object is not a `Starlette`, its
   stored attributes hold no `routes` list, so the result is `[]`. The same `[]` a route-less FastAPI app gives.
5. `introspector.py:448`: no entries, so `ApiModel(routes=(), exception_handlers=(), limitations=())`.
6. `apps.py:241` `run_advisors`: the guard is `not application_routes(...) and not state.options.app`. The option is
   set, so the "no routes seen" branch is skipped and `assess` runs.
7. `restapi/service.py:54`: no routes, no rule evaluated. `service.py:74`:
   `evidence(usable=False, coverage_complete=True, limitations=[])`, commented "confirmed empty".
8. `advisors/findings.py:80-92`: `coverageComplete` is true and there are no limitations, so `incomplete` is false
   and the run is `PASSED`.
9. `testsession/outcome.py:300`: no `UNKNOWN` advisor, so no unknown reason; the run exits 0 and the terminal prints
   "sharpit checked: … REST API advisor".

Finding: step 4 folds "no readable route list" into "empty route list", and every later step is correct for an
empty app. The defect is at step 4, not at the status derivation.

Second trace, same code, input `--sharpit-app pkg:app` with a Flask instance, an `APIRouter` or a hand-wrapped
`CORSMiddleware(app)`: step 2 calls the object with no arguments, `TypeError` is raised, `apps.py:183` reports
`application could not load (TypeError)`. For a router this refuses something the introspector can read.

Withdrawn: "an explicit route-less FastAPI app should be `UNKNOWN` too". The 0.3.0 spec (line 398-399) rules that it
stays the confirmed-empty `PASSED`; the fix keeps it.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D5 | factory returns an object with no stored route list | High | `UNKNOWN`, reason names the class | Integration |
| 2 | D5 | same, default gate | High | pytest exits 1; 0 with `--sharpit-allow-unknown` | Integration |
| 3 | D8 | WSGI-shaped instance named directly | High | not called, `UNKNOWN`, same reason | Integration |
| 4 | D8 | `APIRouter` with a route named directly | High | not called, assessed (`PASSED`/`FAILED`, `usable` true) | Integration |
| 5 | D4 | explicit route-less FastAPI app | High | stays `PASSED` (spec'd confirmed empty) | Integration |
| 6 | D6 | inspectable object that is also callable | High | never called | Unit |
| 7 | D6 | callable whose signature cannot be read | High | never called | Unit |
| 8 | D6 | callable that needs arguments | Medium | returned, not called; the reason says what was expected | Unit |
| 9 | D6 | not inspectable, has a `router` attribute, accepts zero arguments | Medium | never called (the old rule, kept) | Unit |
| 10 | D5 | a class whose own attributes hold a `routes` list | High | not inspectable: no confirmed-empty pass for a class | Unit |
| 11 | D3 | the reason passes the report masker | High | masked like advisor findings | Unit |
| 12 | D3 | a host class with a non-string `__module__` | Medium | no host `__str__` runs; `?` in its place | Unit |
| 13 | D8 | factory raises | Medium | `UNKNOWN`, `application could not load (<Type>)` unchanged | Integration |
| 14 | D8 | factory with optional arguments | Medium | called | Unit |
| 15 | D8 | `async def` factory (returns a coroutine) | Medium | `UNKNOWN`, was a false `PASSED`; covered by rule 1, reason names `builtins.coroutine` | covered by 1 |
| 16 | D8 | hand-wrapped app `CORSMiddleware(app)` | Medium | `UNKNOWN`; reason hint tells the user what to pass | covered by 3 |
| 17 | D8 | an existing suite names a non-app object only to import its module | Medium | becomes `UNKNOWN`: a behaviour change, in the changelog | existing test updated |
| 18 | D5 | floor versions (`fastapi 0.115`, `starlette 0.44`): is `router.routes` a list there | High | the tests pass on `--resolution lowest-direct` | CI `lowest` job, run locally |
| 19 | D8 | a zero-argument callable app instance (`__call__(self, *args)`) | Low | still called (stated limitation); result is `UNKNOWN` | none |
| 20 | D8 | a router pass covers less than an app pass (no app-level handlers) | Low | stated in the changelog | none |

Scenario 17 is real: `tests/pytest_plugin/test_plugin_reports.py::test_live_engine_driver_counts_as_covered` passes
`--sharpit-app=appmod:engine` (a SQLAlchemy `AsyncEngine`) to get the module imported, and relied on the empty pass.

## Must-cover before merge

- `test_sharpit_app_factory_of_an_uninspectable_app_is_unknown`
- `test_sharpit_app_uninspectable_app_fails_the_run_by_default`
- `test_sharpit_app_uninspectable_app_is_tolerated_with_allow_unknown`
- `test_sharpit_app_instance_without_a_route_list_is_uninspectable`
- `test_sharpit_app_router_is_assessed`
- `test_sharpit_app_empty_fastapi_app_is_a_confirmed_empty_pass`
- `test_load_app_never_calls_an_inspectable_object`
- `test_load_app_never_calls_a_callable_with_an_unavailable_signature`
- `test_inspectable_is_false_for_a_class_that_holds_a_route_list`
- `test_uninspectable_reason_passes_the_report_masker`
- the `lowest` CI job, locally, for the plugin app tests

## Deferred

- Unwrapping hand-wrapped middleware to reach the inner app.
- The neighbouring reason `application could not load (<Type>)` and the app spec are not masked either
  (`apps.py:183`); it predates this change.
- A framework adapter lookup in place of the direct `FastApiIntrospector` import (ROADMAP, after 0.7.0).

## Known-issues cross-reference

- No `KNOWN_ISSUES.md` in the repo.
- [#65](https://github.com/ffroliva/sharpit/issues/65): a run exits 1 when an advisor can only partly assess the app.
  Its proposal keeps "nothing was assessed" as exit 1, which is this case; no conflict.
- MVP spec §14/§15: nothing on `--sharpit-app`. The 0.3.0 spec §14 row "unknown, not pass" covers the direction.
