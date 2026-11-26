# Issue #329: a baseline entry is fixed only when its owner proved it

> For agentic workers: run `/sharpit:status --feature 329-baseline-owner` for the next unchecked step. One task at a
> time; `/sharpit:check` before every commit.

**Goal:** with `--sharpit-baseline`, a test-runtime entry that is no longer seen is reported `fixed` only when the run
proves it: its owning test ran, completed its call phase, the run's evidence is whole, and no attempt or phase of that
test still shows the finding. Every other unseen test-runtime entry is `inconclusive`, with a reason, and stays in a
rewritten baseline. Advisor entries keep the current rule.

**Architecture:** the owner of a test-runtime entry is the pytest node id, already one of the three parts of its
fingerprint (`src/sharpit/engine/advisors/findings.py:35`). The baseline stores it as `sha256(node id)[:16]`, never as
text. The engine (`engine/testsession/baseline.py`) decides fixed or inconclusive from the run's `TestFacts`; the pytest
adapter (`pytest_plugin/session.py`) records whether a test's call phase passed, and `pytest_plugin/report_io.py`
passes the facts and the run's completeness to the engine. Capture, masking of findings, the guard, activation and the
exit status do not change. The baseline schema stays `sharpit-baseline/1`; the report schema stays `sharpit-report/1`
with two added keys.

**Predict verdict:** pending (`/sharpit:predict` before Task 2; the `owner` digest is new output derived from the node
id, see the risk register).

**Scenarios:** [2026-11-26-329-baseline-owner-scenarios.md](2026-11-26-329-baseline-owner-scenarios.md). Its
must-cover tests are this plan's acceptance criteria.

## Global Constraints

From AGENTS.md, the ones this change can break:

- **Fails closed.** Anything this run does not prove is `inconclusive`, never `fixed`.
- **Secrets masked before any output.** The baseline file and the report are outputs.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope.
- **Ratchets only go down:** no module under `src/` over 1000 lines; ruff C901 counts per file in
  `tests/complexity_baseline.json` (`src/sharpit/pytest_plugin/session.py` is not listed, so it must stay at 0).
- Performance: the SQL listener and the capture middleware keep their budget tests; nothing here runs in either.
- **Port BootUI, do not reinvent;** each adaptation is a deviation row in the lane's matrix fragment.
- Tests run with `-n`; each red is an assertion that names the defect (`scripts/dev/red_check.py`).

## Definitions

**Owner** of an entry: `owner_of(node_id) = sha256(node_id.encode("utf-8", "surrogatepass")).hexdigest()[:16]`, or
`null` when the finding has no test node id (every advisor finding).

**Completed** (per `TestFacts`): `True` when every call-phase report of the attempt passed under pytest, read before any
sharpit gate rewrites the report; `False` when one did not; `None` when no call report was seen (not run, skipped at
setup, setup error, `--setup-only`, `--setup-plan`, a worker that sent no value).

**Incomplete rules** (per run): every rule in `gates.GATE_IDS` when the run has an unknown reason or a session hook
failure warning; `sharpit.unbounded-read` alone when the `unbounded-read` source lists a limitation; otherwise none.

**Still shown** (per attempt): the entry's fingerprint is among the findings that `gates.evaluate_test` gives for any
phase of the attempt with an unrelaxed budget (`Budget(0, False, 0)`, N+1 threshold 2, nothing dismissed; the
max-queries rule only for the call phase), with an observed count at or above the entry's `observed`, or at any count
when the owner's own gate is off (`allow_n_plus_one`, `allow_unbounded_read`, no max-queries budget).

**Reasons**, checked in this order; the first that applies is the entry's reason, and an entry with none is `fixed`:

| # | Reason text | When |
|---|---|---|
| 1 | `recorded without its owner` | the entry has no `owner` (a baseline written before this change) |
| 2 | `the run's evidence is incomplete` | the entry's rule is an incomplete rule of this run |
| 3 | `its test did not run` | no `TestFacts` of this run has the entry's owner |
| 4 | `its test did not complete` | a deciding attempt (`outcome.deciding`) of the owner is not `completed is True` |
| 5 | `its test has a new finding of the same rule` | the run's findings hold a `new` finding of the entry's rule whose `testNodeId` has the entry's owner |
| 6 | `its test still shows it outside the gate` | any attempt of the owner still shows it |

## Decisions this plan takes

These follow from the design and the fail-closed rule; each is pinned by a test.

1. **`compare()` requires test facts.** `tests` and `incomplete` are keyword-only and have no default, so a caller
   cannot reach the current "unseen means fixed" result for a test-runtime entry by omission. An empty `tests` makes
   every unseen test-runtime entry `its test did not run`.
