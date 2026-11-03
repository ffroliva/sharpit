# Lane W-workload: defined-workload compare and sweep (U17, gated)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. **Task 0 is a spike; nothing after it
> starts until the owner answers spec §13 O5.**

| | |
|---|---|
| **Lane id** | `W-workload` (worktree `C:\development\github\sharpit-wt\0.5.0-W-workload`, branch `lane/0.5.0-W-workload`) |
| **Goal** | A jvm-pulse-style defined workload: run a declared set of requests in-process, compare two runs or sweep a parameter, and write one offline, shareable, masked report. Flagging per request with a configurable minimum count; "insufficient evidence" distinct from "clean". |
| **Spec** | §7.3 |
| **Source** | upstream tracker U17 (BootUI needs 3 requests per route; sharpit flags per request: keep that, make the count configurable) |
| **Worker** | codex gpt-6-luna (or claude-flavio if U20 is done and codex is busy); reviewer the other |
| **Council** | **required** (a new action surface that drives the host app) |
| **Depends on** | owner O5; U20-memory (R0: `pytest_plugin/options.py`); spike verdict |
| **May touch** | `src/sharpit/engine/workload/` (new: `spec.py` (TOML via `tomllib`), `runner.py` (drives an ASGI callable passed in; no Starlette import in the engine: the adapter passes a `send(method, path, body) -> (status, elapsed_ns, facts)` callable), `compare.py`, `report.py`), `src/sharpit/fastapi/workload.py` (adapter: `httpx.ASGITransport` or Starlette `TestClient`, in-process), `src/sharpit/__main__.py` or the CLI module (`sharpit workload run|compare|sweep`), `src/sharpit/pytest_plugin/options.py` (`--sharpit-min-requests`), `src/sharpit/engine/testsession/gates.py` (evidence sufficiency: `insufficient` status per rule), `tests/engine/workload/`, `tests/fastapi/test_workload.py`, `tests/safety/test_w_workload_safety.py`, `docs/workload.md`, `docs/superpowers/spikes/2026-11-xx-workload.md`, the lane folder |
| **Must NOT touch** | any GET route or MCP tool module (the workload is not reachable from either); `settings.py`; budgets |

## Review Focus

1. Zero sockets: the run is in-process; a socket spy counts no `connect`.
2. The report is masked aggregates only: no request or response body, no header value.
3. Not reachable from a GET, an MCP tool or a running sharpit mount.

## Task 0: spike (2 h)

1. Does `httpx.ASGITransport` (optional, already a test dep?) or Starlette `TestClient` give per-request facts
   (queries, findings) through the existing capture correlation without a running server?
2. Report format candidates for O5 (single-file HTML with inline data, JSON + Markdown): size on the bench corpus.
3. Noise: coefficient of variation of p50/p95 over 5 runs of 200 requests; the minimum run length for a compare to
   mean anything (the report prints it).
Verdict: `docs/superpowers/spikes/2026-11-xx-workload.md`.

## Task 1: spec and runner (engine)
- [ ] Red commit: `test_workload_spec_parses_and_bounds` (request count clamped to a documented max, warning),
  `test_runner_per_request_facts`, `test_min_requests_insufficient_vs_clean` (`--sharpit-min-requests 3`, one request
  → `insufficient`, not `clean`; default 1 → flagged on the first request).
- [ ] Implement. Commit `feat: defined workload runner`.

## Task 2: compare, sweep, report
- [ ] Red commit: `test_compare_two_runs_deltas`, `test_sweep_parameter_series`, `test_workload_report_masked`
  (responses holding tokens; report has none), `test_report_is_self_contained` (no network reference).
- [ ] Implement in O5's format. Commit `feat: workload compare, sweep and offline report`.

## Task 3: CLI and safety
- [ ] Red commit: `test_workload_opens_no_socket`, `test_workload_not_reachable_from_get_or_mcp` (route table and
  `tools/list` contain nothing workload), `test_workload_refuses_without_app`. Implement the CLI. Commit
  `feat: sharpit workload CLI`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/W-workload/`: `council.md`, `handoff.md`, `findings.md`, `checklist.md`.
