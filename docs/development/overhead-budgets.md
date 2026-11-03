# Overhead budgets

How sharpit measures its performance impact, how to read a budget failure, and how to tell a busy machine from a slower sharpit.

## What the budget tests guard

sharpit runs inside someone else's app, so what counts is the time it adds. Two budget tests guard the hot paths:

- `tests/fastapi/test_capture_overhead.py`: capture middleware, 0.2 ms per request.
- `tests/fastapi/test_sql_trace_overhead.py`: SQL listener, 50 µs per statement.

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

1. **Read the noise in the message.** Check if the overshoot sits within the reported noise.
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