2. **`inconclusiveFindings` is `null` when `fixed` is `null`** (a partial run, an advisor that did not run). An empty
   list would claim that nothing was withheld. When `fixed` is an integer, it is a list sorted by fingerprint.
3. **An `owner` that is present but not a string or null is a malformed baseline** (`ValueError`), which is already an
   unknown reason that fails the run. A string of any form is accepted; one that matches no test yields reason 3.
4. **An advisor entry's `owner` is ignored** on read and written as `null`: advisor entries keep the current rule.
5. **`completed` absent from a worker's facts is `None`**, so a mixed-version run withholds `fixed` (reason 4).
6. **The same-rule new finding is read from the findings `compare()` annotates**, not from per-test annotations, so the
   result does not depend on whether a worker loaded the baseline.
7. **Incompleteness reads the hook-failure warning through one constant.** `finish.py` gains
   `HOOK_FAILURE_PREFIX = "a sharpit session hook failed ("`, used by its two existing checks and by `report_io`; a
   guard test pins that the warnings built in `sink.py` and `pytest_plugin/__init__.py` start with it.
8. **The report keeps both new keys out of `required`**, so a report written before this change still validates.
9. **Exit status is unchanged.** `inconclusive` never fails or passes a run.

## Out of scope

Route evidence per test (a test whose body no longer calls the code still reads as proof), recovering the owner of a
legacy entry by trial hashing, a prune flag, telling a deleted test from a moved one, and a terminal summary line for
the baseline. The accepted limits are listed in the decision record (Task 8) and the scenario file.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| High | A path reports `fixed` for an entry the run did not prove | One reason per row of the scenario table; each reason branch has a red test and a mutation check (Task 4) |
| High | The owner field carries test-id text into the committed baseline | It is a 16-hex digest; `test_written_owner_has_no_node_id_text` asserts the parametrize text is absent from it and the value matches `^[0-9a-f]{16}$` |
| Medium | A legacy baseline makes every test-runtime entry inconclusive until rewritten | Documented migration (Task 8): rewrite once with both flags on a complete run while the findings are still seen |
| Medium | `pytest_runtest_makereport` passes C901 10 | The non-call branch moves into a helper in Task 3; `uv run ruff check --select C901` stays clean for the file |
| Medium | Re-evaluating facts at session end is slow on a large suite | Only unseen test-runtime entries are re-evaluated, only for tests with their owner; no hot-path code changes |
| Medium | Two more pytester runs per end-to-end test against the CI wall clock | Seven end-to-end tests; every other reason is a unit test over built `TestFacts` |
| Low | Older sharpit drops `owner` when it rewrites a new baseline | Documented in the CHANGELOG; the entries then read as reason 1, never as fixed |

## Safety and overhead paths touched

| Path | Touched | Check |
|---|---|---|
| Fails closed | `compare()` result for unseen test-runtime entries | Every reason has a red test; mutants listed in Task 4 must be killed |
| Masking | New `owner` value in the baseline; `inconclusiveFindings` in the report | Owner is a digest (Task 2 test); `inconclusiveFindings` holds a fingerprint and a fixed reason string only, no application text (Task 5 test) |
| Side effects | The baseline write path only (`--sharpit-write-baseline`) | Existing byte-stability tests plus Task 2's; no new file, socket or environment change |
| SQL listener, capture middleware, sink | Not touched | `tests/engine/testsession/test_sink_overhead.py` and the SQL listener budget tests run unchanged in Task 9 |
| `pytest_runtest_makereport` | One boolean per call report, one reset per setup report | No budget test covers it; the change adds no loop or allocation |
| Activation, guard chain, network | Not touched | None needed |

## Gate commands (each task)

```bash
uv run pytest -n 2 -q <the task's test files>
uv run ruff check
uv run ruff format --check
uv run pyright
uv run python scripts/dev/red_check.py <the task's red node ids>   # before every test: commit
```

`-n 2` keeps two pytester-heavy files from holding every core; raise it on an idle machine and say so in the report.
Guard tests pass before and after the change, so they never go into `red_check`; each is proved by the mutation named
next to it (apply the mutation locally, see the named test fail, revert).

---

### Task 1: seams with no behaviour change

**Files:** `src/sharpit/engine/testsession/baseline.py`, `src/sharpit/engine/testsession/facts.py`,
`src/sharpit/pytest_plugin/session.py`, `src/sharpit/pytest_plugin/report_io.py`,
`tests/engine/testsession/test_baseline.py`.

**Interfaces:** Produces `Entry.owner: str | None = None`, `Comparison.inconclusive: tuple[tuple[Entry, str], ...] = ()`,
`TestFacts.completed: bool | None = None` (not yet serialised), `compare(..., tests: Sequence[TestFacts],
incomplete: Collection[str])`, both keyword-only and required, both ignored for now, and two module-level helpers in
`session.py`: `record_other_phase(test, report)` and `record_call_completion(test, report)`.

