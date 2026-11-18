# E1-65: an advisor that assessed part of the app does not fail the run

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit. Read BootUI's `FailOn.java` and `FailOnTests.java` at `v2.4.0` in a BootUI clone, not a
> summary.

**Goal:** `pytest --sharpit` exits 0 on a run with no finding at or above `--sharpit-fail-on` when an advisor assessed
part of an application and listed what it could not read (issue #65). A finding still fails, and lost capture still
leaves the run `unknown`.

**Architecture:** the advisor status gains one value, `PARTIAL`. `AdvisorRun.of` separates an advisor that could not
assess (`UNKNOWN`) from one that assessed part of the app (`PARTIAL`). The session merge orders the statuses, adds no
unknown reason for `PARTIAL` and records one warning per partial app. The terminal summary, the Markdown summary and
the report schema learn the new value.

**Contract (BootUI 2.4.0 `FailOn.java`):** `EVALUATED = {SCANNED, PARTIAL}` (line 57); a scan with no usable evidence is
unevaluable (lines 131-135); a `PARTIAL` scan with no counted finding succeeds and prints that having no finding is not
proof there is none (lines 151-155); a counted finding fails whether the scan is `SCANNED` or `PARTIAL`.

## Scenarios

`fail_on` is `HIGH`; "exit" is the pytest exit status of a run whose tests all pass.

| # | Situation | Advisor status | Session status | Exit |
|---|---|---|---|---|
| 1 | Usable app, incomplete coverage (an opaque mount), no finding | `PARTIAL`, first limitation as reason | `pass`, one warning "assessed part of" | 0 |
| 2 | The same, with a finding at or above `fail_on` | `FAILED`, no reason | `fail` | 1 |
| 3 | The same, with a finding below `fail_on` only | `PARTIAL` | `pass` | 0 |
| 4 | Nothing assessed: the advisor is not usable and lists a limitation | `UNKNOWN` | `unknown` | 1 |
| 5 | The scan status is `ERROR`, including a rule error, and no finding | `UNKNOWN` | `unknown` | 1 |
| 6 | The scan status is `ERROR` with a finding at or above `fail_on` | `FAILED`, reason kept | `fail`, unknown reason listed | 1 |
| 7 | Not usable, no limitation, coverage complete (unchanged in this change) | `PASSED` | `pass` | 0 |
| 8 | A partial advisor beside a run with no SQL source attached | `PARTIAL` | `unknown` (no SQL source) | 1 |
| 9 | A partial advisor beside lost events or a lost worker | `PARTIAL` | `unknown` (lost capture) | 1 |
| 10 | xdist: one worker `PARTIAL`, another `PASSED` for the same app | `PARTIAL` | `pass` | 0 |
| 11 | xdist: one worker `PARTIAL`, another `UNKNOWN` | `UNKNOWN` | `unknown` | 1 |
| 12 | xdist: one worker `PARTIAL`, another `FAILED` | `FAILED` | `fail` | 1 |
| 13 | Report-only mode with a partial advisor | `PARTIAL` | report only; no unknown reason | 0 |
| 14 | A `PARTIAL` report validated against either copy of `report.schema.json` | `PARTIAL` | any | n/a |

Status order for one advisor over several workers or apps: `FAILED`, `UNKNOWN`, `SKIPPED`, `PARTIAL`, `PASSED`.

## Decisions

- Rule errors stay `UNKNOWN` (BootUI treats an errored scan as `PARTIAL`): the rule that errored may have been the one
  that finds the problem.
- The report enum widens inside `sharpit-report/1`; the changelog states it.
- A `PARTIAL` advisor is a visible status, not `PASSED` with `coverageComplete` false.
- The exit status stays pytest's: `1`, where BootUI's `--fail-on` exits `3`.
- An advisor that is not usable and lists no limitation keeps today's status.

## Tasks

### Task 1: Tests that pin the boundary

**Files:** `tests/engine/testsession/test_outcome.py`, `tests/engine/advisors/`, `tests/test_report_schema.py`,
`tests/pytest_plugin/test_plugin_gate_defaults.py`, `tests/pytest_plugin/test_plugin_xdist.py`.

- [ ] **Step 1:** Rewrite the tests that pin the old behaviour so each keeps its intent with an advisor that is not
      usable or whose scan status is `ERROR`, never by dropping an assertion.
- [ ] **Step 2:** Add three tests ported from `FailOnTests` (a partial scan with a finding still fails, a partial scan
      without one passes and says it is not proof, zero findings from a scan with no usable evidence cannot pass).
- [ ] **Step 3:** Add the status-order, lost-SQL, xdist, rule-error, schema and end-to-end tests for scenarios 1 to 14.
- [ ] **Step 4:** Run `scripts/dev/red_check.py` over every new test; each fails on an assertion. Commit
      `test: an advisor that assessed part of the app does not fail the run (#65)`.

### Task 2: The status and the merge

**Files:** `src/sharpit/engine/advisors/findings.py`, `src/sharpit/engine/testsession/outcome.py`,
`src/sharpit/engine/testsession/finish.py`.

- [ ] **Step 1:** `AdvisorRun.of` returns `UNKNOWN` for an advisor that is not usable or whose scan errored, `PARTIAL`
      for a usable advisor with a gap, and `FAILED` for a finding at or above the threshold (a reason only when the
      advisor could not assess).
- [ ] **Step 2:** `_worst` orders the statuses; `merge` takes `fail_on` and adds one warning per partial app.
- [ ] **Step 3:** Run the Task 1 tests; all pass.

### Task 3: The surfaces

**Files:** `src/sharpit/pytest_plugin/terminal.py`, `src/sharpit/report/summary.py`, both copies of
`report.schema.json`.

- [ ] **Step 1:** `_ASSESSED` includes `PARTIAL`; the Markdown summary lists the partial notes.
- [ ] **Step 2:** Both schema copies accept `PARTIAL`.
- [ ] **Step 3:** Commit `fix: an advisor that assessed part of the app passes with a note instead of failing the run (#65)`.

### Task 4: Documents

**Files:** `docs/pytest-safety-gate.md`, `skills/sharpit/SKILL.md`, `CHANGELOG.md`,
`docs/reference/matrix-updates/e1-65.tsv`.

- [ ] **Step 1:** State the partial rule in the gate document and the user skill.
- [ ] **Step 2:** Changelog entry under `Unreleased`: the enum widens within `sharpit-report/1`; the gate change.
- [ ] **Step 3:** Deviation rows: exit `1` against BootUI's `3`; the session, app and worker merge; rule errors stay
      `UNKNOWN`; an advisor that is not usable with no limitation is unchanged.
- [ ] **Step 4:** Commit `docs: the partial advisor rule, the report enum and the deviations (#65)`.

### Task 5: Gates

- [ ] **Step 1:** `uv run pytest -q -n 2` over the affected test directories, `uv run ruff check`,
      `uv run ruff format --check`, `uv run pyright`; all green.
