# Lane U20-memory: memory and runtime depth (spike now; build only with O3/O4)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.
> **Task 0 (spike) may run now. Tasks 1–4 wait for the spike verdict and the owner's answers to O3 and O4
> (OWNER-ONLY).**

| | |
|---|---|
| **Lane id** | `U20-memory` (worktree `C:\development\github\sharpit-wt\0.5.0-U20-memory`, branch `lane/0.5.0-U20-memory`) |
| **Goal** | Fill `activity`'s BootUI memory keys with honest Python measures and add test-session memory facts (per-route allocation, retained growth over N requests), **without any hook during normal serving**. |
| **Spec** | §7.1, §9 |
| **Contract** | `activity/resources.captured.json`, `activity/journal.captured.json` (routes built by D2), `activity/captured.json` (`heapUsedBytes`, `heapMaxBytes`, `heapCommittedBytes`, `heapAfterGcBytes`, journal `gc`); test-session facts are `sharpit-report/1` additive |
| **Worker** | claude-flavio (Opus); reviewer codex |
| **Council** | **required** (interpreter state; a GET-rule clarification) |
| **Depends on** | spike verdict + O3/O4; D2 (R0: `engine/capture/activity.py`; it builds `/activity/resources` and `/activity/journal`); R0 next: T-unbounded-read-2 (`facts.py`, `gates.py`) |
| **May touch** | `src/sharpit/engine/capture/activity.py` (memory keys from the sampler), `src/sharpit/engine/capture/memory.py` (new: RSS/limit readers if O3, `gc.get_stats()` diff), `src/sharpit/engine/testsession/memory.py` (new: tracemalloc snapshot diff, retained growth), `src/sharpit/engine/testsession/facts.py`, `src/sharpit/engine/testsession/gates.py` (finding `sharpit.memory-growth`), `src/sharpit/pytest_plugin/session.py`, `src/sharpit/pytest_plugin/marker.py`, `src/sharpit/pytest_plugin/options.py` (`--sharpit-memory`), `src/sharpit/settings.py` (`memory_*` rows: only this lane adds them, after O3), `tests/engine/capture/test_memory.py`, `tests/engine/testsession/test_memory.py`, `tests/pytest_plugin/test_plugin_memory.py`, `tests/safety/test_u20_memory_safety.py`, `docs/superpowers/spikes/2026-11-xx-memory.md`, the lane folder. If O4 = yes: `src/sharpit/engine/memray.py`, `pyproject.toml`, `uv.lock` (allowed for this lane by F5-gate's `ALLOWED_PATHS`) |
| **Must NOT touch** | `fastapi/capture.py` (no serving hook), `gc.callbacks` anywhere, guard, budget constants, `tests/engine/test_import_boundary.py` (F5a owns the call-site rule) |

## Must-cover

`test_get_leaves_interpreter_state_untouched` (covered generically by F5a's `SideEffectGuard`; this lane runs it over
activity/overview and every MCP tool), `test_gen2_count_from_gc_stats_diff`, `test_memory_off_by_default`,
`test_tracemalloc_started_by_us_is_stopped`, `test_tracemalloc_started_by_user_is_left_running`,
`test_tracemalloc_frame_depth_restored`, `test_memory_session_failure_restores_state`,
`test_duplicate_attach_is_idempotent`, `test_retained_growth_flags_leak_fixture`, `test_clean_route_not_flagged`,
`test_memory_keys_null_with_reason_without_o3`.

## Task 0: spike (`/sharpit:spike`, 2 h, scratch branch, no merge)

1. `tracemalloc` overhead per request at 1 and 25 frames; does a snapshot diff around one request attribute to the
   route under `TestClient` and under xdist?
2. Retained growth: after N = 50 identical requests and `gc.collect()`, does `snapshot.compare_to` show a leak fixture
   and nothing for a clean route?
3. `gc.get_stats()[2]["collections"]` sampled every activity tick: is the per-minute rate stable?
4. RSS/limit sources per platform (Linux cgroup v1/v2, macOS `ru_maxrss`, Windows none).
5. (O4 input only) `memray` in a scratch venv: capture size and overhead.
Under multi-agent load the numbers are marked "loaded" and re-measured in a quiet window before any owner call.
Verdict: `docs/superpowers/spikes/2026-11-xx-memory.md`.

## Task 1: activity memory keys
- [ ] Red commit (fake readers; skeleton returns `None`): `test_gen2_count_from_gc_stats_diff` (two ticks with a
  forced `gc.collect(2)` between → journal `gc` event; expected failure: no event), `test_memory_keys_null_with_reason_without_o3`
  (O3 = no or a non-Linux platform: keys `null`, reason present), `test_get_leaves_interpreter_state_untouched`; the
  three activity goldens stay green.
- [ ] Implement in the sampler only. If O3 = yes: RSS and `memory.max` behind `SHARPIT_MEMORY_PROC_READS` (default
  off). Commit `feat: activity memory from gen-2 collection counts`.

## Task 2: test-session memory facts
- [ ] Red commit (pytester): `test_memory_off_by_default`, `test_retained_growth_flags_leak_fixture`,
  `test_clean_route_not_flagged`, and the lifecycle set: `test_tracemalloc_started_by_us_is_stopped`,
  `test_tracemalloc_started_by_user_is_left_running` (user's tracing and frame limit unchanged after the session),
  `test_tracemalloc_frame_depth_restored`, `test_memory_session_failure_restores_state` (an exception inside the
  session's memory hook), `test_duplicate_attach_is_idempotent`.
- [ ] Implement; ownership rule: sharpit records `tracemalloc.is_tracing()` and the frame limit before starting and
  restores exactly that. Finding `sharpit.memory-growth` additive; fingerprint = route + growth site. Commit
  `feat: test-session memory growth findings`.

## Task 3: overhead
- [ ] `test_memory_session_overhead_budget` (new constant in a new file; prove it bites with a `time.sleep(0.0001)`
  in the snapshot hook, then remove). Under load: `parked: budget under load`, re-measured paired in a quiet window.

## Task 4: memray on demand (only if O4 = yes; advisor recommends out)
- [ ] `test_memray_capture_is_cli_only_action`, `test_memray_absent_is_unavailable`; gatekeeper `engine/memray.py`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/U20-memory/`: `council.md`, `handoff.md`, `findings.md`, `field-map.md` (activity
memory keys → Python source), `checklist.md`.
