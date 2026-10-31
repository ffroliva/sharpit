---
name: perf-audit
version: "1.0"
description: >
  Use when asked to audit, review or speed up sharpit's runtime, when an overhead budget test fails or flakes, before
  a change to a per-request or per-statement hook (capture middleware, SQL listener, log handler, masking), or when
  someone says "it's slow" without numbers. Not for test-suite speed (that is optimize).
---

# perf-audit: no claim without a paired measurement

sharpit runs inside someone else's app. What counts is the time it **adds** to a host request or statement, so every
number is a **pair**: the same work with sharpit's hook on and off, in one process, on one machine.

**Reading code finds candidates. Only a paired measurement makes one a finding.** A list ranked by reading is a
hypothesis list; label it that way or measure it.

## Where to look, in order

1. Capture middleware: every host request. Budget ≤ 0.2 ms, `tests/fastapi/test_capture_overhead.py`.
2. SQL listener: every statement. `tests/fastapi/test_sql_trace_overhead.py`.
3. Log handler and exception hook: every log line or error.
4. Collectors, advisors, UI reads: only on demand. Last, and only if 1–3 are clean.

## The measurement recipe

Copy the shape of `tests/fastapi/test_capture_overhead.py`:

1. Build the **same app twice**: hook on, and hook off. Off means the panels are disabled, not "a different app".
2. Drive it in-process with a raw ASGI scope (no `TestClient`, no httpx: their cost hides yours).
3. Run batches of N calls, alternating on and off, and keep the **minimum** per side over ≥ 5 batches.
   Contention only adds time, so the minimum is the honest number.
4. Report `on − off` per call, and the spread across batches. If the spread is bigger than the effect, there is no
   finding yet: run more batches or a bigger N before you conclude anything.
5. Prove the hook ran: assert that something was captured in the "on" run.
6. One measurement at a time, each in its own scratch folder with its own log. Two runs in parallel compete for the
   CPU and overwrite each other's output. Never write scripts or profiler output into the repo.
7. A hook whose library is missing (SQLAlchemy for the SQL listener) is installed with its extra or reported
   **not measured**, never estimated.

## A failing or flaky budget test

- Run it on the **untouched base** (`git stash` is banned; use a clean worktree of `origin/main`) before blaming or
  fixing anything. Do the same for any other test that fails during your work.
- Run the test at least three times on each side. If the base also fails, or the spread is as wide as the budget,
  report the measurement as noisy, with the numbers. Do not raise the budget, mark the test slow, skip it, or retry
  until green. A change to the harness itself (more batches, alternating on and off) is its own PR, red first.

## Changes to masking, the guard or anything that stores captured data

Speed never trades against safety (AGENTS.md "Safety model"). Before such a change:

- the masking corpus (`tests/test_masking_corpus.py`) and the safety matrix stay unchanged and green;
- a new cache or shortcut gets its own failing test first, which shows it cannot hold or return an unmasked secret;
- the change goes through `/sharpit:predict` and `/sharpit:llm-council --tier high`, as AGENTS.md requires.

A change that alters output (even "a token rotating mid-request") is a behaviour change. Call it one; don't hide it in
a speed patch.

## Report

| # | Where | Candidate or finding | on − off (spread) | Fix | Test that holds it |
|---|---|---|---|---|---|

Then: what was measured and how (N, batches, machine), what was only read, and what was not checked.

## Red flags: stop and measure

| Thought | Reality |
|---|---|
| "No time for benchmarks, just list what's slow" | Then the list says *candidates*, unmeasured. Patch nothing yet. |
| "TestClient says 21 ms per request" | That is httpx. No off run means no sharpit number. |
| "It fails at 0.23 ms, so the code got slower" | First: does the base fail too, and how wide is the spread? |
| "The cache only holds unmasked results" | Then prove it with a failing test before writing it. |
| "That other failure probably isn't mine" | Run it on the base. Probably is not evidence. |
