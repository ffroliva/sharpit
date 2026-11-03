# P-sink-mask-memo findings

Implementer: Claude subagent (claude-opus-5-5)

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/testsession/test_sink_overhead.py::test_sink_on_sql_repeated_statement_overhead_budget | e1559d3b441fd07381a054c49a77a1c170f12121 | `check_budget` (tests/overhead.py): `overhead 47.770 µs ... budget 30.000 µs` on the un-memoised sink | Fixed in 278e88cb6c1d7dca6b544b0c51b65636b54ef027 |

`red_check.py` said `RED (assertion under tests/)` for it at the red commit.

## Pins (Historical SHA)

Both safety tests pass on the base: the un-memoised sink masks on every call, so they cannot be reds. Each was
mutation-proven in a scratch copy of `src/` (run with `PYTHONPATH=<scratch>/src`, `sharpit.__file__` checked).

| Test | Historical SHA | Mutation | Failure under the mutation |
|---|---|---|---|
| tests/engine/testsession/test_sink.py::test_masked_fingerprint_memo_never_returns_an_unmasked_value | 18eb9f014f5fb7f9ddd2a4b6ac65edbb129ac04a | A: `_mask` memo that hands back the raw string on a hit | `test_sink.py:490: assert 'ghp_' not in '{"worker": ...'` |
| tests/engine/testsession/test_sink.py::test_masked_fingerprint_memo_keys_on_masker_settings | 18eb9f014f5fb7f9ddd2a4b6ac65edbb129ac04a | B: module-global memo keyed on the text only (shared across sinks and maskers) | `test_sink.py:505: assert 'ghp_' not in '{"worker": ...'` (the strict sink got the loose sink's raw text) |

New rule, removed in a scratch copy: making the memo module-global (mutation B) fails the settings test; removing the
memo (the red SHA) fails the budget test.

## Budget measurement

`on_sql` per repeated statement, paired against a no-op hook, 60 rounds x 300 statements (Windows 11, CPython 3.13,
this lane's venv): un-memoised 47.8-50.8 µs, memoised 10.8-11.9 µs. Budget 30 µs: about 2.5x the memoised cost,
below the un-memoised one. The remaining ~11 µs is `filtered_rule`, `normalize`, `category_of` and the counters (out
of this lane's scope).

## Scratch suite, paired wall time

The spike's suite rebuilt outside the repo (scratchpad): SQLite in memory, SQLAlchemy 2.1.6, CPython 3.13, 150 tests x
(40 `session.get` + one `selectinload` list + 40 filtered `select`), 12,343 statements counted in the report. Six rounds,
separate processes, side order alternating per round; "before" is this lane's red commit e1559d3 (`src/` via
`git archive`, on `PYTHONPATH`), "after" is the fix 278e88c. On both sides `--sharpit --sharpit-no-advisors
--sharpit-allow-unknown --sharpit-report=report.json`.

| Side | min | rounds (s) | min - off |
|---|---|---|---|
| off (plain pytest) | 4.25 s | 5.07 4.80 5.05 4.25 4.50 4.45 | |
| before (no memo) | 6.31 s | 8.49 7.58 6.57 7.35 6.31 6.64 | 2.05 s (1.48x) |
| after (memo) | 5.27 s | 6.08 5.94 5.79 5.49 5.27 5.31 | 1.02 s (1.24x) |

The suite overhead halves (2.05 s to 1.02 s), in line with the spike's 57% share for re-masking.