So that every later red is an assertion, not a `TypeError` or `AttributeError` on a missing name.

- [ ] **Step 1:** Add the fields and parameters above. `compare()` ignores `tests` and `incomplete`.
- [ ] **Step 2:** Pass `tests=()` and `incomplete=()` at the seven existing calls in
  `tests/engine/testsession/test_baseline.py` (lines 49, 58, 73, 110, 147, 152, 168). `report_io._apply_baseline`
  passes the merged tests of the report parts and `incomplete=()`.
- [ ] **Step 3:** In `pytest_runtest_makereport` (`session.py:58-100`), move the non-call branch (lines 72-77) unchanged
  into `record_other_phase`, and call `record_call_completion(test, report_obj)` before `test.outcome` is set; it does
  nothing yet. `uv run ruff check --select C901 src/sharpit/pytest_plugin/session.py` reports nothing, so
  `tests/complexity_baseline.json` needs no entry when Task 3 adds the logic.
- [ ] **Step 4:** Gates. `uv run pytest -n 2 -q tests/engine/testsession tests/pytest_plugin/test_plugin_baseline.py
  tests/pytest_plugin/test_plugin_swallowed_baseline.py tests/pytest_plugin/test_plugin_gates.py` stays green with no
  test edited beyond Step 2.
- [ ] **Step 5:** Commit `refactor: thread test facts into the baseline comparison`.

### Task 2: the baseline entry names its owner

**Files:** `src/sharpit/engine/testsession/baseline.py` (`read`, lines 41-71; `write`, lines 118-150; new `owner_of`),
`tests/engine/testsession/test_baseline.py`.

**Interfaces:** Produces `baseline.owner_of(node_id: str | None) -> str | None`. The written row gains `"owner"`;
`read` validates it.

- [ ] **Step 1:** Write the failing tests in `tests/engine/testsession/test_baseline.py`:
  - `test_written_entry_names_its_owner`: a test-runtime finding with `test_node_id="tests/test_a.py::test_n1"` is
    written; the row's `owner` equals `hashlib.sha256(b"tests/test_a.py::test_n1").hexdigest()[:16]`. Red today: the row
    has no `owner`, so `.get("owner")` is `None`.
  - `test_read_keeps_the_owner`: a file whose row has `"owner": "0123456789abcdef"` reads to `Entry.owner ==
    "0123456789abcdef"`. Red today: `read` drops the key, so the entry's owner is `None`.
  - `test_read_rejects_an_owner_that_is_not_a_string` (parametrized over `1`, `true`, `[]`): the test catches the
    `ValueError` from `read` and asserts its text is `baseline owner must be a string or null`. Red today: `read`
    raises nothing, so the assertion that an error was caught fails (not `pytest.raises`, whose `DID NOT RAISE` is not an
    assertion for `red_check`).
  - `test_written_owner_has_no_node_id_text`: a finding whose node id is
    `tests/test_a.py::test_login[password=hunter2secret]`; the written `owner` matches `^[0-9a-f]{16}$` and
    `hunter2secret` is not in it. Red today: the key is missing, so the pattern match fails.
  - `test_advisor_entry_is_written_without_owner`: a `rest-api` finding is written with `"owner": null`. Red today: the
    key is missing (`"owner" in row` is false).
- [ ] **Step 2:** Run `uv run python scripts/dev/red_check.py` on the five node ids; each must be `RED (assertion under
  tests/)`. Commit `test: baseline entries name their owner`.
- [ ] **Step 3:** Minimal code: `owner_of` as defined above; `write` adds `"owner": owner_of(finding.test_node_id)` to
  each finding row (advisor findings have no node id, so `null`) and `"owner": e.owner` to each kept row; `read`
  accepts a missing key or `null` as `None`, a string as itself, anything else raises `ValueError("baseline owner must
  be a string or null")`, and sets `owner=None` for an entry whose fingerprint is not `test-runtime:`.
- [ ] **Step 4:** Guards, green before and after:
  - `test_baseline_schema_and_sorted_bytes` and `test_baseline_write_cleans_lone_surrogates_and_uses_lf` (existing):
    serial writes stay byte-identical. Mutation: emit rows in insertion order; the first fails.
  - `test_legacy_entry_reads_without_owner`: a row with no `owner` key reads, with `Entry.owner is None`. Mutation: make
    a missing key raise; it fails.
  - `test_rewrite_of_own_output_is_byte_identical`: `write` from `read` of its own output gives the same bytes.
    Mutation: drop `owner` from kept rows; it fails.
- [ ] **Step 5:** Gates; commit `feat: write the owner digest of each baseline entry`.

