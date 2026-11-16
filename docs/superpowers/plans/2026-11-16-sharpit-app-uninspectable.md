# `--sharpit-app` Uninspectable App Implementation Plan

> For agentic workers: run `/sharpit:status --feature sharpit-app-uninspectable` for the next unchecked step. One task
> at a time; `/sharpit:check` before every commit.

**Goal:** `pytest --sharpit --sharpit-app <spec>` reports the REST API advisor as `UNKNOWN` when the named object's
routes cannot be read, never as an empty `PASSED`, and accepts a router without trying to call it.

**Architecture:** no engine change. `sharpit/fastapi/introspector.py` separates "no readable route list" (`None`) from
"empty route list" (`[]`) in one shared helper and exposes `inspectable(app)`. `sharpit/pytest_plugin/apps.py` uses it
twice: the loader never calls an inspectable object, and `_configured_models` reports `UNKNOWN` for an object that is
not inspectable. The status derivation, autodetect and installed-app snapshots stay as they are.

**Predict verdict:** CAUTION 5.6/10 (2026-11-16, five personas dispatched in parallel; scores 8, 8, 8, 8, 6, no STOP,
−2 because the Devil's Advocate found a smaller path). The mitigations are tasks 2 and 4 and the risk register.
Scenario: `2026-11-16-sharpit-app-uninspectable-scenario.md`.

Process note: the first red tests (task 1) and a first version of the fix were written before predict and scenario
ran. Predict reviewed that diff; task 2 holds what it changed.

## Global Constraints

- Runtime deps stay exactly `starlette` and `packaging`; no test dependency is added (no Flask).
- Introspection is defensive: degrade, never crash the host. No host attribute code runs to decide inspectability.
- Secrets masked before any output: the new reason goes through the report masker.
- An explicit route-less FastAPI app stays the confirmed-empty `PASSED` (0.3.0 spec, §6).
- A crash is not a red; one condition per assert; `red_check.py` before every `test:` commit.
- Every pytest run passes `-n`. Explicit `git add` paths. No AI attribution.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| High | The fix makes a green run `unknown` for a suite that named a non-app object | Changelog entry; the reason says what to pass; `--sharpit-allow-unknown` documented next to it |
| High | `router.routes` is not a list on the floor versions, so every explicit app turns `UNKNOWN` | Run the plugin app tests on `--resolution lowest-direct` locally (task 4) |
| Medium | A bare reason hides the user's mistake (factory with arguments, wrapped app, async factory) | Reason ends with `; expected an app, a router or a zero-argument factory` |
| Medium | A class holding a `routes` list is taken for an app and passes as confirmed empty | `inspectable` is false for a class; test |
| Medium | The `router` attribute rule in the loader is unpinned | Test that fails when the rule is removed |
| Low | The reason carries a host class name unmasked | Passed through the report masker; `__module__` formatted only when it is a `str` |
| Low | `bind()` proves "accepts no arguments", not "is a factory" | Stated in the PR body and in the helper's docstring |
| Low | A router pass covers less than an app pass | Changelog |

### Task 1: Red tests for the two defects and the router case

**Files:** `tests/pytest_plugin/test_plugin_apps.py`

**Interfaces:** Consumes `sharpit.pytest_plugin.apps.load_app`; the JSON report's `advisors[].status/reason/apps`.

- [x] **Step 1:** Write the pytester tests (WSGI-shaped instance, factory of an unreadable object, default gate,
  `--sharpit-allow-unknown`, router, empty FastAPI app, FastAPI factory, raising factory) and the `load_app` unit
  tests (inspectable callable, unavailable signature, needs arguments, optional arguments).
- [x] **Step 2:** `uv run python scripts/dev/red_check.py <ids>`: seven `RED (assertion under tests/)`.
- [x] **Step 3:** Commit `test: --sharpit-app on an app whose routes cannot be inspected` (2569bef3).

### Task 2: Red tests for the predict mitigations

**Files:** `tests/pytest_plugin/test_plugin_apps.py`, `tests/pytest_plugin/test_plugin_reports.py`

**Interfaces:** Consumes `sharpit.fastapi.introspector.inspectable`, `sharpit.pytest_plugin.apps._configured_models`.

- [ ] **Step 1:** Change the expected reason to
  `application routes cannot be inspected (<module.Class>); expected an app, a router or a zero-argument factory`.
- [ ] **Step 2:** `test_inspectable_is_false_for_a_class_that_holds_a_route_list`.
- [ ] **Step 3:** `test_uninspectable_reason_passes_the_report_masker` (a recording masker on the fake state).
- [ ] **Step 4:** `test_uninspectable_reason_never_formats_a_host_module_object` (non-string `__module__`).
- [ ] **Step 5:** `test_load_app_never_calls_an_object_with_a_router_attribute`; remove the rule once to see it fail.
- [ ] **Step 6:** `test_live_engine_driver_counts_as_covered` names a SQLAlchemy engine as the app to get its module
  imported; it relied on the empty pass. Add `--sharpit-allow-unknown`, keep its assertion.
- [ ] **Step 7:** `red_check.py` on the new and changed ids; commit `test: predict mitigations for the --sharpit-app fix`.

### Task 3: The fix

**Files:** `src/sharpit/fastapi/introspector.py`, `src/sharpit/pytest_plugin/apps.py`

**Interfaces:** Produces `inspectable(app: object) -> bool`. `_route_list` keeps its signature and results.

- [ ] **Step 1:** `_stored_routes(app) -> list[BaseRoute] | None`; `inspectable` (false for a class);
  `_route_list` on top of it.
- [ ] **Step 2:** `load_app`: return the object unchanged when it is inspectable, not callable, has a `router`
  attribute (`inspect.getattr_static` with a sentinel), has an unreadable signature or needs arguments
  (`inspect.signature(obj).bind()`); call it otherwise.
- [ ] **Step 3:** `_configured_models`: not inspectable → `AdvisorRun("rest-api", "UNKNOWN", …)` with the masked
  reason. The load-error branch is unchanged.
- [ ] **Step 4:** Targeted tests green with `-n auto`; `/sharpit:check`.
- [ ] **Step 5:** Commit `fix: distinguish uninspectable apps from empty apps in --sharpit-app`.

### Task 4: Docs and the special CI jobs

**Files:** `CHANGELOG.md`, `README.md`, `website/docs/pytest-plugin.md`,
`docs/superpowers/specs/2026-11-01-sharpit-0.3.0-design.md`

- [ ] **Step 1:** Changelog `[Unreleased]` → `Fixed`: the false pass, routers accepted, what can turn `unknown`.
- [ ] **Step 2:** README and website page: one sentence with the reason wording.
- [ ] **Step 3:** 0.3.0 spec §6, next to "confirmed-empty `PASSED`": name the new reason.
- [ ] **Step 4:** `lowest`, `no-sqlalchemy` and `coverage` jobs locally (`docs/development/ci.md`), each in its own
  environment.
- [ ] **Step 5:** `/sharpit:check`; commit `docs: --sharpit-app reports an uninspectable app as unknown`.

### Task 5: Review and hand-over

- [ ] **Step 1:** End to end with a real Flask app outside the repo: both `--sharpit-app` forms are `UNKNOWN`, the
  N+1 finding still appears.
- [ ] **Step 2:** `/sharpit:branch-review`.
- [ ] **Step 3:** Stop for the contributor: push and draft PR only on their word. PR body: cause, the
  `finding → test → red output` table, the limitation, the behaviour change.
