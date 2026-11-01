# T-n-plus-one-message — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans. Best-effort lane 1; one task/commit at a time.

**Goal:** Make SQLAlchemy N+1 findings identify the lazy relationship, show the masked query and
first application source location, while keeping the existing fingerprint stable and query-heavy
overhead within budget.

**Architecture:** Extend the SQLAlchemy bridge in `engine/sqla.py` with test-session-only ORM
load/lazy-load observation. Aggregate relationship counts and first application frame into
per-test facts; enrich only the finding message/details, preserving `sharpit.n-plus-one`
identity as the normalized statement fingerprint. The bridge remains the optional-library
gatekeeper.

**Tech Stack:** Python >=3.12, SQLAlchemy 2 optional, pytest, existing paired overhead harness.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§5.5 F5–F6, 6.3,
10.2–10.3.

## Header and ownership

- **Lane:** T-n-plus-one-message (best effort 1).
- **Worker profile:** L, judgement-heavy (ORM event lifecycle, relationship attribution,
  hot-path budget).
- **Dependencies:** F and A-sqlalchemy-statistics merged; F5 precedes T-unbounded-read, which
  consumes its ORM load hooks. Best-effort lane per §2.
- **May touch:** `src/sharpit/engine/sqla.py` (`attach_session()` line 320 and shared listener
  registration); `src/sharpit/engine/testsession/facts.py` (`PhaseFacts`, `TestFacts`);
  `src/sharpit/engine/testsession/gates.py` (`evaluate_test`, line 34); existing
  `src/sharpit/pytest_plugin/` session wiring only if it needs to call the new `sqla` lifecycle
  helper; `tests/engine/test_sqla.py`,
  `tests/engine/testsession/test_gates.py`, new `tests/engine/test_n_plus_one_overhead.py`,
  `tests/pytest_plugin/test_plugin_gates.py`; fixture app under
  `tests/fixtures/apps/n_plus_one/` (create in Task 1); lane evidence folder.
- **Must not touch:** Other lanes' modules, `engine/guard.py`, report/baseline schema or
  fingerprints, panel modules/UI, `scripts/dev/lane_gate.py`, import-boundary rules, overhead
  budget constants, complexity/sonar baselines, dependency lists, `uv.lock`.

## Global constraints

- SQLAlchemy is imported only through `engine/sqla.py`; no new runtime dependency.
- Hooks attach only during pytest test sessions and detach at session end; failures cannot
  change host query behavior.
- Mask SQL before report output; parameters are never retained.
- Existing fingerprint remains based on normalized statement shape; never raise an overhead
  budget.

## Review Focus

1. **Relationship evidence vs repeated statement without ORM relationship evidence:**
`test_n_plus_one_names_lazy_relationship_or_keeps_statement_fallback` in Task 2.
2. **Collections vs many-to-one, sync and async loads:**
`test_lazy_load_reports_suggested_loader_by_direction`, `test_async_lazy_load_is_attributed` in
Task 2.
3. **Application frame filtering and absent app frame:**
`test_first_lazy_load_uses_innermost_application_frame`, `test_no_application_frame_is_null` in
Task 2.
4. **Session lifecycle and listener failure:** `test_orm_hooks_attach_only_for_test_session`,
`test_listener_failure_does_not_change_query_result` in Task 1.
5. **35,000 SELECT regression:** `test_sqlalchemy_orm_hook_overhead_budget` in Task 3 using
`tests/overhead.py::paired` and `check_budget`.

---

### Task 1: Reproduce F5 and add bounded ORM load facts

**Files:** Create fixture app `tests/fixtures/apps/n_plus_one/` and
`tests/engine/test_n_plus_one_overhead.py`; modify `src/sharpit/engine/sqla.py` and
`src/sharpit/engine/testsession/facts.py`; test `tests/engine/test_sqla.py`.

**Interfaces:** `sqla.attach_session() -> bool` remains the entry point; add private
attach/detach of SQLAlchemy instance/attribute listeners paired with existing test-session
start/stop calls. Add `PhaseFacts.relationship_loads: Counter[str]`,
`relationship_sql: dict[str, str]`, `relationship_sites: dict[str, str | None]`.
Listener records only current test tag, relationship identity, masked statement text and first
application location.

- [ ] **Step 1: Build the fixture first and write failing pytester test**
  `test_spike_f5_names_player_performances`. Mirror spike T1 (`Player.performances`, 1,018 lazy
  loads); assert current 0.3.0 emits only `1018 executions of one SELECT in the call phase`,
  with no relationship name, suggestion or app source. Keep SQLAlchemy/SQLite fixture
  deterministic and execute its normal app query. Run with `--sharpit-no-advisors
  --sharpit-allow-unknown` so app discovery does not obscure the N+1 message result.
