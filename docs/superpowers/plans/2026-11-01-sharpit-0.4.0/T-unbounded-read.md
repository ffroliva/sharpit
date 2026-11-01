# T-unbounded-read — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Best-effort lane 3; one task/commit at a time.

**Goal:** Flag ORM SELECTs that materialize at least twice the bound page size on endpoints
declaring paging parameters, with a marker override.

**Architecture:** Reuse the test-session ORM instance-load hooks and attribution added by
T-n-plus-one-message; correlate those loads with request route metadata and the current bound
`limit`/`page_size`. Keep SQL inspection inside the engine gatekeeper and count materialized ORM
instances only; do not infer a page size when none is bound.

**Tech Stack:** Python >=3.12, SQLAlchemy 2 optional, pytest, Starlette/FastAPI adapter
metadata.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§5.5 F2, 6.3, 10.2–10.3.

## Header and ownership

- **Lane:** T-unbounded-read (best effort 3; F2).
- **Worker profile:** L, judgement-heavy (request/ORM correlation and conservative gate
  semantics).
- **Dependencies:** F and T-n-plus-one-message merged; F5 supplies ORM load hooks. G1G2 is
  merged first for report-only/baseline gate behavior.
- **May touch:** `src/sharpit/engine/sqla.py` only to extend T-n-plus-one-message hooks;
  `src/sharpit/engine/spi.py` (`ApiRouteInfo.query_params`, line 29) only if additional declared
  parameter metadata is essential; `src/sharpit/engine/testsession/facts.py`, `gates.py`;
  `src/sharpit/pytest_plugin/marker.py`, request/ORM attribution module; post-F
  `src/sharpit/fastapi/` request metadata module if available; `tests/engine/test_sqla.py`,
  `tests/engine/testsession/test_gates.py`, new
  `tests/pytest_plugin/test_plugin_unbounded_read.py`; fixture
  `tests/fixtures/apps/unbounded_read/`; lane evidence folder.
- **Must not touch:** N+1 message format/fingerprint, other lanes' modules, `engine/guard.py`,
  panel routes/UI, report schema unless coordinated with G1G2, `scripts/dev/lane_gate.py`,
  import-boundary rules, overhead constants, complexity/sonar baselines, dependency lists or
  `uv.lock`.

## Global constraints

- `sharpit.unbounded-read` is HIGH/default-gating;
  `@pytest.mark.sharpit(allow_unbounded_read=True)` relaxes it.
- Fire only on routes declaring `skip`, `limit`, `offset`, `page`, or `page_size` and a SELECT
  with no SQL `LIMIT`/`FETCH`.
- Count ORM instances materialized; threshold is `loaded >= page_size * factor`, factor default
  2 and configurable by `SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR`.
- Page size comes from the request's bound `limit` or `page_size`. No bound value means no
  finding; do not guess from `skip`, `offset`, or page number.
- No new runtime dependency; SQLAlchemy stays gated in `engine/sqla.py`; SQL and parameters
  remain masked/dropped.

## Review Focus

1. **Spike's `query.all()[skip:skip + limit]` behavior:**
`test_spike_f2_flags_52_loaded_for_page_of_5` in Task 3.
2. **Declared paging parameter but no bound limit/page size:**
`test_paging_route_without_bound_page_size_does_not_guess` in Task 2.
3. **Bound zero, string, invalid or huge page size:**
`test_page_size_binding_validation_is_conservative` in Task 2; invalid values do not crash or
become permissive.
4. **LIMIT/FETCH and non-paged controls:** `test_select_with_limit_or_fetch_is_not_flagged`,
`test_non_paged_route_is_not_flagged` in Task 3.
5. **Threshold configuration and marker:** `test_unbounded_read_factor_default_and_override`,
`test_allow_unbounded_read_marker` in Tasks 1 and 3.

---

### Task 1: Reproduce F2 in a fixture app before implementation

**Files:** Create `tests/fixtures/apps/unbounded_read/` and
`tests/pytest_plugin/test_plugin_unbounded_read.py`.

**Interfaces:** No product interface yet. The fixture models a `Team` table, a route with `skip`
and `limit`, and Python-side slicing after `.all()`; use 52 rows and a requested page size of 5.

- [ ] **Step 1:** Add the fixture app and test case without changing production code; response
  contains the expected five teams.
- [ ] **Step 2:** Add `test_spike_f2_flags_52_loaded_for_page_of_5`; assert there is no
  `sharpit.unbounded-read` finding in current sharpit and the report remains `pass`.
  Supply `--sharpit-app=fixture:app` so unrelated app-discovery unknown status cannot mask the
  missing F2 finding.
- [ ] **Step 3:** Run against 0.3.0. Expected red is the assertion that sharpit emits the
  unbounded-read finding; the successful response and pytest collection prove the planted case
  executes.
- [ ] **Step 4:** Commit `test: reproduce unbounded paged-read spike`.

### Task 2: Extend F5 ORM events with per-request instance counts

