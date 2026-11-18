# Lane A5a: journal robustness (BootUI 2.4.0 parity)

## Goal

Port the two BootUI 2.4.0 journal robustness enhancements to sharpit:
1. Idempotent aggregate registration in the runtime journal.
2. Request profile timeline tie-break by SQL monotonic execution start nanos.

## Scenarios

### Scenario 1: Idempotent aggregate registration in runtime journal

- **BootUI 2.4.0 reference:** `E/engine/journal/RuntimeJournal.java:625`, `RuntimeJournalTests.registeringTheSameAggregateAgainNeitherCountsTwiceNorRepairsMissingCoverage`.
- **Expected behaviour:** In BootUI 2.4.0, calling `addListener` with the same `JournalAggregates` instance a second time no-ops, preserving existing event counts and coverage completeness rather than rebinding or double-counting.
- **sharpit context:** In sharpit, `RuntimeJournal` is an in-memory event ring buffer (`deque`) without a background drain thread or listener dispatch loop. Capture hooks register into `HookRegistry`, which stores hooks in an insertion-ordered dict keyed by `hook.name` (`_hooks[hook.name] = hook`), guaranteeing idempotent registration by design. `RuntimeJournal` exposes no mutable listener registration API where duplicates could be admitted.
- **Verification:** Port `# ported: RuntimeJournalTests.registeringTheSameAggregateAgainNeitherCountsTwiceNorRepairsMissingCoverage` in `tests/engine/capture/test_journal.py` as an architectural guard verifying that `RuntimeJournal` exposes no listener registration API and that `HookRegistry` registration is idempotent. Record the adaptation in `docs/reference/matrix-updates/a5a-journal.tsv`.

### Scenario 2: Request profile timeline tie-break by SQL monotonic start nanos

- **BootUI 2.4.0 reference:** `E/engine/journal/RequestJournalProfiles.java:272-293,525-536,682`, `RequestJournalProfilesTests.delayedSqlTimelineTiesUseExecutionStartRatherThanPublicationSequence`, `RequestJournalProfilesTests.sqlMonotonicTieBreakDoesNotMoveItAheadOfNonSqlItems`.
- **Expected behaviour:** Timeline items associated with a request are sorted primarily by `offsetMillis` (ascending). When two items have equal `offsetMillis`:
  1. If both items carry monotonic execution start nanos (`startNanos`, derived as `completedNanos - durationNanos` for SQL items with non-negative completed and duration nanoseconds), order by `startNanos` ascending.
  2. If either item lacks `startNanos` (e.g. non-SQL items such as `connection`, or SQL items without complete timing), the tie-break skips `startNanos` and falls through to publication sequence (`sequence` ascending). Consequently, a SQL monotonic start tie-break never moves a SQL item ahead of a preceding non-SQL item.
  3. When `startNanos` values are equal, publication sequence breaks the tie.
- **sharpit context:** `src/sharpit/engine/collectors/insights/profile.py` implements request profile timeline ordering and `sql_start_nanos`.
- **Verification:** Port both `RequestJournalProfilesTests` cases in `tests/engine/insights/test_insights_profile.py`. Verify failure under the pre-2.4.0 offset-sequence ordering (red first), then implement the 2.4.0 comparator in `src/sharpit/engine/collectors/insights/profile.py`.

## Tasks

- [ ] **Step 0:** Document plan and scenarios in `A5a-journal.md`.
- [ ] **Step 1:** Port idempotent aggregate registration test (`RuntimeJournalTests.registeringTheSameAggregateAgainNeitherCountsTwiceNorRepairsMissingCoverage`) in `tests/engine/capture/test_journal.py` as an architectural guard, and record adaptation row in `docs/reference/matrix-updates/a5a-journal.tsv`.
- [ ] **Step 2:** Port both `RequestJournalProfilesTests` cases in `tests/engine/insights/test_insights_profile.py`, verify red first with `scripts/dev/red_check.py`, then implement the SQL start monotonic tie-break comparator in `src/sharpit/engine/collectors/insights/profile.py`.
