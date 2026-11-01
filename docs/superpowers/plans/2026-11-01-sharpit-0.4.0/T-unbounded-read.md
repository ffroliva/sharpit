# T-unbounded-read — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Best-effort lane 3; one task/commit at a time.

**Goal:** Flag ORM SELECTs that materialise at least twice the bound page size during a request
to an endpoint declaring paging parameters, with a marker override (spike F2).

**Architecture:** The rule **requires `sharpit.install`**: the capture middleware is what knows
the matched route and the request's bound `limit`/`page_size`, so it records a small paging
context on the request (`RequestInfo`). Without `install` (no capture middleware) the rule reports
a limitation and does not fire. Counting is per statement through a test-session-only
`InstanceEvents.load` listener (class-level on mapped classes, through `engine/sqla.py`): each
load increments the counter of the statement currently executing in that request. This is a
separate listener from T-n-plus-one-message's `SessionEvents.do_orm_execute` (which identifies
lazy relationships); a lookup-table query is its own statement, so it never adds to another's
count. Page size is never inferred when none is bound.

**Tech Stack:** Python >=3.12, SQLAlchemy 2 optional, pytest, Starlette/FastAPI adapter
metadata.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §5.5 F2 (r5), §6.3,
§10.2–10.3, §11.

## Header and ownership

- **Lane:** `T-unbounded-read` (best effort 3; F2). Evidence folder
  `.superpowers/sdd/0.4.0/lanes/T-unbounded-read/`.
- **Worker profile:** L, judgement-heavy (request/ORM correlation and conservative gate
  semantics).
- **Depends on:** T-swallowed-exceptions (PLAN.md). The T-* lanes are serial
  `G1G2 → T-n-plus-one-message → T-swallowed-exceptions → T-unbounded-read` because they share
  `engine/testsession/facts.py`, `engine/testsession/gates.py` and `pytest_plugin/marker.py`; this
  lane rebases onto both predecessors' `PhaseFacts`/`Budget` additions and uses G1G2's
  `evaluate_test` signature. Consumes F's F1a table (`F-foundation.md`) for the post-split
  `fastapi/capture.py` and `pytest_plugin/` modules.
- **May touch:** `src/sharpit/engine/sqla.py` (the new `InstanceEvents.load` listener, attached
  and removed with `attach_session()` `:320` / `detach_session()` `:331`);
  `src/sharpit/engine/capture/correlation.py` (`RequestInfo` at `:13` gains one optional field
  `paging: PagingContext | None = None`); `src/sharpit/fastapi/capture.py` (`CaptureMiddleware`
  at `:283`: set `paging` once the route is matched; F1a names the post-F location);
  `src/sharpit/settings.py` (one field `activity_unbounded_read_factor: int = 2`, min 2, beside
  `activity_n_plus_one_threshold` at `:82`, plus its parser row); `src/sharpit/engine/testsession/facts.py`,
  `gates.py`; `src/sharpit/pytest_plugin/marker.py`; `tests/engine/test_sqla.py`,
  `tests/engine/testsession/test_gates.py`, `tests/fastapi/test_capture_paging.py` (new),
  `tests/pytest_plugin/test_plugin_unbounded_read.py` (new); fixture
  `tests/fixtures/apps/unbounded_read/` (with a `conftest.py` that calls `sharpit.install(app)`);
  the implementer files in the lane evidence folder (C2).
- **Must not touch:** N+1 message format/fingerprint and the `do_orm_execute` listener
  (T-n-plus-one-message), other lanes' modules, `engine/guard.py`, panel routes/UI, report schema,
  `scripts/dev/lane_gate.py`, import-boundary rules, existing overhead constants, complexity/sonar
  baselines, dependency lists or `uv.lock`, `tests/test_safety_matrix.py`,
  `tests/test_masking_corpus.py` (C5), any `review.md` or `gate/` path.

## Global constraints

- `sharpit.unbounded-read` is HIGH/default-gating;
  `@pytest.mark.sharpit(allow_unbounded_read=True)` relaxes it; report-only and baselines apply.
- Fire only on routes declaring `skip`, `limit`, `offset`, `page`, or `page_size` and a SELECT
  with no SQL `LIMIT`/`FETCH`.
- Count ORM instances materialised per statement; threshold `loaded >= page_size * factor`,
  factor default 2, setting `SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR`.
- Page size comes from the request's bound `limit` or `page_size` (a positive integer); no bound
  value means no finding; never guess from `skip`, `offset` or `page`.
- **Needs `sharpit.install`.** No capture middleware → the source reports the limitation
  `"unbounded-read needs sharpit.install(app): the capture middleware supplies the route and its
  page size"` and the rule does not fire.
