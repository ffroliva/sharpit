# Lane T-unbounded-read-2: unbounded reads beyond paged routes (U3/U14, design first)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. **Task 0 is a spike; Tasks 1–3 run
> only on a GO verdict.**

| | |
|---|---|
| **Lane id** | `T-unbounded-read-2` (worktree `C:\development\github\sharpit-wt\0.5.0-T-unbounded-read-2`, branch `lane/0.5.0-T-unbounded-read-2`) |
| **Goal** | Catch the bench's unbounded-read forms that T-unbounded-read (paged routes) misses: non-paged routes that load many entities and return few (`len(query.all())`, Python-side filtering or paging; D09–D11, D16, D18), with evidence "entities loaded vs items returned". |
| **Spec** | §7.4 |
| **Source** | upstream tracker U3, U14; 0.4.0 lane `T-unbounded-read` (`lane/0.4.0-T-unbounded-read`, 21 commits, not on `main` at planning time) |
| **Worker** | codex gpt-6-luna (built T-unbounded-read); reviewer Opus |
| **Council** | not required |
| **Depends on** | T-unbounded-read on `release/0.5.0`; D2 (R0: `fastapi/capture.py`); U20-memory merged **or** parked/declined by the owner (R0: `facts.py`, `gates.py`; council r2 M5). R0 next: W-workload (`gates.py`). Spike may run now; build only on GO |
| **May touch** | `src/sharpit/fastapi/capture.py` (response item count, one block, only on GO), `src/sharpit/engine/capture/correlation.py`, `src/sharpit/engine/testsession/facts.py`, `src/sharpit/engine/testsession/gates.py` (`_unbounded_read_findings`), `tests/fastapi/test_capture_item_count.py`, `tests/fastapi/test_capture_item_count_overhead.py`, `tests/pytest_plugin/test_plugin_unbounded_read_2.py`, `tests/fixtures/apps/unbounded_read_2/`, `docs/superpowers/spikes/2026-11-xx-unbounded-read.md`, the lane folder |
| **Must NOT touch** | `engine/sqla/` (T-unbounded-read's ORM load counting is reused as is), the capture budget constant |

Red rule: PLAN.md §Red rule. Overhead verdicts under multi-agent load are `parked: budget under load` and re-measured
paired in a quiet window.

## Must-cover (GO only)

`test_item_count_overhead_budget`, `test_non_paged_route_loading_10000_returning_10_found`,
`test_export_route_returning_all_not_flagged`, `test_paged_route_behaviour_unchanged`,
`test_streaming_response_skipped_with_limitation`.

## Review Focus

1. The capture middleware cost stays inside its existing budget (never raised).
2. A route returning a large list it really needs (export endpoint) is not a false positive: the rule is "loaded ≫
   returned", ratio and minimum configurable, defaults from the spike.
3. A streaming or non-JSON response is skipped with a limitation, not parsed.

## Task 0: spike (2 h)

Measure, on the capture middleware path, counting the items of a top-level JSON array response: (a) from the response
model before serialisation (FastAPI: the endpoint's return value length, read in a route wrapper), (b) by scanning the
body bytes for top-level commas. Against the capture overhead budget. Verdict file with numbers. NO-GO → append to spec
§14 "unbounded reads: paged routes only; D09–D11, D16, D18 a documented gap", update PARITY notes, close the lane.

## Task 1 (GO): item count
- [ ] Red commit: `test_item_count_recorded_for_json_list`, `test_streaming_response_skipped_with_limitation`,
  `test_item_count_overhead_budget` (new constant in a new file; prove it bites).
- [ ] Implement the spike's chosen method. Commit `feat: record returned item count on captured requests`.

## Task 2 (GO): rule
- [ ] Red commit (pytester, bench twins): `test_non_paged_route_loading_10000_returning_10_found` (D09 twin),
  `test_python_side_filter_found` (D10), `test_len_of_all_found` (D11), `test_export_route_returning_all_not_flagged`,
  `test_paged_route_behaviour_unchanged` (T-unbounded-read's tests stay green).
- [ ] Implement in `_unbounded_read_findings`; message additive, fingerprint per route + statement shape. Commit
  `feat: unbounded reads on non-paged routes`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/T-unbounded-read-2/`: `handoff.md`, `findings.md`, `checklist.md`, spike verdict path.
