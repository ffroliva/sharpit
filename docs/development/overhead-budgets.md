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

## Reading a failure

The failure message prints overhead, noise, and min/median/max per side.

Noise is how far a typical round sits above the fastest, measured as the median minus the min on the noisier side. If the overshoot (overhead minus budget) is within the noise, the message says so: suspect the machine.

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

After the alternating harness: TBD