- No new runtime dependency; SQLAlchemy stays gated in `engine/sqla.py`; SQL and parameters
  remain masked/dropped.
- A red is the assertion that names the defect (C4); the spike test asserts the **desired**
  finding, so it is red on 0.3.0.

## Review Focus

1. **Spike F2 reproduced (canonical, PLAN.md Review Focus 7):**
   `test_spike_f2_unbounded_read_found` in Task 1 (`query.all()[skip:skip + limit]`, 52 `Team`
   loaded for a page of 5).
2. **Declared paging parameter but no bound limit/page size:**
   `test_paging_route_without_bound_page_size_does_not_guess` in Task 3.
3. **Bound zero, string, invalid or huge page size:**
   `test_page_size_binding_validation_is_conservative` in Task 3; invalid values neither crash
   nor become permissive.
4. **LIMIT/FETCH, non-paged and lookup-query controls:** `test_select_with_limit_or_fetch_is_not_flagged`,
   `test_non_paged_route_is_not_flagged`, `test_lookup_query_does_not_add_to_count` in Task 4.
5. **No `install`:** `test_without_install_reports_limitation_and_does_not_fire` in Task 3.
6. **Threshold configuration and marker:** `test_unbounded_read_factor_default_and_override`
   (Task 2), `test_allow_unbounded_read_marker` (Task 4).

---

### Task 1: Reproduce F2 in a fixture app before implementation

**Files:** Create `tests/fixtures/apps/unbounded_read/` (app + `conftest.py` calling
`sharpit.install(app)`) and `tests/pytest_plugin/test_plugin_unbounded_read.py`.

**Interfaces:** No product interface yet. The fixture models a `Team` table, a route with `skip`
and `limit`, and Python-side slicing after `.all()`; 52 rows and a requested page size of 5.

- [ ] **Step 1:** Add the fixture app and its test case without changing production code; the
  response contains the expected five teams.
- [ ] **Step 2:** Add the pytester test `test_spike_f2_unbounded_read_found`; assert the
  **desired** outcome: the report holds a `sharpit.unbounded-read` finding naming `Team`, `52`
  loaded and page size `5` (one condition per assert). Supply `--sharpit-app=fixture:app` so
  app-discovery status cannot mask the result.
- [ ] **Step 3:** Run on the base. Expected red: the assertion on the finding fails (0.3.0 has no
  such rule); the successful response and collection prove the planted case executes. Quote the
  red in `findings.md`.
- [ ] **Step 4:** Commit `test: reproduce unbounded paged-read spike`.

### Task 2: Per-statement ORM load counts in the test session

**Files:** Modify `src/sharpit/engine/sqla.py`, `src/sharpit/engine/testsession/facts.py`,
`src/sharpit/settings.py`; tests `tests/engine/test_sqla.py`, `tests/test_settings.py` (one
row); use the fixture from Task 1.

**Interfaces:** A test-session-only `InstanceEvents.load` listener (registered through
`sqla.sqlalchemy_module()` with `propagate=True` on the mapper base, removed at
`detach_session()`) increments `loads[(request_id, statement_key)][entity]`, where
`statement_key` is the statement `before_cursor_execute` (`sqla.py:153`) is executing for that
request. Add `UnboundedReadFact(route: str, statement: str, entity: str, loaded: int, page_size:
int, has_limit: bool, location: str | None)` to `PhaseFacts` (serialised for xdist). Settings
field `activity_unbounded_read_factor: int = 2` (min 2; invalid → default + warning, as
`activity_n_plus_one_threshold`).

- [ ] **Step 1: Write failing tests** `test_load_counts_are_per_statement`,
  `test_load_counts_are_scoped_to_request`, `test_multiple_entities_count_separately`,
  `test_listener_does_not_change_query_results`, `test_unbounded_read_factor_default_and_override`.
- [ ] **Step 2: Run;** expected named assertions fail (stubs), no collection errors (C4).
- [ ] **Step 3: Implement** the listener and facts; one registration only, removed with the
  session.
- [ ] **Step 4: Verify** request isolation, worker/test attribution, fact serialisation.
- [ ] **Step 5: Commit** `feat: count ORM rows loaded per statement in paged requests`.

### Task 3: Paging context from the capture middleware

**Files:** Modify `src/sharpit/engine/capture/correlation.py`, `src/sharpit/fastapi/capture.py`;
tests `tests/fastapi/test_capture_paging.py`, `tests/pytest_plugin/test_plugin_unbounded_read.py`.

