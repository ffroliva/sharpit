# Slow endpoint

## Goal and entry

Use for a named slow route or retained slow request. Explain the bottleneck before editing.
Load the [shared contract](README.md); do not launch a load test without approval.

## Prerequisites

Confirm route, input/data scale, expected response, reproduction permission, warmup, concurrency, measurement window,
and acceptance statistic/threshold. Use a user-agreed threshold, not a universal latency target.
Identify whether the symptom includes startup, downstream dependencies, streaming, or asynchronous completion.

## Investigation

| MCP tool | CLI equivalent | Read for |
| --- | --- | --- |
| `get_live_activity` | `sharpit activity --query "<route>" --limit 20 --json` | Relevant profileable request IDs, durations, and severity |
| `get_request_profile` | `sharpit request-profile <id> --json` | SQL timing breakdown, statement count, N+1 suspects, exceptions, and overall timing |
| `get_runtime_insights` | `sharpit insights list --query "<route>" --json` | Route observations, limitations, and next calls |
| `get_http_routes` | `sharpit http routes --limit 20 --json` | Retained route rankings (p50/p95/p99 latency, request counts) |
| `get_http_exchanges` | `sharpit http exchanges --limit 20 --json` | Retained HTTP exchanges with headers, durations, status codes |
| `get_threads` | `sharpit threads --limit 25 --json` | Thread states (RUNNABLE / WAITING), call stacks, asyncio event loop tasks and await chains |
| `get_agent_status` | `sharpit agent status --json` | Agent sensor status (reports NOT_ATTACHED in this version; no method-level code path sensors) |

1. Pick a current request ID from relevant activity or an observation exemplar. Check retention, profile source,
   truncation, and correlation notes. Do not repeatedly retry an evicted ID.
2. Separate database work, handler execution, and missing evidence. Inspect `get_request_profile` for total request
   duration and time spent in SQL. If database time dominates, follow [Database efficiency](database-efficiency.md);
   do not treat database query time as an application CPU hotspot.
3. Inspect Python concurrency and event loop behavior. In FastAPI:
   - `async def` endpoints execute directly on the single-threaded asyncio event loop. Any synchronous blocking call
     (such as `time.sleep()`, synchronous file I/O, or CPU-bound loops) blocks the event loop and stalls all concurrent
     connections.
   - Synchronous `def` endpoints run in an AnyIO worker thread pool. If the thread pool is saturated, incoming requests
     queue waiting for an available thread.
   - Check `get_threads` (`sharpit threads --json`) to inspect thread states, call stacks, active asyncio tasks, and
     their await chains.
4. Note on method-level code paths: BootUI provides a Java bytecode agent with code paths and method probes.
   sharpit ships no Python bytecode profiler or code-path sensor in this version; `get_agent_status` reports
   `NOT_ATTACHED`. Handler timing is determined by subtracting recorded SQL time from overall request duration in
   `get_request_profile`, combined with thread and task inspection. Report this limitation rather than assuming method
   profiling is available.
5. If request evidence leaves CPU utilization or thread contention unexplained, hand off to
   [Python performance and memory](python-performance-and-memory.md), retaining the same budget.

## Fix and verify

Read impact, validate the source mechanism, and propose the smallest change. In review-first mode stop before editing.
For approved execution, run functional tests, reload the application, and replay the agreed workload. Compare the
chosen statistic over predefined samples, after equivalent warmup, with identical data/concurrency and comparable
dependencies. Include errors and timeouts, not just successful fast samples.

Use [Verify my changes](verify-my-changes.md) to confirm changed code ran and inspect new SQL and side effects.
A route-ranking improvement alone cannot justify a fix or prove a sustained speedup.

## Stop and report

Stop with a scoped limitation if samples are insufficient, the workload or dependencies changed, or telemetry is
missing. Do not tune timeouts, enlarge thread pools, or add caching layers just to improve a number without
validating semantics and identifying the true bottleneck.