**Files:** Modify `src/sharpit/engine/sqla.py`, `src/sharpit/engine/testsession/facts.py`, the
F5 ORM attribution module, and `tests/engine/test_sqla.py`; use fixture from Task 1.

**Interfaces:** Consume T-n-plus-one-message listener lifecycle and test tag. Add
`UnboundedReadFact(route: str, statement: str, entity: str, loaded: int, page_size: int,
location: str | None)` to per-test facts; add request-scoped counters keyed by request/test and
SELECT identity. Adapter supplies route parameter names and bound scalar values; engine receives
only values needed for rule evaluation.

- [ ] **Step 1: Write failing unit tests** `test_load_counts_are_scoped_to_request`,
  `test_multiple_entities_count_separately`, `test_listener_does_not_change_query_results`, and
  `test_unbounded_read_factor_default_and_override`; expected fact/config behavior does not
  exist.
- [ ] **Step 2: Run tests;** expected named assertions fail, no collection errors.
- [ ] **Step 3: Extend the existing T-n-plus-one listener** to count materialized ORM instances
  by SELECT and entity within request context; avoid duplicate listener registration and retain
  cleanup semantics.
- [ ] **Step 4: Verify** request isolation, worker/test attribution, and fact serialization.
- [ ] **Step 5: Commit** `feat: count ORM rows loaded for paged requests`.

### Task 3: Supply conservative paged-route context and gate option

**Files:** Modify post-F request metadata hook (or create
`src/sharpit/fastapi/paging_context.py` if F provides no such hook),
`src/sharpit/engine/testsession/gates.py`, `src/sharpit/pytest_plugin/marker.py`, and tests
`tests/pytest_plugin/test_plugin_unbounded_read.py`.

**Interfaces:** Add `PagingRequest(route: str, parameter_names: frozenset[str], bound_values:
Mapping[str, object])`; adapter sets/resets it around request handling without invoking route
code. Add `allow_unbounded_read: bool = False` to `Budget`; marker parser accepts the new key.
Factor resolves from `SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR`, default 2.

- [ ] **Step 1: Add failing tests** from Review Focus 2, 3 and 5; test parameter-name matching
  and request-context reset after exception.
- [ ] **Step 2: Run on 0.3.0;** expected rule/marker/config assertions fail; the no-page-size
  control has no finding.
- [ ] **Step 3: Implement route and bound parameter capture.** Take page size only from bound
  `limit` or `page_size`; accept only a positive integer. Do not derive from `page`, `skip`, or
  `offset`.
- [ ] **Step 4: Verify** context clears across requests and test attempts, including exception
  paths.
- [ ] **Step 5: Commit** `feat: capture bounded page context for ORM reads`.

### Task 4: Detect and gate unbounded reads

**Files:** Modify `src/sharpit/engine/testsession/gates.py`, ORM fact serialization/formatting
module from Task 2, and `tests/engine/testsession/test_gates.py`; extend Task 1 fixture/test.

**Interfaces:** Add rule `sharpit.unbounded-read`; extend existing `evaluate_test(...)` using
Task 1 facts and Task 2 `PagingRequest`. Emit HIGH finding if paged route, no `LIMIT`/`FETCH`,
and `loaded >= page_size * factor`. Message names route, entity, loaded count and page size;
include masked SQL and first application location where available. Fingerprint uses stable
statement identity, not runtime count/page values.

- [ ] **Step 1:** Add controls for `LIMIT`, `FETCH`, non-paged route and exact threshold
  boundary; assert default factor 2 and configured-factor behavior.
- [ ] **Step 2:** Run the spike and control cases; the Task 1 test is already confirmed red on
  0.3.0 for the missing finding.
- [ ] **Step 3: Implement the gate and marker relax**; preserve report-only/baseline behavior
  through the existing gate path and add xdist fact round-trip coverage.
- [ ] **Step 4:** Run targeted tests; expect the spike case to flag and controls not to flag.
- [ ] **Step 5: Commit** `feat: gate unbounded ORM reads on paged routes`.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/T-unbounded-read/` must contain `handoff.md`, `review.md` (fresh
reviewer, distinct id, head SHA, final line `VERDICT: APPROVE`), `findings.md` (finding → test →
red output; fixed or parked), `field-map.md` (`N/A — no panel DTO change; map finding fields to
Finding DTO`), `checklist.md` mapping gate, masking, optional-library and test-session safety
evidence, and `gate/` logs for four gates plus lowest-direct/no-SQLAlchemy pinned to head SHA.

## Definition of done

- [ ] Task 1 reuses T-n-plus-one-message ORM load hooks; no duplicate global listeners remain
  attached.
- [ ] Task 2 obeys route/page-size conditions, resets request state and accepts marker/config
  override.
- [ ] Task 3 reproduces F2 red on 0.3.0 (52 loaded for 5), gates only the defined case, and
  respects report-only/baselines.
- [ ] Incomplete best-effort work is parked with reason, evidence and next step in `handoff.md`.