- [ ] **Step 2: Run on 0.3.0.** Expected red: the message lacks `Player.performances`; the
  existing N+1 gate itself still fires.
- [ ] **Step 3: Implement test-session listener facts** in `sqla.py` and `PhaseFacts`; correlate
  load callbacks to `TEST` tag and remove listeners when the session detaches. A failed optional
  listener warns once and leaves query results unchanged.
- [ ] **Step 4: Verify** listener attach/detach, test attribution, serialization round trip, and
  exception isolation with named tests in Review Focus.
- [ ] **Step 5: Commit** `feat: capture SQLAlchemy lazy relationship loads`.

### Task 2: Render actionable relationship finding

**Files:** Modify `src/sharpit/engine/testsession/gates.py`; tests
`tests/engine/testsession/test_gates.py`, `tests/pytest_plugin/test_plugin_gates.py`, and
fixture from Task 1.

**Interfaces:** Extend `evaluate_test(facts: TestFacts, budget: Budget, n_plus_one_threshold:
int, dismissed: Collection[str]) -> list[Finding]` without changing parameters. For ORM-backed
groups, `Finding.message` includes `<Model>.<relationship> lazy-loaded <N> times`, masked
statement and loader hint (`selectinload(Model.relationship)` for collection;
`joinedload(Model.relationship)` for many-to-one), and first application frame. Non-ORM N+1
groups retain the current statement fallback. Fingerprint remains unchanged.

- [ ] **Step 1: Add failing tests** from Review Focus and
  `test_statement_fingerprint_unchanged_with_relationship_detail`; assert `Player.performances`,
  count, masked SQL, suggestion, location, and equal fingerprint after message enrichment.
- [ ] **Step 2: Run tests against 0.3.0;** expected relationship/message/location assertions
  fail, while fingerprint control passes.
- [ ] **Step 3: Implement rendering** from Task 1 facts; never put raw parameters or credentials
  in a message.
- [ ] **Step 4: Verify** ORM and sqlite-only fallback messages, report serialization and
  fingerprint stability.
- [ ] **Step 5: Commit** `feat: explain SQLAlchemy N+1 relationships`.

### Task 3: Pin the query-heavy overhead budget

**Files:** Modify `tests/engine/test_n_plus_one_overhead.py`; reuse `tests/overhead.py::paired`
and `check_budget`; reference `docs/development/overhead-budgets.md`.

**Interfaces:** Run the same approximately 35,000 SELECT workload with ORM hooks off/on and
sharpit off/on in paired rounds; pin per-statement overhead to measured lane results plus the
usual margin. No production API changes.

- [ ] **Step 1: Add failing budget assertion** `test_sqlalchemy_orm_hook_overhead_budget`;
  retain Task 1 fixture and independently verify query count so a shortened workload cannot
  pass.
- [ ] **Step 2: Measure the baseline in the lane run** and record off/on rounds and noise in
  `handoff.md`; spike reference is 23.5 s plain, 39.3 s sharpit, 38.4 s queryguard.
- [ ] **Step 3: Keep the measured threshold in the test** without changing shared budget
  constants; allowed margin follows `docs/development/overhead-budgets.md`.
- [ ] **Step 4: Verify** the test stays selected in normal pytest jobs and run lane gates.
- [ ] **Step 5: Commit** `test: budget SQLAlchemy ORM observation overhead`.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/T-n-plus-one-message/` must contain `handoff.md`, `review.md`
(fresh reviewer, different id, head SHA, final line `VERDICT: APPROVE`), `findings.md` (each
finding fixed with red-test/output or parked with reason), `field-map.md` (`N/A — no panel DTO
change; map message details to `Finding.message`), `checklist.md` with applicable
safety/performance evidence and non-panel items marked N/A, and `gate/` logs for four gates plus
lowest-direct and no-SQLAlchemy pinned to head SHA.

## Definition of done

- [ ] Task 1 reproduces F5 on 0.3.0 first and collects ORM relationship facts only during a test
  session.
- [ ] Task 2 reports relationship, masked statement, correct loader suggestion, first
  application location; stable fingerprint.
- [ ] Task 3 pins the 35,000 SELECT overhead without raising or deselecting a budget.
- [ ] Any unfinished best-effort item is parked with reason and exact next step in `handoff.md`.
