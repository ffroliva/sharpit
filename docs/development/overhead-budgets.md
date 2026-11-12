# Overhead budgets

How sharpit measures its performance impact, how to read a budget failure, and how to tell a busy machine from a slower sharpit.

## What the budget tests guard

sharpit runs inside someone else's app, so what counts is the time it adds. Four budget tests guard the hot paths:

- `tests/fastapi/test_capture_overhead.py`: capture middleware, 0.2 ms per request.
- `tests/fastapi/test_sql_trace_overhead.py`: SQL listener, 50 µs per statement.
- `tests/fastapi/test_sql_journal_overhead.py`: the `sql` journal event offered per recorded statement, 25 µs. Measured 2026-11-12, five paired runs, `-n 0`: 7.4 to 12.3 µs. The 50 µs test above runs with the journal on by default, so it includes this cost; on a loaded workstation it passed 4 of 5 five-run sets' files and failed once at 55 µs (base with the offer stubbed out failed 1 of 4 at 60 µs: the baseline sits near the budget when the machine is busy). Round 2 (`22ff97e5`, `97735e08`: the producer charges the event's size itself instead of the journal walking it, and the recorder truncates the shape once): 10 runs, `-n 0`, 5.8 µs median (3.4 to 8.8); `test_statement_overhead_budget` 30.2 µs median (28.0 to 33.3) against 23.9 µs (20.9 to 25.9) on `origin/release/0.6.0` in the same interleaved loop, so the event still adds about 6 µs to the 50 µs row.
- `tests/fastapi/test_log_journal_overhead.py`: the `log` journal event offered per WARN-or-above record the log handler sees, 20 µs (first number, for the owner; measurement in the lane report). Records below WARNING pay one integer compare.
- `tests/fastapi/test_sql_trace_overhead.py::test_recorder_cache_miss_within_budget`: SQL listener on a statement the recorder has not seen, 300 µs. The 50 µs test repeats one statement, so it never reaches the scan or the masker. Measured 2026-11-05 with `uv run python -m scripts.dev.overhead_check <test> --runs 10`, 1,000 distinct statements a side, on a quiet workstation: 58 µs median (57 to 64) on `9725dc1`, 213 µs median (199 to 230) with the recorder's masker pass. The rise is the price of masking, paid once per distinct text while the statement stays in the recorder's 1,024-entry cache; a statement with inline literals is a new text every time. With one scan on a miss and no second read of unchanged text: 114 µs median (96 to 136), 130 µs (120 to 176) under `--load`. The test's statement is 43 characters and the cost grows with length: paired on and off, a 736-character statement adds 581 µs (350 at `9725dc1`), a 4,901-character one 4,175 µs (2,349). 300 µs is a first number, set from that measurement, for the owner to confirm.
- `tests/fastapi/test_sql_trace_overhead.py::test_recorder_cache_miss_on_a_large_statement_within_budget`: SQL listener on a distinct 138 KB statement (10,000 `'k=v'` literals), 40 ms. Nothing past the scan's 20,000 characters is shown, so the masker reads that window and a 4,096-character margin, not the whole statement (council finding, Task 35). Measured 2026-11-08 on a workstation at 64 to 68 % CPU from other agents, `-n 0`: 4.5 ms on base `523eb1e5` (same shape, a scratch script: the test needs HEAD's modules), 90 ms on `6975ff94` before the bound (52 ms in this test, red against 40), and with the bound, `overhead_check --runs 10`: 24.6 ms median (20.9 to 31.2), noise 1.8 ms. The residual over base is the masker's pass over the bounded window, the price a 24 KB statement pays too. 40 ms is a first number, for the owner to confirm.
- `tests/fastapi/test_sql_trace_overhead.py::test_mysql_family_read_budget`: distinct ORM-style backtick statements, family scan against one MySQL read, maximum 1.2x. There is no statement cache in this direct lexer measurement, so each input reaches the reader. A statement holding a `$` or a `\` pays the second read, and one holding a `\` four more for the session readings: no budget covers those, and no statement of an ORM holds them unless its values are inline.
- `tests/fastapi/test_mask_error_overhead.py`: `mask_error` on a log line, 350 µs per line. That is about 2x `fa2d51e`, the tree the masking redesign started from: a line with no SQL marker takes the path of `mask_text`. `test_error_text_overhead` times the facade's `error_text`, the call the log tail makes, on the same line against the same budget. Measured 2026-11-08 on the SQL output architecture (Task 32, five runs alone, `-n 0`): `mask_error` 236 µs median (173 to 251), `error_text` 233 µs median (181 to 248), noise 11 to 15 µs. The facade adds no pass.

CI's coverage job deselects them because coverage tracing distorts timing. Every other test job runs them.

## How they measure

Each test runs the same workload with the hook on and off, in one process. Rounds alternate on/off and the side that goes first swaps every round (`tests/overhead.py`). The fastest round of each side is kept, because contention only adds time.

Both rules exist to prevent machine noise from distorting the measurement:

- **Alternating on and off.** A runner can slow down for seconds at a time. Timing all off rounds before all on rounds puts that slowdown on on, reporting 60 for a true cost of 10 in `tests/test_overhead_harness.py`.
- **Swapping which side goes first.** The first round after a switch pays for a cold cache. Always running off first charges that penalty to off and hides overhead, reporting -40 for a true cost of 10 in `tests/test_overhead_harness.py`.

### Round size: many short rounds beat a few long ones

The minimum works only if some rounds of each side run without contention. On a shared runner (four vCPUs, `pytest -n auto` workers alongside) the machine slows down in waves lasting a fraction of a second. A round longer than a wave always overlaps one, so its minimum still carries contention and the on-minus-off difference swings by more than the budget.

The SQLAlchemy lazy-load budget (`tests/engine/test_n_plus_one_overhead.py`, 35 µs per lazy load) hit this. A lazy load costs about 200 to 450 µs of wall time on a runner. With 21 rounds of 1,000 lazy loads (about 0.3 s per round), CI failed now and then on different jobs: for example "overhead 49.9 µs, noise 148 µs". The test now runs 1,001 rounds of 20 lazy loads (about 5 ms per round), for the same total work and wall time. It still measures real lazy loads through the production hooks that `sqla.attach_session()` attaches.

Measured on a workstation already at 60% CPU from other jobs, with five repetitions per shape:

| Shape | Overhead, no injected cost (µs) | Spread | With 50 µs busy work in the hook (µs) |
|---|---|---|---|
| 21 × 1,000 loads | 11.0, -37.9, -27.3, 58.0, 5.9 | 96 | 81.7, 55.2, 71.4, 67.6, 119.7 |
| 1,001 × 20 loads | 12.4, 11.0, 11.7, 17.5, 15.2 | 6.5 | 69.3, 75.9, 74.8, 73.5, 63.5 |

**Blind spot: costs rarer than once per round.** The minimum bounds only work that recurs in every 20-load round. A cost paid in bursts further apart passes, even if its amortised total is over budget. An independent review measured this: 4 ms of busy work every 100th lazy load (40 µs amortised) passed 4 runs out of 4, because the fastest "on" round was a clean one. The same 40 µs paid every load, every 4th load or every 20th load failed every time. Today's hook has no such periodic path: no bounded buffer, counter or flush in `_record_relationship` / `_lazy_seen`. If one is ever added, give it its own test: one long timed run of the whole workload on each side, checking total time divided by lazy loads, so a rare burst counts at its amortised weight.

The reading is also not quite "per lazy load in steady state". `detach_session()` clears `_lazy_seen`, so in every round the first lazy load pays the full first-seen observation (1 load in 20, against 1 in 1,000 before). This over-reports, which is the safe direction.

**Noise column.** For short rounds, `noise` (median minus min of one round) describes how much a single 5 ms round varies, not how stable the minimum is. It stays far above the overshoot even for a real regression, so the "suspect a busy machine" hint is not evidence for this test. Use the paired runs and the comparison against main from the checklist below.

CPU time (`time.thread_time`) would not help. The variation is in how fast the CPU runs, not in time spent descheduled: QueryThreadCycleTime showed the same spread. On Windows, `thread_time` also only ticks every 15.6 ms. The harness (`tests/overhead.py`) is unchanged, so the other budget tests mean what they did. A budget test that flakes the same way should get shorter rounds before anything else.

## Reading a failure

The failure message prints overhead, noise, and min/median/max per side.

Noise is how far the fastest round moves between the first and the second half of the run, on the less stable side. The overhead is a difference of two minimums, so the question is how much a minimum depends on which rounds were timed. A busy stretch moves it. A wide but steady spread of single rounds does not, which is normal when there are many short rounds. If the overshoot (overhead minus budget) is within the noise, the message says so: suspect the machine.

Until 2026-11-03, noise was the median minus the min of one side. With many short rounds (the lazy-load budget, 1,001 rounds of 5 ms) that figure stayed between 124 and 274 µs even for real regressions. Every injected regression then printed "suspect a busy machine". `tests/test_overhead_harness.py` holds the cases that tell the two definitions apart. Noise figures in older job summaries and in the known numbers below use the old definition.

## Is it a false positive? A checklist

Follow these steps when a budget test fails:

1. **Read the noise in the message.** Check if the overshoot sits within the reported noise. Low noise means a real rise: an overshoot well past the noise is not a busy runner. Never blame the runner without a noise figure.
2. **Run the check script locally.** Run `uv run python -m scripts.dev.overhead_check <test> --runs 10` locally; then with `--load` to see how it behaves on a busy machine.
3. **Compare against main.** Run the same on a clean worktree of `origin/main`. If main fails the same way, it is not your change.
4. **Evaluate the result.** Only a failure larger than its noise, that also does not happen on main, is a regression.

## Watching the trend

Every CI run appends a row per budget test to the job summary (overhead, budget, noise). Compare runs there before deciding a number moved.

## What never to do

- Raise a budget to pass.
- Mark a budget test slow, skip or deselect it.
- Retry until green.
- Change the harness without a separate PR and a test seen red first.

Moving a budget is a product decision for the owner, with the measurements in the PR.

## Known numbers (2026-10-31)

Capture overhead measured 0.12 to 0.18 ms per request.

Under bursty load (every core busy 0.7 s, idle 0.7 s) the old sequential harness failed 3 of 12 runs (0.530, 0.244 and 0.259 ms against a 0.2 ms budget). On a quiet machine it passed 10 of 10 runs.

After the alternating harness, on the same machine and load: 0 of 12 runs failed under load (overhead 0.119 to 0.191 ms, median noise 0.044 ms) and 0 of 10 quiet (0.117 to 0.160 ms, median noise 0.024 ms). The worst loaded run is still close to the budget, so a rare failure on a very busy runner remains possible; the noise in the message tells it apart.

## Removed budgets

### security-logs hook per request (removed 2026-11-04, owner's decision)

`tests/fastapi/test_security_logs_overhead.py` held a 2.000 µs wall-clock budget for what the enabled `security-logs`
panel adds to a 200 request. It is gone, on purpose, as an explicit owner exception to architecture rule 5 for this one
test.

Why: the number it measured is zero by construction. The capture middleware reaches the hook only for a 401 or 403
(`if sent in (401, 403) and wiring.on_security_event is not None`), so on a timed 200 the hook-on and hook-off apps run
the same code. What the test reported was the error of the estimator, and the error is larger than the budget:

- 65 results from 13 CI runs on 2026-11-04: 36 were negative (down to -45 µs, a hook cannot speed a request up), 6 were
  over the budget (2.13 to 21.6 µs; four on Linux 3.14, one of them on `release/0.5.0` before any masking gate), and a
  quiet runner scatters about ±1 µs against a 2 µs budget. A passing run and a failing run of the same code, hours apart.
- A control with two identical hook-off apps, 12 fresh processes: -3.8 to +3.7 µs, as wide as the real pair.
- The `noise` figure cannot see the cause. A constant offset between two apps is the same in both halves of the run, so
  it does not show in the split-half gap, and a 2 µs margin is 1.25 % of a 130-160 µs request.

What replaces it: `test_200_request_runs_no_security_logs_code` in the same file. It profiles a round of 200 requests and
asserts that no function of `engine/capture/securitylogs.py` is entered, and that a 401 does enter it (so the profile can
see the lane). It was checked to bite: with the guard in `capture.py` changed to call the hook on every request, it fails
on `assert ['hook', ...] == []` (110 calls). The 0.2 ms capture budget still covers the middleware as a whole.

This is not a precedent. A budget that measures real work (the other budget tests time 20 to 50 µs per call, or 0.2 ms)
stays, and moving one is still the owner's decision with the measurements in the PR.
