# Lane U20-memory: memory and runtime depth (gated)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. **Task 0 is a spike; nothing after it
> starts until the coordinator records the spike verdict and the owner's answers to spec §13 O3 and O4.**

| | |
|---|---|
| **Lane id** | `U20-memory` (worktree `C:\development\github\sharpit-wt\0.5.0-U20-memory`, branch `lane/0.5.0-U20-memory`) |
| **Goal** | Fill `activity`'s BootUI memory keys with honest Python measures, and add test-session memory facts: per-route allocation, retained growth over N requests, gen-2 GC rate, RSS vs the cgroup limit, an on-demand memray capture. |
| **Spec** | §7.1, §9 |
| **Contract** | `activity/captured.json`, `activity/resources.captured.json`, `activity/journal.captured.json` (`heapUsedBytes`, `heapMaxBytes`, `heapCommittedBytes`, `heapAfterGcBytes`, journal `gc`); no BootUI contract for the test-session facts (`sharpit-report/1` additive) |
| **Worker** | claude-flavio (Opus); reviewer codex |
| **Council** | **required** (global interpreter state; a GET rule clarification) |
| **Depends on** | spike verdict + O3/O4; T-swallowed-2 (R0: `facts.py`, `session.py`); B-security-logs (R0: `fastapi/capture.py`) |
| **May touch** | `src/sharpit/engine/capture/activity.py` (memory keys from the sampler), `src/sharpit/engine/capture/memory.py` (new: sampler readers, gc callback counter), `src/sharpit/engine/testsession/memory.py` (new: tracemalloc snapshot diff per route, retained growth), `src/sharpit/engine/memray.py` (new gatekeeper, only if O4 = yes), `src/sharpit/engine/testsession/facts.py`, `src/sharpit/engine/testsession/gates.py` (new finding `sharpit.memory-growth`), `src/sharpit/pytest_plugin/session.py`, `src/sharpit/pytest_plugin/marker.py`, `src/sharpit/pytest_plugin/options.py` (`--sharpit-memory`), `src/sharpit/fastapi/capture.py` (attach the gc counter; one block), `src/sharpit/fastapi/routes/activity*.py` (memray action route, if O4), `tests/engine/capture/test_memory.py`, `tests/engine/testsession/test_memory.py`, `tests/pytest_plugin/test_plugin_memory.py`, `tests/fastapi/test_memory_overhead.py`, `tests/safety/test_u20_memory_safety.py`, `tests/engine/test_import_boundary.py` (one row: `tracemalloc`/`gc.callbacks` only in session modules and `engine/capture/memory.py`), `docs/superpowers/spikes/2026-11-xx-memory.md`, the lane folder |
| **Must NOT touch** | existing budget constants; guard; `settings.py` (F5 pre-created `memory_*`) |

## Review Focus

1. A GET or MCP call never starts `tracemalloc`, never touches `gc.callbacks`.
2. The gc callback is an integer add; its budget test bites.
3. No JVM GC advice copied; every key whose Python meaning differs is logged in spec §14.

## Task 0: spike (`/sharpit:spike`, time-boxed 2 h)

Questions, answered by experiment on the bench corpus app and `examples/fastapi_sqla`:
1. `tracemalloc` overhead per request at 1 and 25 frames; does a snapshot diff around one request attribute to the
   route's own allocations under `TestClient` (same thread) and under xdist?
2. Retained growth: after N = 50 identical requests, does `snapshot.compare_to` show a leak fixture (a module-level
   list append) and nothing for a clean route, after `gc.collect()`?
3. `gc.callbacks` cost with an integer-add callback under an allocation-heavy loop.
4. Where RSS and the cgroup limit come from on Linux (cgroup v1/v2), macOS (`resource.getrusage` peak only) and
   Windows (none without ctypes; `null` + reason).
Verdict file: `docs/superpowers/spikes/2026-11-xx-memory.md` (GO / GO-narrowed / NO-GO, numbers).

## Task 1: activity memory keys (if O3 = yes; else keys stay `null` with the reason, Task 1 skipped)
- [ ] Red commit: `test_activity_memory_keys_from_sampler` (fake readers), `test_memory_keys_null_with_reason_without_cgroup`,
  `test_get_leaves_tracing_and_gc_callbacks_untouched` (GET activity/overview + every MCP tool:
  `tracemalloc.is_tracing()` and `len(gc.callbacks)` unchanged), golden parity for the three activity goldens still green.
- [ ] Implement in the sampler (never in the GET). Commit `feat: activity memory from RSS, cgroup limit and gen-2 collections`.

## Task 2: test-session memory facts
- [ ] Red commit (pytester): `test_per_route_allocation_reported_with_marker`, `test_retained_growth_flags_leak_fixture`,
  `test_clean_route_not_flagged`, `test_memory_off_by_default` (no tracemalloc without the marker/flag),
  `test_tracemalloc_stopped_at_session_end_if_we_started_it` (and left running if the user started it).
- [ ] Implement; finding `sharpit.memory-growth` additive, fingerprint = route + growth site. Commit
  `feat: test-session memory growth findings`.

## Task 3: overhead
- [ ] `tests/fastapi/test_memory_overhead.py::test_gc_callback_overhead_budget` (new constant; prove it bites with a
  `time.sleep(0.0001)` in the callback, then remove). Commit `test: gc callback overhead budget`.

## Task 4: memray on demand (only if O4 = yes)
- [ ] Red commit: `test_memray_capture_is_cli_only_action` (absent from `tools/list`; `/cli` only; 403 read-only;
  file under `SHARPIT_STATE_DIR`), `test_memray_absent_is_unavailable` (no import outside `engine/memray.py`;
  boundary row). Implement. Commit `feat: on-demand memray capture`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/U20-memory/`: `council.md`, `handoff.md`, `findings.md`, `field-map.md` (activity
memory keys → Python source), `checklist.md`.
