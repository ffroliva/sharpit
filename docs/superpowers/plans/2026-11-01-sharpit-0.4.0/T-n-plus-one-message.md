# T-n-plus-one-message — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Best-effort lane 4 (PLAN.md); one task/commit at a time.

**Goal:** Make SQLAlchemy N+1 findings identify the lazy relationship, show the masked query and
first application source location, while keeping the existing fingerprint stable and query-heavy
overhead within budget (spike F5 + F6).

**Architecture:** Extend the SQLAlchemy bridge in `engine/sqla.py` with one test-session-only
`SessionEvents.do_orm_execute` listener (class-level on `sqlalchemy.orm.Session`). For a lazy
load (`orm_execute_state.is_relationship_load`) it reads `lazy_loaded_from` (the parent
`InstanceState`) and `loader_strategy_path` (its last element is the `RelationshipProperty`),
and tags the statement with `orm_execute_state.update_execution_options(sharpit_relationship=…)`.
The existing `before_cursor_execute` (`sqla.py:153`) reads the tag back from
`context.execution_options` and records the relationship identity next to the statement group it
already counts. `prop.direction` (`ONETOMANY`/`MANYTOMANY` → collection, `MANYTOONE` →
many-to-one) picks the loader hint. Not `InstanceEvents.load` (that is T-unbounded-read's counter,
per statement). Aggregates go into per-test facts; only the finding message/details are
enriched, `sharpit.n-plus-one` identity stays the normalised statement fingerprint. The bridge
remains the optional-library gatekeeper.

**Tech Stack:** Python >=3.12, SQLAlchemy 2 optional, pytest, existing paired overhead harness.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §5.5 F5–F6 (r5), §6.3,
§10.2–10.3, §11.

## Header and ownership

- **Lane:** `T-n-plus-one-message` (best effort 4). Evidence folder
  `.superpowers/sdd/0.4.0/lanes/T-n-plus-one-message/`.
- **Worker profile:** L, judgement-heavy (ORM event lifecycle, relationship attribution,
  hot-path budget).
