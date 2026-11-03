# B-security-logs handoff

Implementer: Claude subagent (claude-opus-5-5)

Status: DONE. The four coordinator questions below are answered (see Coordinator rulings).
Branch `lane/0.5.0-B-security-logs`, worktree `C:\development\github\sharpit-wt\0.5.0-B-security-logs`, base `ae0c227`.
Task 0 (predict + council) skipped on the coordinator's instruction: the council runs on the finished diff.

## Commits

| SHA | Commit |
|---|---|
| d5506b8 | test: security event ring buffer and report (red) |
| bb7c21e | feat: security event ring buffer and report |
| 7796847 | test: security events from 401/403 and record_security_event (red) |
| 78c8458 | feat: security events from 401/403 and record_security_event |
| b76a932 | test: security-logs routes, stream and MCP read tool (red) |
| 191bbaa | feat: security-logs routes, stream and MCP read tool |
| b62dbdc | test: security-logs view (red) |
| 1ef1873 | feat: security-logs view and rebuilt UI bundle |
| 27ef24b | test: security-logs hook budget runs 40 short rounds to settle each side's minimum |
| e6a0c38 | docs: lane B-security-logs evidence |
| 1c4d1e2 | chore: merge release/0.5.0 into lane B-security-logs (UI bundle rebuilt from merged ui/) |
| cc700e5 | test: all-capture-panels-off lists include security-logs (coordinator Q2/Q3) |
| ad1274d | test: security-logs budget in 1000 short rounds and an exact no-lane-code-on-200 check (perf audit) |

Red SHAs, assertions, dispositions, pins and mutation proofs: `findings.md`.

## Attach point (delta 1)

`src/sharpit/fastapi/capture.py`, `CaptureWiring.attach_at_install`, right after `self.app = app` (line 185 at head):
`self.on_security_event = attach_security_logs(ctx)`. `securitylogs.attach(ctx)` is the one place that assigns
`CaptureState.security_logs` (a `SecurityEventBuffer`) and registers the context; it returns the hook or `None`
(panel unimplemented or disabled). The only other line touched in that file is its import. The hook call site
(`sent in (401, 403) and wiring.on_security_event is not None`, before `REQUEST.reset`) is F's and unchanged: a 200
pays one tuple-membership test, as before this lane.

## Decisions

- `record_security_event(type, principal=None, data=None)`: `data` is a mapping, not `**data` (the 0.5.0 delta and
  must-cover write `data={"details": ...}`; a mapping also allows keys such as `type` or `remote-address`, which
  BootUI events carry and `**kwargs` cannot). Exported with one line: `from ... import record_security_event as
  record_security_event` (no `__all__` edit).
- Unavailable reason (no capture middleware) is the capture's own reason, `CAPTURE_TOO_LATE_REASON`, as contract
  [AMBIG] says, not the 0.4.0 plan's "...only record_security_event() events are shown": without the middleware no
  request is correlated, so `record_security_event` records nothing either and that sentence would be false.
  `auditEventsPresent` stays `true`. The engine holds a copy of the string (it may not import the adapter);
  `test_unavailable_when_capture_missing` pins them equal.
- Masking: `Masker.mask` (key, secret value, sharpit token) → the contract's normalised-key markers → `Masker.mask_text`
  over the value (sharpit widening, so `Bearer <jwt>` and `token=...` inside text are scrubbed; the golden's
  `RemoteIpAddress=127.0.0.1` text stays visible, matching the golden). Values are stringified at record time so a
  read never runs host `__str__`. Principal is shown verbatim except `null` under METADATA_ONLY.
- `traceId` = request id (0.4.0 plan); `nullable.json` records why the golden's `null` becomes a string.
- The panels04 flag flipped in the Task 2 feat commit (78c8458): Task 2's tests need the panel enabled.
- MCP `get_security_logs` uses the shared `_LIMIT_ONLY` schema (limit capped by `SHARPIT_MCP_MAX_RESULTS`, as every
  sharpit limit tool); BootUI's guide default 20 is not applied. No required args, so no TOOL_ARGS/TOOL_SEEDS.
