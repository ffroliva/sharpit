# D2 handoff: capture-panel drift to BootUI 2.2.0

Implementer: Claude Code subagent (claude-opus-5-5)

- Base: 78706ac (release/0.5.0). Head: 1330118895831f2b88d485b5d2f33027f18c1196. Status: ready-for-review, with the coordinator edits below.
- Slot lines re-read on release/0.5.0 (delta 1): `fastapi/capture.py` `CaptureMiddleware.__call__` builds the row in its
  `finally` block (`exchange_row(...)`, after the security-event hook and `REQUEST.reset`); `fastapi/install.py` was not
  touched (no construction change needed: `durationMicros` is computed in `SqlTraceRecorder.record`). The capture routes
  live in `fastapi/routes/__init__.py` (not May-touch): the 2.2.0 routes are new modules under `fastapi/routes/` spliced
  first by `fastapi/adapter.py::_with_drift_routes` (a drift route with the same path and methods replaces the base one).

## Done

| Task | Red SHA | Fix SHA |
|---|---|---|
| 1 http-exchanges: route/routeSource/requestId, retention, `?route=`, `GET /http-exchanges/routes`, `get_http_routes` | e1895b79a2a52339feacc76c40339e77168e2073 | ec7470d2c8d561c37da574ba1a81277fc359b9a1 |
| 2 sql-trace `durationMicros` + retention, log-tail `messageOmitted`, exceptions `caughtInCode` + `GET /exceptions/caught`, MCP query/limit views | f6ae586e223b3a5eb8c8c4e393f2e51d172844f4 | 4d5a2a3c6ec25d7c15b4ab866756124b50182477 |
| 3 activity profile keys, journal-only filter warning, `GET /activity/journal`, `GET /activity/resources`, `get_request_profile`, `get_live_activity` QUERY_LIMIT | f7429daae5488f5d022d50b976ef187b3bcfe3d9 | 37d49a25acf902fd5c49918740b30bc72d79385f |

Per-test reds, pins and their mutation proofs, and the paired overhead runs: `findings.md`. Per-key map: `field-map.md`.

## Must-cover

| Test | Status at head |
|---|---|
| tests/fastapi/test_activity_api.py::test_activity_resources_golden_parity | exists, passes |
| tests/fastapi/test_activity_api.py::test_activity_journal_golden_parity | exists, passes |
| tests/fastapi/test_http_exchanges_api.py::test_http_routes_golden_parity | exists, passes |
| tests/fastapi/test_exceptions_api.py::test_exceptions_caught_golden_parity | exists, passes |
| tests/safety/test_d2_safety.py::test_capture_drift_get_no_side_effects | exists, passes |
| tests/safety/test_d2_safety.py::test_new_tools_read_only | exists, passes |
| tests/engine/capture/test_http_routes.py::test_capture_overhead_budget_unchanged | exists, passes (pin, mutation-proven) |

## Gates (lane worktree)

- `ruff check`, `ruff format --check`: clean. `pyright`: 0 errors.
- Full suite (`pytest -q -n 4`): 5293 passed, 7 failed, 24 skipped at 37d49a2 (log: integration logs/D2-pytest.log). 1330118 then fixed the one D2-caused failure there (tests/test_foundation_suite_equivalence.py: the drift routes are now spliced in place, base order kept; re-run green). tests/engine/test_n_plus_one_overhead.py failed only under that run's load (11 min suite) and passes alone (13 s); its path is untouched. The remaining 5 are listed below.
- Failures at head, none caused by a D2 defect: the shared pins below need the coordinator's edit, and
  `tests/fastapi/test_security_api.py::test_mcp_tools_list_has_only_get` already fails at base 78706ac
  (`get_security_logs` from B-security-logs matches its "security" filter).

## Coordinator rulings applied (after merging release/0.5.0, merge commit on this branch)

- Q1 (corrected ruling): the four new base GET routes are appended to `tests/test_safety_matrix.py::ROWS` (rows only,
  commit abddfe0330ca2484934d9646e26daded8250d8f5; pass `--allow-path tests/test_safety_matrix.py` to the gate);
  `GET_ROWS` removed from `tests/safety/test_d2_safety.py`, which keeps `TOOL_ARGS`/`TOOL_SEEDS` and the lane tests.
  Matrix, tool, surface, safety and masking tests: 1476 passed, 2 skipped.
- Q2: `tests/surface.py` lists `get_http_routes` and `get_request_profile` at the end of the tool and CLI lists; the two
  tools moved to the end of `_BASE_TOOLS` in `engine/tools.py` so the catalogue order matches the appended names.
- Follow-ups (left as ruled): (a) `fastapi/routes/activity.py` overwrites the `activity` name in
  `routes/__init__.py`; `adapter.py` puts it back (commented `shortcut:`). Rename or move it when that file may change.
  (b) MCP compacted default limits need the "limit was given" fact that `engine/tool_dispatch.py` drops.

## Full suite after the rulings

5295 passed, 5 failed, 24 skipped (log: integration logs/D2-pytest2.log, a 10-minute run under machine load). The
four budget failures (capture, security-logs, n+1, sql-trace overhead) pass when re-run alone (5 passed, 31 s); the
remaining failure, `test_get_route_table_is_complete`, now passes (Q1 above).

## Decisions

- `routeSource` is `FRAMEWORK_TEMPLATE` (FastAPI's `scope["route"].path`, behind its mounts) or `MASKED_PATH`
  (`sqlinsights.mask_route` of the masked path). `DECLARED_MAPPING` is not produced; the second note says so.
- `topFor` criteria are REQUESTS, TOTAL_DURATION, P95_DURATION: the golden tags every route of a 5-route window with
  exactly those three (the contract example's `TOTAL_TIME` disagrees with the capture).
- Retention: `reservedCapacity`/`reserved` (and `slowThresholdMillis` for exchanges) are null with nullable.json
  reasons: sharpit's rings are plain deques with no reserved share.
- Journal and resources are honest-unavailable: `enabled: false` / `available: false`, nulls listed in
  `activity/nullable.json` (U20 fills the memory keys later, delta 2).
- `GET /exceptions/caught` uses the plan's reason string.
- Not built: `POST /activity/journal/clear` and `GET /activity/request/{id}/journal` (no journal to clear or read;
  a write route would also need a matrix WRITES row), sql-trace entry keys `requestId/executionId/threadKind/requestPhase`
  (not in the plan), UI view changes (existing views ignore the added keys).

## How to resume

Branch `lane/0.5.0-D2` is committed through 1330118895831f2b88d485b5d2f33027f18c1196. Next: the coordinator's edits above, then review.
