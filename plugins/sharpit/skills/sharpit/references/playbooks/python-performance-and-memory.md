# Python performance and memory

## Goal and entry

Use for high CPU utilization, memory growth, event-loop stalls, thread exhaustion, or process resource consumption
unexplained by ordinary request evidence in a FastAPI application. Load the [shared contract](README.md).
This is a local development workflow, not a production monitoring service.

## Prerequisites

Confirm repository and runtime identity, Python implementation and version (CPython 3.12–3.14), process PID,
representative workload, OS environment, and host resource limits.

BootUI provides JVM-specific tools (such as HotSpot heap dumps, JFR profiling, and GC tuning); sharpit runs on Python
and FastAPI and does not have those JVM diagnostic mechanisms. Obtain process-level memory (RSS) and CPU metrics from
the operating system or host environment where permitted.

BootUI’s escalation table and capture discipline apply: begin with existing in-process evidence, then request OS/process evidence if needed. Keep profiler output local; never upload it.

## Investigation

### Start with sharpit evidence

| MCP tool | CLI equivalent | What it actually does |
| --- | --- | --- |
| `get_threads` | `sharpit threads --limit 25 --json` | Python OS threads with states (RUNNABLE / WAITING) and stacks, plus asyncio event-loop tasks with await chains |
| `get_request_profile` | `sharpit request-profile <id> --json` | Correlated request timing breakdown: total duration, SQL time, statement count, and exceptions |
| `get_metrics` | `sharpit metrics --limit 25 --json` | Bounded available meters (Prometheus or custom application meters if registered) |
| `get_overview` | `sharpit overview --json` | Python runtime version, platform, process startup time, active profiles, and sharpit status |
| `get_live_activity` | `sharpit activity --limit 20 --json` | High-frequency activity, requests, SQL execution, and durations |

### Documented tooling limitations

sharpit provides diagnostic evidence through the tools listed above. Where BootUI relies on JVM-specific tooling,
sharpit does not have equivalent tools:
- **No heap dumps or object graphs:** Python uses reference counting with cyclic garbage collection (`gc`). sharpit has
  no live memory footprint mutators, JVM tuning, or heap dump analysis tools. Never invent commands for them.
- **No Java Flight Recorder (JFR):** Python has no native JFR runtime recording facility.
- **No Native Memory Tracking (NMT):** Python does not expose a JVM-style NMT interface.
- **No method-level bytecode profiler:** `get_agent_status` reports `NOT_ATTACHED` because sharpit ships no bytecode
  profiler agent in this version.

Record these limitations explicitly in the assessment plan rather than treating absent tooling as an installation defect.

### Ordered diagnostic steps

Read `get_runtime_insights` (`sharpit insights list --query all --json`) for `route-time-breakdown` when route timing applies.

1. Read `get_threads` (`sharpit threads --json`):
   - Inspect Python OS threads and their states (`RUNNABLE` vs `WAITING`).
   - Inspect active asyncio event-loop tasks, their current coroutines, and await chains.
   - Look for thread contention, deadlocks, or worker threads stuck in synchronous I/O or sleep calls.
2. Read `get_request_profile` (`sharpit request-profile <id> --json`) for slow requests:
   - Separate database duration from Python application execution time.
   - If SQL time accounts for the majority of latency, hand off to [Database efficiency](database-efficiency.md).
   - If application time dominates, look for CPU-bound computation or synchronous blocking calls inside the handler.
3. Diagnose asyncio event-loop stalls vs worker thread-pool exhaustion:
   - **Event-loop stalls (`async def` handlers):** In FastAPI, `async def` route handlers run directly on the
     single-threaded asyncio event loop. Calling synchronous blocking functions (such as `time.sleep()`, synchronous
     database drivers, or CPU-intensive loops) directly inside an `async def` handler halts the event loop, freezing
     all concurrent requests.
   - **Thread-pool exhaustion (`def` handlers):** Synchronous `def` handlers run in an AnyIO worker thread pool
     (default capacity 40 threads). If synchronous handlers block on external networks or sleep, all pool threads
     become occupied, and incoming requests queue waiting for an available thread.
4. Diagnose memory growth:
   - Since sharpit does not capture Python heap dumps, inspect application source code for unbounded in-memory caches,
     global dictionaries without TTL or eviction, unclosed connections, or database queries that load entire tables into
     memory without pagination or chunking.
5. **PARTIAL** means incomplete coverage; **INSUFFICIENT** means evidence cannot support a conclusion; **UNKNOWN** means a check has not run or status is unavailable. Low-footprint diagnostic reads return paused evidence, not fresh measurements.
6. Reading PARTIAL / INSUFFICIENT / UNKNOWN evidence:
   - **Thread paging:** `get_threads` returns a bounded page; check `page.hasMore` before concluding that unlisted
     threads are absent.
   - **Masking:** Under `METADATA_ONLY` or default secret masking, thread names or arguments containing sensitive
     patterns are masked.
   - **Metrics:** If no Prometheus client or custom meters are registered, `get_metrics` returns an empty list;
     this reflects application instrumentation, not zero resource consumption.

### What needs the user's approval

Low-footprint controls are actions; obtain approval before `sharpit low-footprint enable` or `sharpit low-footprint disable`. Enabling discards buffered diagnostics.

Obtain explicit user approval before:
- Attaching external OS profilers or debuggers (e.g., `py-spy`, `cProfile`).
- Running load generation scripts or benchmarks against the local application.
- Restarting the development application.
- Changing logging levels, worker pool configurations, or environment variables.

## Fix and verify

Validate the root cause in source code before editing:
- Move CPU-bound work or blocking synchronous I/O out of `async def` handlers using `anyio.to_thread.run_sync()` or
  dedicated background workers.
- Add pagination (`limit` / `offset` or keyset pagination) to database queries to prevent unbounded in-memory lists.
- Set bounds and TTL eviction on in-memory caches.

In review-first mode, propose the fix in the action plan and stop. Under approved execution, use
[Verify my changes](verify-my-changes.md). Replay the agreed workload with equivalent concurrency and warmup.
Verify with `get_threads` that the event loop remains responsive and worker threads do not saturate, and verify
with `get_request_profile` that handler duration improved without errors.

## Stop and report

Stop when permissions are missing, external profiling is unauthorized, the budget expires, or evidence is inconclusive.
Report the observed thread states, event-loop task counts, SQL vs handler duration split, and confirmed or unverified
status. Clearly document any tooling limitations (such as absence of heap dumps) rather than claiming an unmeasured
property is healthy.