- Stream: reuses `change_events` + `sse_response` (shared coalescing, not BootUI's 750 ms; unchanged).

## Coordinator rulings

Q1 done on release (c63623b, merged in 1c4d1e2). Q2/Q3 approved and applied in cc700e5. Q4: perf audit; budget kept
at 2 µs, measurement changed to 1000 × 10 and an exact `sys.setprofile` pin added (ad1274d; findings §Overhead).
The `record_security_event(data=)` and unavailable-reason decisions were accepted; kept above for the council.

## Questions for the coordinator (as asked; answered above)

1. `tests/conftest.py` `TIMING_MODULES`: add `"test_security_logs_overhead.py",  # lane B-security-logs`.
   Without it `tests/test_overhead_harness.py::test_every_budget_module_runs_last` and
   `::test_budget_order_check_survives_a_fixture_conftest` fail (the new budget module is not ordered last).
2. `tests/fastapi/test_capture_wiring.py:34` `CAPTURE_PANELS` and `tests/fastapi/test_capture_overhead.py`
   `CAPTURE_PANELS`: add `"security-logs"`. The panel needs the capture middleware (it is in F's
   `fastapi/capture.py::CAPTURE_PANELS`), so "every capture panel disabled" now has to disable it too:
   `test_all_capture_panels_disabled_adds_nothing[plain|sqlalchemy]` fail, and `test_request_overhead_budget`'s off
   side silently gains the middleware (its number then understates capture's cost; see findings §Overhead).
3. `tests/fastapi/test_transactions_api.py:113` (`test_transactions_alone_does_not_install_capture_middleware`): same
   cause; its disabled tuple needs `"security-logs"`.

4. The plan's `BUDGET_NS = 2_000` for the hook on a 200 is below the harness's resolution (noise 3–88 µs on a
   ~155 µs request; on a 200 both sides run identical code). Alone it passes 4/5 runs; one OVER sat inside the noise.
   Not raised. Options: accept it as load-sensitive like the other budgets, or re-scope the budget to a direct
   paired microbenchmark of the hook on a 401 (the only path that runs lane code).

## Gates (lane head 1ef1873, before the evidence commit)

- `uv run ruff check` / `ruff format --check`: clean on every lane file. `uv run pyright` on the lane's src files: 0
  errors. `npm run check` clean; vitest `SecurityLogs.test.ts` 3/3; `npm run build` committed.
- Full suite (`-n 4`, log `0.5.0-integration/.superpowers/sdd/0.5.0/logs/B-security-logs-pytest.log`): 4926 passed,
  11 skipped, 9 failed: the 6 tests named in the questions above; `test_patch_targets_are_defined_where_called`
  (fails on the base too, same run of the related subset at `ae0c227`); `test_transactions_capture_with_sql_trace_and_discovery_off`
  (order-dependent: passes alone at head, it needs "the only installed context"); and the two budgets
  (`test_security_logs_hook_overhead_budget` 33.7 µs with 88 µs noise, `test_request_overhead_budget`) under full-suite
  load; both re-run alone in findings §Overhead.
- Must-cover, all exist and pass at head: `test_security_event_values_masked_everywhere`, `test_stream_guarded`,
  `test_security_logs_get_no_side_effects`, `test_inactive_security_logs_paths_404`, `test_mcp_tools_list_has_only_get`,
  `test_report_golden_parity`, the overhead budget test (`BUDGET_NS = 2_000`, new file).

## Live check

Not run: the brief forbids dev servers on shared ports, and `examples/` is outside May-touch. The in-process equivalent
is `tests/fastapi/test_security_logs_api.py` (a real FastAPI app, TestClient, 401/403/record, GET, stream, MCP).
Requests for the coordinator's live-verify: `GET /protected` without credentials (expect 401) then
`GET /sharpit/api/security-logs` (one `AUTHENTICATION_FAILURE`, `data` method/path/status); a route calling
`sharpit.record_security_event("AUTHENTICATION_SUCCESS", principal="alice", data={"details": "Bearer <jwt>"})` (value
shows `Bearer ******`, `masked: true`); `GET /sharpit/api/security-logs?after=2026-11-01T10:00:00` (400).

## Docs for PLAN Step 5 (README / SKILL, not edited here)

`sharpit.record_security_event(type, principal=None, data=None)` records an audit event in the console of the app
serving the current request: use it for `AUTHENTICATION_SUCCESS` (FastAPI has no authentication event bus; 401 and
403 responses are recorded on their own as `AUTHENTICATION_FAILURE` / `AUTHORIZATION_FAILURE`). It never raises; outside
a request, with sharpit inactive or the panel disabled it does nothing. SKILL row: `security-logs` | 401/403 exchanges
and `record_security_event()` | `GET /sharpit/api/security-logs?principal=&type=&after=&offset=&limit=`, stream,
MCP `get_security_logs`.

## How to resume

Coordinator: review, council, gate logs, then `lane_gate.py B-security-logs`.