**Interfaces:** `@dataclass(frozen=True) class PagingContext: route: str; parameter_names:
frozenset[str]; page_size: int | None` in `correlation.py`; `RequestInfo.paging: PagingContext |
None = None`. The middleware fills it once the route is matched, from the route's declared query
parameter names (the same reading as `ApiRouteInfo.query_params`, `engine/spi.py:40`; nothing is
called) and the request's `limit`/`page_size` query value, accepted only as a positive integer.
No route declares a paging name → `paging` stays `None`. The pytest source reports the
no-`install` limitation when no request in the session carried a `RequestInfo`.

- [ ] **Step 1: Add failing tests** `test_paging_route_without_bound_page_size_does_not_guess`,
  `test_page_size_binding_validation_is_conservative`, `test_paging_context_reset_after_exception`,
  `test_without_install_reports_limitation_and_does_not_fire`.
- [ ] **Step 2: Run;** expected context/limitation assertions fail.
- [ ] **Step 3: Implement**; never derive a page size from `page`, `skip` or `offset`.
- [ ] **Step 4: Verify** the context clears across requests and test attempts, including
  exception paths; the capture overhead test (`tests/fastapi/test_capture_overhead.py`) stays
  green unchanged.
- [ ] **Step 5: Commit** `feat: record the bound page size of paged requests`.

### Task 4: Detect and gate unbounded reads

**Files:** Modify `src/sharpit/engine/testsession/gates.py`, `src/sharpit/pytest_plugin/marker.py`,
`tests/engine/testsession/test_gates.py`; extend the Task 1 test.

**Interfaces:** Rule `sharpit.unbounded-read`; `Budget` gains `allow_unbounded_read: bool = False`
(`marker.budget_for`, `marker.py:12`, accepts the key). `evaluate_test` keeps the signature G1G2
leaves it with; it emits a HIGH finding when the request was paged, the statement has no
`LIMIT`/`FETCH` and `loaded >= page_size * factor`. Message names route, entity, loaded count and
page size, with the masked SQL and the first application location. The fingerprint uses the
statement identity (normalised shape + route), never the runtime counts.

- [ ] **Step 1:** Add `test_select_with_limit_or_fetch_is_not_flagged`,
  `test_non_paged_route_is_not_flagged`, `test_lookup_query_does_not_add_to_count`,
  `test_exact_threshold_boundary_flags`, `test_allow_unbounded_read_marker`,
  `test_unbounded_read_respects_report_only_and_baseline`.
- [ ] **Step 2:** Run; expected rule/marker assertions fail; the Task 1 spike stays red.
- [ ] **Step 3: Implement the gate and marker relax** through the existing gate path; xdist fact
  round trip covered.
- [ ] **Step 4:** Run targeted tests: `test_spike_f2_unbounded_read_found` green, controls do not
  flag.
- [ ] **Step 5: Commit** `feat: gate unbounded ORM reads on paged routes`.

## §6.1 → task (spec order; non-panel lane, `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity, `nullable.json`, field map | `N/A`: not a panel lane |
| 2 `# ported:` citations | `N/A`: no BootUI behaviour ported (spike tests cite `# spike: F2`) |
| 3 safety (`no_side_effects`, masking) | 3–4 (masked SQL; no parameters; the middleware reads only the query string; no GET/MCP surface) |
| 4 gatekeeper | 2 (`InstanceEvents.load` only in `engine/sqla.py`; boundary test green) |
| 5 overhead budget | 3 Step 4 (existing capture budget unchanged); the load listener is test-session only |
| 6 MCP read-only | `N/A`: no MCP tool |
| 7 Svelte view | `N/A`: no UI |
| 8 four gates + lowest-direct + no-SQLAlchemy | 4 (gated logs: coordinator) |
| 9 live check | `N/A`: test-session feature; the pytester spike test is the end-to-end check |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/T-unbounded-read/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open
  findings), `findings.md` (`finding → test → red output`, each row `fixed` + red-test name or
  `parked` + reason; the F2 red quoted), `field-map.md` (`N/A — not a panel lane`), `checklist.md`
  (the ten §6.1 items above in order, each with an evidence path or `N/A` + reason).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`,
  reviewer id ≠ implementer id, head SHA; `ponytail-review` too, since it touches `sqla.py` and
  the capture middleware), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path.

## Definition of done

- [ ] Task 1 reproduces F2 red on the base (52 loaded for 5) for the right reason.
- [ ] Task 2 counts per statement via `InstanceEvents.load`; one listener, removed with the
  session.
- [ ] Task 3 takes the page size only from a bound `limit`/`page_size`, resets per request, and
  reports the no-`install` limitation.
- [ ] Task 4 gates only the defined case, honours the marker, report-only and baselines.
- [ ] Incomplete best-effort work is parked with reason, evidence and next step in `handoff.md`.