### Task 3: record whether the call phase completed

**Files:** `src/sharpit/engine/testsession/facts.py` (`TestFacts`, lines 246-300: `to_json`, `from_json`),
`src/sharpit/pytest_plugin/session.py` (the two helpers from Task 1),
`tests/engine/testsession/test_sink.py` (next to the existing `TestFacts` JSON round trips),
`tests/pytest_plugin/test_plugin_session_completed.py` (new; unit tests over the two helpers with
`SimpleNamespace` report objects, no pytester, so they do not depend on the pytest version's subtest support).

**Interfaces:** Produces `TestFacts.completed` in JSON and the behaviour of `record_call_completion` and
`record_other_phase`.

- [ ] **Step 1:** Write the failing tests:
  - `test_completed_survives_the_worker_round_trip`: `TestFacts.from_json(facts.to_json()).completed is True` for facts
    with `completed=True`. Red today: `to_json` does not write it, so it comes back `None`.
  - `test_completed_missing_from_a_worker_is_none`: `from_json` of a dict without `completed` gives `None`. Guard (passes
    today through the default); kept with its mutation: default the missing key to `True`.
  - `test_a_failing_report_keeps_completed_false`: call reports passed, failed, passed (one per subtest) leave
    `completed is False`. Red today: Task 1's stub leaves `None`, so the assertion `is False` fails.
  - `test_setup_report_resets_completed`: `completed=False`, then a setup report, then a passed call report gives
    `True`. Red today: `completed` stays `None`.
  - `test_completed_is_read_before_a_gate_fails_the_test`: a passed call report whose `outcome` a gate later sets to
    `failed` leaves `completed is True`. Red today: `None`.
- [ ] **Step 2:** `red_check` on the four red ids; commit `test: record whether a test's call phase completed`.
- [ ] **Step 3:** Minimal code: `to_json` writes `"completed"`, `from_json` reads `data.get("completed")`.
  `record_other_phase` also sets `test.completed = None` on a setup report (a rerun whose first attempt recorded no
  event reuses the same `TestFacts`). `record_call_completion` sets `test.completed = report.passed and
  test.completed is not False` (sticky: pytest sends one call report per subtest); it runs before the gates rewrite the
  outcome.
- [ ] **Step 4:** `uv run ruff check --select C901 src/sharpit/pytest_plugin/session.py` still reports nothing.
  Mutants to kill: drop `is not False` (`test_a_failing_report_keeps_completed_false`
  fails); drop the setup reset (`test_setup_report_resets_completed` fails).
- [ ] **Step 5:** Gates; commit `feat: record call-phase completion in the test facts`.

### Task 4: compare() proves fixed or names the reason

**Files:** `src/sharpit/engine/testsession/baseline.py` (`compare`, lines 74-115; new `unproved`, `_shown`,
`_still_shown`), `tests/engine/testsession/test_baseline.py`, `tests/engine/testsession/tsfakes.py` (a `facts(...)`
builder for `TestFacts` with phases, budget and completion, if the existing fakes lack one).

**Interfaces:** Consumes `outcome.deciding`, `gates.evaluate_test`, `gates.Budget`, `gates.GATE_IDS`. Produces
`baseline.unproved(entry, tests, incomplete, findings) -> str | None` and `Comparison.inconclusive` filled, sorted by
fingerprint. An inconclusive entry is also in `Comparison.carried`, so `--sharpit-write-baseline` keeps it through the
existing `keep=` path.

- [ ] **Step 1:** Write the failing unit tests. Each builds a baseline with one test-runtime entry (owner
  `owner_of("tests/test_a.py::test_n1")`, `observed=30` where a count applies), runs `compare()` with built
  `TestFacts` and no current finding for it, and asserts `result.fixed == ()` and the reason. Red today for every one:
  `compare()` ignores the facts and returns the entry in `fixed`.
  - `test_entry_without_owner_is_not_fixed`: reason 1.
  - `test_incomplete_evidence_is_not_fixed`: `incomplete=gates.GATE_IDS`; reason 2.
  - `test_unbounded_read_limitation_withholds_only_its_rule`: `incomplete={gates.UNBOUNDED_READ}`; the unbounded-read
    entry has reason 2, an N+1 entry of a completed owner is `fixed`.
  - `test_deleted_owner_is_not_fixed`: no facts for the owner; reason 3.
  - `test_renamed_owner_is_not_fixed`: facts only for `tests/test_a.py::test_n1_renamed`; reason 3.
  - `test_skipped_owner_is_not_fixed`: facts with `completed=None`, `outcome="skipped"`; reason 4.
  - `test_xfailed_owner_is_not_fixed`: `completed=False`, `outcome="skipped"`; reason 4.
  - `test_owner_that_fails_before_the_code_is_not_fixed`: `completed=False`, `outcome="failed"`; reason 4.
  - `test_owner_with_setup_error_is_not_fixed`: no call phase, `completed=None`, `outcome="error"`; reason 4.
  - `test_owner_with_a_failing_subtest_is_not_fixed`: `completed=False`, `outcome="passed"`; reason 4.
  - `test_changed_statement_is_not_fixed`: the run has a `new` N+1 finding with the owner's node id and another
    fingerprint; reason 5.
  - `test_allow_n_plus_one_is_not_fixed`: completed owner whose call phase still has the group at 20 statements,
    budget `allow_n_plus_one=True`; reason 6.
  - `test_raised_threshold_is_not_fixed`: the group at 30 is still in the call facts, threshold relaxed by the
    marker; reason 6 (re-evaluation uses threshold 2).
  - `test_raised_max_exceptions_is_not_fixed`: the exception is still in the call facts under a raised
    `max_exceptions`; reason 6.
  - `test_dropped_max_queries_is_not_fixed`: max-queries entry `observed=30`, budget `max_queries=None`, call count 20;
    reason 6.
  - `test_finding_moved_to_setup_phase_is_not_fixed`: the group is in the `setup` phase facts only; reason 6.
  - `test_finding_in_an_earlier_rerun_attempt_is_not_fixed`: attempt 1 still shows it and failed, attempt 2 completed
    and is clean; reason 6.
  - `test_inconclusive_entry_is_carried`: any reason-3 entry is in `result.carried`.
- [ ] **Step 2:** Port the BootUI tests (`SideEffectComparisonTests` at v2.5.0), each with its `# ported:` line:
  - `test_gone_only_where_its_owner_ran_again` (`# ported:
    SideEffectComparisonTests.aNewHostOfARouteIsAddedAndAGoneOneRemovedOnlyWhereItsOwnerRanAgain`): two entries, one
    whose owner completed (`fixed`), one whose owner did not run (reason 3); the other's new finding is `new`. Red
    today: both are `fixed`.
  - `test_evidence_not_recorded_whole_withholds_and_fixes_nothing` (`# ported:
    SideEffectComparisonTests.aSensorThatDidNotRecordEitherRunWholeIsNotComparedAndListsNothing`): `incomplete`
    holds every rule; no entry is `fixed`, each has reason 2. Red today: all are `fixed`.
- [ ] **Step 3:** `red_check` on every id of Steps 1 and 2; commit `test: an unproved baseline entry is not fixed`.
- [ ] **Step 4:** Minimal code, following the definitions above: `unproved` returns `None` for an entry whose
  fingerprint does not start with `test-runtime:`; otherwise the first reason that applies. `_shown` evaluates each
  phase of an attempt as a call phase with the unrelaxed budget and keeps max-queries findings from the call phase only;
  `_still_shown` applies the count rule. `compare()` computes the reasons for unseen entries only, after the existing
  partial and carried checks, removes those entries from `fixed`, adds them to `carried` and to `inconclusive`.
- [ ] **Step 5:** Update `test_compare_existing_new_and_fixed` to pass a completed `TestFacts` for its `gone` owner,
  so it still asserts `fixed == ["gone"]` (with no facts the entry is now reason 3, which is the change).
- [ ] **Step 6:** Guards, green after Step 4, each with the mutation that must make it fail:
  - `test_completed_clean_owner_is_fixed` (30 to 3 statements, no relaxation). Mutation: return a reason
    unconditionally.
  - `test_relaxed_gate_with_the_finding_gone_is_fixed` (`allow_n_plus_one`, 30 to 1). Mutation: treat a gate that is off
    as always shown.
  - `test_count_at_the_baselined_value_is_still_shown`: entry `observed=30`, facts at 30 under a dropped max-queries.
    Mutation: compare with `>` instead of `>=`.
  - `test_xpass_owner_is_fixed`: `completed=True`, `outcome="passed"`. Mutation: require `outcome == "passed"` and
    `completed` from the setup report.
  - `test_teardown_error_after_a_passed_call_is_fixed`: `completed=True`, `outcome="error"`. Mutation: require
    `outcome == "passed"`.
  - `test_owner_failed_by_another_rule_is_fixed` (`# ported:
    SideEffectComparisonTests.anOwnerThatDidSomethingElseOutsideTheJvmThisRunCountsAsExercised`, adapted: another
    rule's new finding in the owner still proves this entry gone): `completed=True`, a `new` exception finding.
    Mutation: drop the rule filter in reason 5.
  - `test_flaky_rerun_with_the_code_fixed_is_fixed`: attempt 1 failed without the finding, attempt 2 completed and clean.
    Mutation: read `completed` from every attempt instead of the deciding one.
  - `test_advisor_entry_keeps_the_current_rule`: an unseen `rest-api` entry with an `owner` string is `fixed` when the
    advisor ran in full. Mutation: drop the `test-runtime:` check.
  - Mutants to kill in addition: delete each reason branch in turn (the reason's red test fails).
- [ ] **Step 7:** Gates; commit `fix: report a baseline entry fixed only when its owner proved it (#329)`.

### Task 5: the report names inconclusive entries

**Files:** `src/sharpit/pytest_plugin/report_io.py` (`_apply_baseline`, lines 108-137; new `_incomplete_rules`),
`src/sharpit/engine/testsession/finish.py` (lines 81-85: `HOOK_FAILURE_PREFIX`),
`src/sharpit/engine/testsession/report.schema.json` and `docs/reference/report.schema.json` (lines 42-56),
`tests/pytest_plugin/test_plugin_baseline.py`, `tests/engine/testsession/test_baseline.py`,
`tests/engine/testsession/test_finish.py`, `tests/test_report_schema.py`.

**Interfaces:** Produces report keys `baseline.inconclusive` (integer, or `null` when `fixed` is `null`) and
`baseline.inconclusiveFindings` (`[{"fingerprint", "reason"}]`, or `null` when `fixed` is `null`).

- [ ] **Step 1:** Write the failing end-to-end tests in `tests/pytest_plugin/test_plugin_baseline.py`. Each writes a
  baseline on a first complete run of an app whose `/n1` route runs one SELECT 30 times (one test per route), then
  changes the suite, reruns with `--sharpit-baseline` and `--sharpit-report`, and asserts `baseline["fixed"] == 0` and
  the entry's reason in `inconclusiveFindings`. Red today: `fixed == 1`.
  - `test_issue_329_deleted_test_is_not_fixed` (the issue's reproduction): the `/n1` test is deleted; reason 3.
  - `test_skip_marker_on_the_owner_is_not_fixed`: the `/n1` test gains `@pytest.mark.skip`; reason 4.
  - `test_crashed_xdist_worker_is_not_fixed`: with `-n 2`, the `/n1` test calls `os._exit(1)` (the pattern of
    `test_xdist_crashed_worker_unknown`); reason 2.
  - `test_dropped_sql_events_are_not_fixed`: a conftest replaces the sink's SQL callback with one that raises (the
    pattern of `test_plugin_hook_raises_session_continues`); reason 2.
  - `test_request_moved_to_a_fixture_is_not_fixed`: the `/n1` request moves into a function-scoped fixture of the same
    test; reason 6.
  - `test_write_keeps_an_inconclusive_entry`: the deleted-owner run also passes `--sharpit-write-baseline` to the same
    path; the rewritten file still has the entry's fingerprint and its `owner`.
  - `test_report_lists_inconclusive_with_reason`: the deleted-owner report has `baseline["inconclusive"] == 1` and
    `inconclusiveFindings == [{"fingerprint": <the entry>, "reason": "its test did not run"}]`. Red today: the key is
    absent (`.get` is `None`).
- [ ] **Step 2:** Unit tests in `tests/engine/testsession/test_baseline.py` over `_apply_baseline` with
  `render_parts`:
  - `test_unknown_reason_marks_every_rule_incomplete`: a part with an unattached swallowed-exception source (an unknown
    reason) gives reason 2 for an N+1 entry. Red today: `fixed`.
  - `test_hook_failure_warning_marks_every_rule_incomplete`: a warning that starts with `HOOK_FAILURE_PREFIX`; reason 2.
    Red today: `fixed`.
  - `test_unbounded_read_without_install_is_not_fixed`: the `unbounded-read` source lists `UNBOUNDED_READ_LIMITATION`;
    the unbounded-read entry has reason 2. Red today: `fixed`.
  - `test_partial_run_keeps_inconclusive_null`: on a partial run `inconclusive` and `inconclusiveFindings` are `null`.
    Red today: both keys absent; asserted with `"inconclusive" in data["baseline"]` first.
- [ ] **Step 3:** `tests/test_report_schema.py`: `test_report_schema_accepts_inconclusive_keys` (a report with both
  keys validates; one with `inconclusive: -1` or a finding row without `reason` does not) and
  `test_report_schema_accepts_a_report_without_inconclusive_keys` (guard: an older report still validates; mutation:
  add the keys to `required`). Red today for the first: `inconclusive: -1` validates because the key is unknown and
  unconstrained.
- [ ] **Step 4:** `red_check` on every red id; commit `test: the report lists inconclusive baseline entries`.
- [ ] **Step 5:** Minimal code. `finish.py` gains `HOOK_FAILURE_PREFIX` and uses it at lines 81 and 84.
  `report_io._incomplete_rules(data)` returns `gates.GATE_IDS` when `data["unknownReasons"]` is non-empty or a warning
  starts with `HOOK_FAILURE_PREFIX`, `{gates.UNBOUNDED_READ}` when the `unbounded-read` source lists a limitation, and
  `()` otherwise. `_apply_baseline` passes it and writes the two keys. Both schema copies gain
  `"inconclusive": {"type": ["integer", "null"], "minimum": 0}` and `"inconclusiveFindings"` (array or null of objects
  with required string `fingerprint` and `reason`, no other keys); `required` is unchanged.
- [ ] **Step 6:** Guards: `test_hook_failure_warnings_start_with_the_prefix` (the warning text built in
  `engine/testsession/sink.py:132` and `pytest_plugin/__init__.py:59` starts with `HOOK_FAILURE_PREFIX`; mutation:
  change the prefix); `test_fixed_for_a_real_fix_serial_and_xdist` (parametrized over no `-n` and `-n 2`: the `/n1`
  route is fixed to one SELECT, `fixed == 1`, `inconclusive == 0`; mutation: return reason 3 unconditionally);
  `test_partial_xdist_report_keeps_fixed_null` (existing) stays green.
- [ ] **Step 7:** Gates; commit `feat: report inconclusive baseline entries with their reason`.

### Task 6: the summary counts inconclusive entries

**Files:** `src/sharpit/report/summary.py` (`_baseline_line`, lines 37-42), `tests/test_report_summary.py`.

- [ ] **Step 1:** `test_summary_prints_inconclusive`: a report with `fixed: 1, inconclusive: 2` renders
  `- **Baseline:** 4 existing, 0 new, fixed 1, inconclusive 2`. Red today: the line ends at `fixed 1`. Guard:
  `test_summary_without_inconclusive_is_unchanged` (an older report renders as today; mutation: print
  `inconclusive None`).
- [ ] **Step 2:** `red_check`; commit `test: the summary counts inconclusive baseline entries`.
- [ ] **Step 3:** Minimal code: append `, inconclusive N` when `inconclusive` is an integer.
- [ ] **Step 4:** Gates; commit `feat: count inconclusive baseline entries in the summary`.

### Task 7: deviation rows

**Files:** `docs/reference/matrix-updates/0.10.0-baseline-owner.tsv` (new), `scripts/dev/generate_parity_deviations.py`
(`FRAGMENTS_0_10_0`, line 63), `tests/docs/test_parity_deviations.py` (the `0.10.0` count), `docs/reference/PARITY.md`
(regenerated).

BootUI 2.5.0 has no findings baseline with a fixed or inconclusive state. Its counterpart is the run comparison of side
effects (`bootui-engine/src/main/java/io/github/jdubois/bootui/engine/insights/SideEffectComparison.java`): a key whose
owner was not exercised is `NOT_EXERCISED`, not removed (lines 101-106 and 120-127), and a sensor that did not record a
run whole is not compared (`notCompared`, lines 219-233). Rows (tab-separated: key, status, reason):

| Key | Status | Reason |
|---|---|---|
| `gate:baseline-fixed-needs-owner` | adapted | BootUI reports a side-effect key gone only when its owner (route, execution or startup) was exercised, else NOT_EXERCISED; sharpit's owner is the pytest node id, because each test-runtime fingerprint is per test, and an unproved entry is inconclusive with a reason |
| `gate:baseline-exercised` | adapted | BootUI counts any key or request of the owner as exercised; sharpit requires every call-phase report of the owner's deciding attempt to pass, because a test can stop before the code |
| `gate:baseline-incomplete-run` | adapted | BootUI withholds the comparison per sensor that did not record a run whole; sharpit withholds every test-runtime entry on any unknown reason or session hook failure, and the unbounded-read entries alone when that source has a limitation |
| `gate:baseline-relaxed-gate` | n-a | BootUI side effects have no per-test gate to relax; sharpit re-evaluates the owner's facts with every gate unrelaxed, so a marker that loosened a gate cannot make an entry fixed |
| `gate:baseline-identity-drift` | n-a | BootUI keys have no per-test fingerprint; a new finding of the same rule in the owner withholds fixed, because a changed identity cannot be told from a second finding |
| `gate:baseline-owner-digest` | n-a | BootUI stores route and execution names in its run file; sharpit stores a sha256 digest of the node id, so test-id text is not added to the committed baseline |
| `gate:baseline-new-needs-exercised-before` | n-a | BootUI does not report a key new when its owner was not exercised in the previous run; sharpit keeps every unlisted finding new, which fails closed |

- [ ] **Step 1:** Add the fragment, add `("baseline-owner", "0.10.0-baseline-owner.tsv")` to `FRAGMENTS_0_10_0`, raise the
  `0.10.0` count in `test_every_fragment_row_is_categorized` by seven (one per row; a fragment count only rises when a
  fragment is added), and run `uv run python scripts/dev/generate_parity_deviations.py --write`.
- [ ] **Step 2:** `uv run python scripts/dev/generate_parity_deviations.py --check` and
  `uv run pytest -n 2 -q tests/docs/test_parity_deviations.py` pass. Commit `docs: log the baseline owner deviations`.

### Task 8: documentation

**Files:** `README.md` (lines 96-98), `docs/pytest-safety-gate.md` (lines 5-19, 35-49), `skills/sharpit/SKILL.md`
(lines 340-345) and its byte-identical copy `plugins/sharpit/skills/sharpit/SKILL.md`, `website/docs/pytest-plugin.md`
(lines 195-210), `docs/decisions/baseline-owner.md` (new) and its line in `docs/decisions/README.md`, `CHANGELOG.md`
(`[Unreleased]`).

- [ ] **Step 1:** README, safety-gate page, website page and both SKILL copies: a listed entry not seen is `fixed` only
  when its test ran and completed, the run's evidence was whole and the test no longer shows it; otherwise it is
  `inconclusive`, with its reason in `inconclusiveFindings`, and a rewrite keeps it. The SKILL drops the claim that
  `baselineState` can be `fixed` (findings carry `existing` or `new` only). The safety-gate page adds how to clear an
  entry that stays inconclusive: rewrite without `--sharpit-baseline` (with the ini option set, `--sharpit-baseline=`)
  on a complete run, which also drops carried advisor entries, or delete its row, found by the fingerprint the report
  lists.
- [ ] **Step 2:** Decision record `docs/decisions/baseline-owner.md` (Status, Decision, Rationale, Consequences,
  Enforcement): the owner digest, the six reasons and their order, the report keys, the migration of a legacy baseline,
  and the accepted limits: a test whose body no longer reaches the code, SQL on a thread no test owns, a raised
  `unbounded_read_factor` (no facts are kept above it), a loosened gate whose count falls but stays above the old limit,
  and a statement that loses its identity. Enforcement names the tests of Tasks 2-6.
- [ ] **Step 3:** CHANGELOG under `[Unreleased]`:
  - Fixed: a baseline entry is reported fixed only when its test ran and completed, the run's evidence was whole and the
    test no longer shows it; such entries were reported fixed even when their test was deleted, skipped or failed early
    (#329).
  - Added: baseline entries record a digest of their test (`owner`); reports list `inconclusive` and
    `inconclusiveFindings`.
  - Changed: an entry written before this release is inconclusive until the baseline is rewritten once with both
    `--sharpit-baseline` and `--sharpit-write-baseline` on a complete run; an older sharpit that rewrites the file drops
    `owner`.
- [ ] **Step 4:** `cmp skills/sharpit/SKILL.md plugins/sharpit/skills/sharpit/SKILL.md` is silent;
  `uv run ruff format --check`; `uv run pytest -n 2 -q tests/docs tests/cli/test_cross_task_review.py`;
  `/sharpit:doc-review`. Commit `docs: describe fixed and inconclusive baseline entries`.

### Task 9: verification

- [ ] **Step 1:** `uv run pytest -n 2 -q tests/engine/testsession tests/pytest_plugin tests/test_report_summary.py
  tests/test_report_schema.py tests/docs tests/engine/test_import_boundary.py tests/test_code_shape.py` (background).
- [ ] **Step 2:** The overhead budget tests run unchanged: `tests/engine/testsession/test_sink_overhead.py` with `-n 0`
  on an idle machine.
- [ ] **Step 3:** `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`; `tests/complexity_baseline.json`
  and `sonar-baseline.txt` unchanged or lower.
- [ ] **Step 4:** Live check of the issue's reproduction against the branch: `fixed: 0`, `inconclusive: 1`,
  `inconclusiveFindings[0].reason == "its test did not run"`, exit status unchanged; then with the test restored and the
  route fixed, `fixed: 1`, `inconclusive: 0`.
- [ ] **Step 5:** `/sharpit:branch-review`, then a draft PR whose body lists each `finding → test → red output`.

## Definition of done

- [ ] All steps checked
- [ ] `/sharpit:check` green (ruff check, ruff format --check, pyright strict, pytest)
- [ ] Every Critical and High scenario has a named test that exists and passes at the head
- [ ] Every guard test has its mutation recorded with the failing output
- [ ] Deviation rows logged in `docs/reference/matrix-updates/0.10.0-baseline-owner.tsv` and PARITY.md regenerated
- [ ] No source of masking, capture, guard or activation changed (`git diff --stat origin/main` lists only the files
  named in Tasks 1-8)
