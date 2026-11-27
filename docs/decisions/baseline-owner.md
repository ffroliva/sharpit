# Baseline entry owner

## Status

Implemented for 0.10.0 ([#329](https://github.com/ffroliva/sharpit/issues/329)).

## Decision

A test-runtime baseline entry that the run does not see is reported `fixed` only when the run proves it. Every other
unseen test-runtime entry is `inconclusive`, with a reason, and a rewrite with `--sharpit-baseline` and
`--sharpit-write-baseline` keeps it. Advisor entries keep their rule: an unseen entry is `fixed` when its advisor
assessed the whole app.

Each test-runtime entry records `owner`, the first 16 hexadecimal characters of the SHA-256 digest of its test's pytest
node id. An advisor entry is written with `owner: null`, and an `owner` read for it is ignored. An `owner` that is
neither a string nor null makes the baseline malformed. The baseline schema stays `sharpit-baseline/1`.

The reasons are checked in this order; the first that applies is the entry's reason, and an entry with none is `fixed`:

1. `recorded without its owner`: the entry has no `owner`.
2. `the run's evidence is incomplete`: the entry's rule is incomplete for this run. Every runtime gate is incomplete
   when the run has an unknown reason or a session hook failure warning; `sharpit.unbounded-read` alone is incomplete
   when the `unbounded-read` source lists a limitation.
3. `its test did not run`: no test of the run has the entry's owner.
4. `its test did not complete`: a deciding attempt of the owner has a call-phase report that did not pass, or no
   call-phase report.
5. `its test has a new finding of the same rule`: the run's findings hold a `new` finding of the entry's rule whose test
   has the entry's owner.
6. `its test still shows it outside the gate`: an attempt of the owner still shows the entry when every phase is
   evaluated with no gate relaxed, at or above the entry's observed count, or at any count when the owner's own gate is
   off. For this check a `sharpit.max-queries` entry counts every phase, although the gate itself counts only the call
   phase, so queries moved into a fixture do not read as fixed.

The report's `baseline` object gains `inconclusive`, a count, and `inconclusiveFindings`, a list of `fingerprint` and
`reason` sorted by fingerprint. Both are `null` on a partial run; they are listed, and the rewrite keeps the entries,
also when `fixed` is `null` because an advisor entry is carried. Neither is required by the report schema, so a report
written before this change still validates. `inconclusive` never changes the exit status.

## Rationale

Before this change an unseen entry was `fixed` whenever the run was complete, so a deleted, skipped or early-failing
test reported its findings fixed although the code was never exercised. The owner is already one part of the
fingerprint of every test-runtime finding, so the run can tell whether that test executed. Storing a digest rather than
the node id keeps test identifiers, including parametrize text, out of the committed baseline. Anything the run does not
prove stays inconclusive, never fixed, which keeps the gate fail-closed.

## Consequences

A baseline written before this change has no owners: each of its test-runtime entries is `inconclusive` until the
baseline is rewritten once with both `--sharpit-baseline` and `--sharpit-write-baseline` on a complete run, while those
findings are still seen. An older sharpit that rewrites a baseline drops `owner`, and its entries then read as reason
1. An entry that stays inconclusive is cleared by a rewrite without `--sharpit-baseline` on a complete run, which also
drops advisor entries carried for an advisor that did not run in full, or by deleting its row.

Accepted limits: a test whose body no longer reaches the code reads as proof; SQL on a thread no test owns is not
attributed to the owner; facts above a raised `unbounded_read_factor` are not kept, so such a read cannot be
re-evaluated; a loosened gate whose count falls but stays above the old limit can read as fixed; and a statement that
loses its identity without leaving a new finding of the same rule in its test, such as one sent without text, which the
N+1 rule does not check, can read as fixed.

## Enforced by

- `src/sharpit/engine/testsession/baseline.py` reads and writes `owner` and decides fixed or inconclusive;
  `tests/engine/testsession/test_baseline.py` verifies each reason, the owner digest and the write path.
- `src/sharpit/pytest_plugin/session.py` records whether a call phase completed;
  `tests/pytest_plugin/test_plugin_session_completed.py` verifies it, and `tests/engine/testsession/test_sink.py`
  verifies that it survives the xdist worker round trip.
- `src/sharpit/pytest_plugin/report_io.py` passes the incomplete rules and writes the report keys;
  `tests/pytest_plugin/test_plugin_baseline.py` verifies the issue's reproduction, a skipped owner, a crashed worker,
  dropped SQL events, a request moved to a fixture, a rewrite that keeps an inconclusive entry and a real fix.
- `src/sharpit/engine/testsession/finish.py` defines `HOOK_FAILURE_PREFIX`; `tests/engine/testsession/test_finish.py`
  pins it against the hook failure warnings.
- `src/sharpit/engine/testsession/report.schema.json` accepts the new keys; `tests/test_report_schema.py` verifies it.
- `src/sharpit/report/summary.py` prints the inconclusive count; `tests/test_report_summary.py` verifies it.