- **Depends on:** G1G2, A-sqlalchemy-statistics, A-postgresql (PLAN.md; R0 chain `A-postgresql → T-n-plus-one-message`). G1G2: the T-* lanes are serial
  `G1G2 → T-n-plus-one-message → T-swallowed-exceptions → T-unbounded-read` because they share
  `engine/testsession/facts.py`, `engine/testsession/gates.py` and `pytest_plugin/marker.py`.
  A-sqlalchemy-statistics: both lanes extend the SQL recorder path (that lane adds lifetime
  totals to `SqlTraceRecorder.record`; this one adds relationship tagging on the statement
  listeners in `sqla.py`), so this lane rebases onto it. Consumes these rows of F's consumer
  interface table (`F-foundation.md`): `sharpit.pytest_plugin.session` and
  `sharpit.engine.testsession.gates.evaluate_test`; and G1G2's `gates.py::fails(dto)` predicate
  (a relationship finding stays `HIGH`, so it fails as today's N+1 does).
- **Start gate (O1, R0):** `engine/sqla.py` is owned by A-postgresql (`run_db_read` keywords,
  `bounded_read_only`), and the two May-touch lists intersect on it, so they never run at the
  same time. This lane starts only after A-postgresql has merged or parked, and edits `sqla.py`
  on top of that merge; the coordinator compares the lists before launch. If A-postgresql is
  still in flight, this lane waits (it is best effort; nothing is gained by racing the owner of
  `sqla.py`). The same gate applies to T-unbounded-read, which also edits `sqla.py`.
- **May touch:** `src/sharpit/engine/sqla.py`, subject to the start gate (`attach_session()` at
  `:320`, `detach_session()` at `:331`, `_LISTENERS`/`_sync_listeners` at `:256-281`,
  `before_cursor_execute` at `:153`, `_emit` at `:195`; the new `do_orm_execute` listener), never
  F's `add_connection_listener` slot or A-postgresql's read helpers; `src/sharpit/engine/testsession/facts.py` (`PhaseFacts` at
  `:56`, `TestFacts` at `:87`); `src/sharpit/engine/testsession/gates.py` (`evaluate_test` at
  `:34`, the `N_PLUS_ONE` branch at `:46-51`); `src/sharpit/pytest_plugin/session.py` (F's `sharpit.pytest_plugin.session` row) only to call
  the new `sqla` lifecycle helper;
  `tests/engine/test_sqla.py`, `tests/engine/testsession/test_gates.py`,
  `tests/engine/test_n_plus_one_overhead.py` (new), `tests/pytest_plugin/test_plugin_gates.py`;
  fixture app `tests/fixtures/apps/n_plus_one/` (new, Task 1); the implementer files in the lane
  evidence folder (C2).
- **Must not touch:** `README.md`, `skills/sharpit/SKILL.md`, `examples/`,
  `tests/test_example_app.py` (O3: user-facing text goes to the lane folder's `docs.md`), other
  lanes' modules, `engine/tools.py` (R3), `engine/guard.py`, report/baseline schema or
  fingerprints, panel modules/UI, `engine/capture/sqltrace.py` (A-sqlalchemy-statistics owns it),
  `scripts/dev/lane_gate.py`, import-boundary rules, existing overhead budget constants,
  complexity/sonar baselines, dependency lists, `uv.lock`, `tests/test_safety_matrix.py`,
  `tests/test_masking_corpus.py` (C5), any `review.md` or `gate/` path.

## Global constraints

- SQLAlchemy is imported only through `engine/sqla.py`; no new runtime dependency.
- Hooks attach only during pytest test sessions (`attach_session`) and detach at session end
  (`detach_session`); failures cannot change host query behaviour (a raising listener warns once,
  query result unchanged).
- Mask SQL before report output; parameters are never retained.
- Existing fingerprint remains based on normalised statement shape; never raise an overhead
  budget.
- A red is the assertion that names the defect (C4); the spike test asserts the **desired**
  message, so it is red on 0.3.0.
- Each task's red is a **red commit** (R2): subject starts `test:`, holding the failing tests plus the
  minimal stubs that make them import; a stub returns a wrong value (an empty `Counter`/`dict`, the old
  statement message), it never raises `NotImplementedError`. Its SHA per red test goes into `findings.md`
  and `handoff.md`; `lane_gate.py` replays each test at that SHA with `--junitxml` (needs a `<failure>`
  starting `AssertionError`) and again at the lane head (must pass). The "Run on the base" steps below
  mean this red commit; a review-finding red is replayed on the parent of its fix commit.

## Review Focus

1. **Spike F5 reproduced (canonical, PLAN.md Review Focus 7):**
   `test_spike_f5_message_names_relationship` in Task 1.
2. **Relationship evidence vs repeated statement without ORM relationship evidence:**
   `test_n_plus_one_names_lazy_relationship_or_keeps_statement_fallback` in Task 2.
3. **Collections vs many-to-one, sync and async loads:**
   `test_lazy_load_reports_suggested_loader_by_direction`, `test_async_lazy_load_is_attributed`
   in Task 2; empty collections still count (`do_orm_execute` fires once per lazy-load SELECT).
4. **Application frame filtering and absent app frame:**
   `test_first_lazy_load_uses_innermost_application_frame`, `test_no_application_frame_is_null`
   in Task 2 (frame rule: `engine/capture/frames.py:21::is_application_frame`).
5. **Session lifecycle and listener failure:** `test_orm_hooks_attach_only_for_test_session`,
   `test_listener_failure_does_not_change_query_result` in Task 1.
6. **Query-heavy regression (F6):** `test_sqlalchemy_orm_hook_overhead_budget` in Task 3 using
   `tests/overhead.py::paired` (`:65`) and `check_budget` (`:38`).

---

### Task 1: Reproduce F5 and add bounded relationship-load facts

**Files:** Create fixture app `tests/fixtures/apps/n_plus_one/`; modify
`src/sharpit/engine/sqla.py` and `src/sharpit/engine/testsession/facts.py`; tests
`tests/engine/test_sqla.py`, `tests/pytest_plugin/test_plugin_gates.py`.

**Interfaces:** `sqla.attach_session() -> bool` / `sqla.detach_session() -> None` remain the
entry points; they also add/remove the `do_orm_execute` listener on `sqlalchemy.orm.Session`
(through `sqla.sqlalchemy_module()`, never `import sqlalchemy`). Execution-option key
`RELATIONSHIP_KEY = "sharpit_relationship"`, value `(identity: str, collection: bool)` with
identity `"<Model>.<relationship>"` (`lazy_loaded_from.class_.__name__` +
`loader_strategy_path[-1].key`). `before_cursor_execute` reads
`context.execution_options.get(RELATIONSHIP_KEY)` and passes it with the statement it already
records. Add `PhaseFacts.relationship_loads: Counter[str]`, `relationship_of: dict[str, tuple[str,
bool]]` (statement group → identity, collection) and `relationship_sites: dict[str, str | None]`
(identity → first application location); serialised and restored with the other `PhaseFacts`
fields (xdist round trip).

- [ ] **Step 1: Build the fixture first and write the failing pytester test**
  `test_spike_f5_message_names_relationship`. Mirror spike T1 (`Player.performances`, 1,018 lazy
  loads); assert the **desired** finding message contains `Player.performances lazy-loaded 1018
  times` and `selectinload(Player.performances)` (one assert each, PT018). Keep the
  SQLAlchemy/SQLite fixture deterministic and run its normal app query. Run with
  `--sharpit-no-advisors --sharpit-allow-unknown` so app discovery does not obscure the result.
- [ ] **Step 2: Commit the red** (`test: reproduce n+1 message spike F5`, with the empty `PhaseFacts`
  fields and `RELATIONSHIP_KEY` as wrong-value stubs) and run it. Expected red: the assertion on `Player.performances` fails
  because 0.3.0 emits only `1018 executions of one SELECT in the call phase`; the N+1 gate itself
  still fires (a separate control assert). Quote the red in `findings.md`.
- [ ] **Step 3: Implement** the `do_orm_execute` listener and the `before_cursor_execute`
  read-back in `sqla.py`, and the `PhaseFacts` fields; attribute to the current test tag; remove
  the listener when the session detaches. A failed listener warns once and leaves query results
  unchanged.
- [ ] **Step 4: Verify** `test_orm_hooks_attach_only_for_test_session`,
  `test_listener_failure_does_not_change_query_result`, the facts serialisation round trip, and
  `test_spike_f5_message_names_relationship` green after Task 2.
- [ ] **Step 5: Commit** `feat: capture SQLAlchemy lazy relationship loads`.

### Task 2: Render actionable relationship finding

**Files:** Modify `src/sharpit/engine/testsession/gates.py`; tests
`tests/engine/testsession/test_gates.py`, `tests/pytest_plugin/test_plugin_gates.py`, and the
fixture from Task 1.

**Interfaces:** `evaluate_test` keeps the signature G1G2 leaves it with (today
`evaluate_test(facts: TestFacts, budget: Budget, n_plus_one_threshold: int, dismissed:
Collection[str]) -> list[Finding]`, `gates.py:34`, plus G1G2's optional baseline keyword); this
lane adds no parameter. For relationship-tagged groups, `Finding.message` includes
`<Model>.<relationship> lazy-loaded <N> times`, the masked statement and the loader hint
(`selectinload(Model.relationship)` for a collection; `joinedload(Model.relationship)` for
many-to-one, from `prop.direction`), and the first application location. Untagged N+1 groups keep
today's statement message. Message keys are additive; the fingerprint is unchanged.

- [ ] **Step 1: Add failing tests** from Review Focus 2–4 and
  `test_statement_fingerprint_unchanged_with_relationship_detail`; assert `Player.performances`,
  count, masked SQL, suggestion, location, and equal fingerprint after message enrichment (one
  condition per assert).
- [ ] **Step 2: Commit the red** (`test: relationship n+1 message reds`; the render helper is a stub that returns
  today's statement message) and run it; expected relationship/message/location assertions fail, while
  the fingerprint control passes.
- [ ] **Step 3: Implement rendering** from Task 1 facts; never put raw parameters or credentials
  in a message.
- [ ] **Step 4: Verify** ORM and sqlite-only fallback messages, report serialisation and
  fingerprint stability.
- [ ] **Step 5: Commit** `feat: explain SQLAlchemy N+1 relationships`.

### Task 3: Pin the query-heavy overhead budget (F6)

**Files:** Create/modify `tests/engine/test_n_plus_one_overhead.py`; reuse
`tests/overhead.py::paired` and `check_budget`; reference `docs/development/overhead-budgets.md`.

**Interfaces:** Paired rounds of the query-heavy workload with sharpit off/on (ORM hooks
attached). Spec F6 targets about 35,000 SELECTs; **a smaller workload with the same
per-statement overhead ratio is allowed** so the test stays fast on every CI leg (spec §5.5 F6,
logged in §11). Pin the per-statement ratio at the measured value plus the usual margin. A new
constant in the new file; no shared budget constant changes. No production API change.

- [ ] **Step 1: Add the failing budget assertion** `test_sqlalchemy_orm_hook_overhead_budget`;
  assert the workload's query count independently (so a shortened run cannot pass), then prove it
  bites (temporary `time.sleep` in the listener → FAIL, removed).
- [ ] **Step 2: Measure** in the lane run; record off/on rounds, noise and the chosen workload
  size in `handoff.md` and `checklist.md` item 5. Spike reference: 23.5 s plain, 39.3 s sharpit,
  38.4 s queryguard.
- [ ] **Step 3: Keep the measured threshold in the test**; margin per
  `docs/development/overhead-budgets.md`.
- [ ] **Step 4: Verify** the test stays selected in normal pytest jobs (never marked slow or
  deselected) and run the four gates locally.
- [ ] **Step 5: Commit** `test: budget SQLAlchemy ORM observation overhead`.

## §6.1 → task (spec order; non-panel lane, `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity, `nullable.json`, field map | `N/A`: not a panel lane |
| 2 `# ported:` citations | `N/A`: no BootUI behaviour ported (F5 tests cite the spike: `# spike: F5 T1`) |
| 3 safety (`no_side_effects`, masking) | 2 (masked statement, no parameters in the message); no GET/MCP surface |
| 4 gatekeeper | 1 (`do_orm_execute` only in `engine/sqla.py`; boundary test green) |
| 5 overhead budget | 3 |
| 6 MCP read-only | `N/A`: no MCP tool |
| 7 Svelte view | `N/A`: no UI |
| 8 four gates + lowest-direct + no-SQLAlchemy | 3 Step 4 (gated logs: coordinator) |
| 9 live check | `N/A`: test-session feature; the pytester spike test is the end-to-end check |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/T-n-plus-one-message/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open
  findings, measured overhead), `findings.md` (`finding → test → red output`, each row `fixed` +
  red-test name or `parked` + reason; the F5 red quoted), `field-map.md` (`N/A — not a panel
  lane`), `checklist.md` (the ten §6.1 items above in order, each with an evidence path or `N/A`
  + reason).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`,
  reviewer id ≠ implementer id, head SHA; `ponytail-review` too, since it touches `sqla.py`),
  `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path.

## Definition of done

- [ ] Task 1 reproduces F5 (red on the base for the right reason) and collects relationship facts
  from `do_orm_execute` only during a test session.
- [ ] Task 2 reports relationship, masked statement, correct loader suggestion, first
  application location; stable fingerprint.
- [ ] Task 3 pins the query-heavy overhead without raising or deselecting a budget.
- [ ] Any unfinished best-effort item is parked with reason and exact next step in `handoff.md`.
