---
name: perf-audit
version: "1.0"
description: >
  Use when asked to audit, review or improve sharpit's runtime performance, before merging a change to a hot path
  (capture middleware, SQL listener, log handler, masking, a collector on a large app), or when an overhead test
  fails. Evidence first: measure, find the cause, then a fix that a budget test holds. Not for test-suite speed
  (that is `optimize`).
---

# `perf-audit`: find and fix real slowness, with evidence

Adapted from the "Optimization Auditor" prompt in `f/awesome-chatgpt-prompts` (CC0), cut to what sharpit needs.
ruff's `PERF`, `C4` and `FURB` rules already block the mechanical cases in CI; this skill covers what a linter cannot
see: complexity, work repeated per request, memory that only grows, and cost added to the host app.

## What sharpit's performance means

sharpit runs **inside someone else's app**. The cost that matters is what it adds to the host:

| Surface | Runs | Budget, held by |
|---|---|---|
| Capture middleware | every host request | ≤ 0.2 ms per request: `tests/fastapi/test_capture_overhead.py` |
| SQL listener | every host statement | `tests/fastapi/test_sql_trace_overhead.py` |
| Log handler, exception hook | every log line / error | bounded buffers; no formatting work when capture is off |
| Collectors, advisors, masking | only when the UI or MCP asks | linear in app size (routes, settings, rows); paged |

A slow panel is an annoyance; a slow hook is a regression in the user's app. Audit the hooks first.

## Procedure

1. **Scope.** One file, one panel, one hook, or a branch diff (`git diff main...HEAD`). Name it.
2. **Measure before you judge.** Profile the scoped path on realistic input, never guess:
   `uv run python -m cProfile -s cumtime <script>` or a `time.perf_counter_ns()` loop like the overhead tests use
   (best of several runs). For memory: `tracemalloc` snapshots before and after N requests.
3. **List findings** in this table, worst first. Each needs a concrete input that shows the cost:

   | # | Where (`file:line`) | Issue | Evidence (input → time/memory) | Fix | Big-O before → after |
   |---|---|---|---|---|---|

   Look for: O(n²) over routes, settings or rows; a regex or `inspect` call compiled or run per request instead of
   once; a buffer, dict or cache with no cap; work done when capture is off; a blocking call on the event loop;
   masking or JSON encoding done twice for one response.
4. **Fix with a guard.** Test first: a budget test (like the overhead tests) or a complexity test (time at n and at
   10n stays roughly linear) that fails on the slow code. Then the smallest fix. Then the paired measurement again,
   before and after, same machine.
5. **Never trade safety for speed.** Masking, the guard chain and the no-side-effects rules in AGENTS.md come first.
   A fix that skips masking, widens a buffer cap or caches a secret is rejected, however fast.

## Rules

- No finding without a measurement or a concrete input. "This might be slow" is not a finding.
- A budget is never raised to make a test pass. If the budget is wrong, say why and ask the owner.
- Findings with no fix this round go to the report as parked, with their evidence.

## Report

The findings table, the before/after numbers per fix, the tests added, and what was parked.
