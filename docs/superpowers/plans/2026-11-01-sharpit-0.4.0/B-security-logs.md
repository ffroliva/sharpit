# Lane B-security-logs: `security-logs` (audit ring buffer, best effort)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development, one task at a time,
> `/sharpit:check` before every commit. **No code before Task 0's council verdict.**

| | |
|---|---|
| **Lane id** | `B-security-logs` (worktree `...\0.4.0-B-security-logs`, branch `lane/0.4.0-B-security-logs`); best effort |
| **Goal** | BootUI's `SecurityLogsReport` from a dedicated, bounded, masked audit ring buffer fed by 401/403 exchanges and by a public `sharpit.record_security_event()`, with BootUI's `update` change stream. |
| **Spec** | §2, §4, §6.1 (3: masking of security event data), §8 intro, §8.1 row `security-logs` (every clause), §11 ("`security-logs` has a sharpit recording API") |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §4; BootUI `SecurityLogsService.java`, `SecurityLogsController.java`, `SecurityLogsReport`, `SecurityLogEventDto`, `SecurityLogDataDto`, `SecurityLogTypeSummaryDto` |
| **Worker** | M, security lane → claude-flavio; reviewer another family + `ponytail-review` (capture middleware) |
| **Depends on** | F (PLAN.md). Consumes these rows of F's consumer interface table (`F-foundation.md`): `sharpit.engine.capture.CaptureState.security_logs` (`Any | None = None`), `sharpit.fastapi.capture.CaptureWiring.on_security_event` and "401/403 capture hook" ( `Callable[[Scope, int], None] | None`; the consumer reads `scope["method"]` / `scope["path"]`), "Pre-created settings fields" (`security_logs_max_logs`), `sharpit.fastapi.routes.<id>` (`routes/security_logs.py`), "implemented flag files" (`engine/panels04/<id>.py` + `ui/src/lib/panels04/<id>.ts`, O4, here `security_logs`), `sharpit.engine.tools04.<id>` (`engine/tools04/security_logs.py`, `TOOLS = ()` until this lane fills it, R3), `tests.golden.assert_parity` (O2), the `ui/src/views/SecurityLogs.svelte` placeholder; F's `examples/fastapi_sqla` wiring (O3: a route that answers 401). `tests/safety/` + `tests/masking/` are F-rest pieces: if absent, the lane creates its own two test files. **Ordering (R0):** the May-touch lists overlap on `fastapi/capture.py`, so the chain is serial: `A-traces → B-security-logs → D2`. This lane does not start while A-traces is in flight and D2 does not start while this lane is; each rebases onto the previous merge |
| **May touch** | `src/sharpit/engine/capture/securitylogs.py` (new: buffer, report, the hook callable, `record_security_event`), the one assignment of `CaptureState.security_logs` and `CaptureWiring.on_security_event` at the attach point F's hook row names (no other line of `src/sharpit/fastapi/capture.py`), `src/sharpit/__init__.py` (one export line: `record_security_event`), `src/sharpit/fastapi/routes/security_logs.py` (F stub), `src/sharpit/engine/panels04/security_logs.py` and `ui/src/lib/panels04/security_logs.ts` (flag flip only, O4), `src/sharpit/engine/tools04/security_logs.py` (the `get_security_logs` tool replaces F's `TOOLS = ()`), `ui/src/views/SecurityLogs.svelte` (replace F's placeholder) + `.test.ts`, `tests/engine/capture/test_securitylogs.py`, `tests/fastapi/test_security_logs_api.py`, `tests/fastapi/test_security_logs_overhead.py`, `tests/safety/test_b_security_logs_safety.py`, `tests/masking/test_b_security_logs_masking.py`, `tests/fixtures/bootui/2.2.0/security-logs/nullable.json` (O2), the implementer files in the lane folder (C2) plus `docs.md` (O3) |
| **Must NOT touch** | §10.3 protected files; `engine/capture/logtail.py` (this is not a log filter); `engine/guard.py`; `engine/tools.py` (R3); `fastapi/capture.py` beyond that one assignment (F already calls the hook with `(scope, status)` on 401/403, before `REQUEST.reset(token)`, R12); `CaptureState` fields (F added `security_logs`); `PANELS`, `nav.ts`, `App.svelte`, `types.ts` (O4); `captured.json` / `provisional.json` (O2); `README.md`, `skills/sharpit/SKILL.md`, `examples/`, `tests/test_example_app.py` (O3); other lanes' modules; `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5); any `review.md` or `gate/` path |

**Architecture:** `SecurityEventBuffer` (deque, `maxlen = clamp(security_logs_max_logs, 1, 10000)`, default 500) in
F's slot `CaptureState.security_logs` (`CaptureState` at `engine/capture/__init__.py:26`); events stored raw-but-bounded (`timestamp_ns`, `principal`, `type`, `data` dict copied, `request_id`)
and masked **at read** with the live exposure policy (BootUI masks per read). A module-level
`WeakValueDictionary[str, SharpitContext]` keyed by `context_id` is filled at install only when the panel is
implemented and enabled; `record_security_event` looks up `REQUEST.get().context_id` there
(`REQUEST` at `engine/capture/correlation.py:23`, `RequestInfo.context_id` at `:15`), so it is a no-op outside a request, for an inactive sharpit, or for another app.

## Global Constraints

- Principal from `scope.get("user")` only (never `request.user`); `UnauthenticatedUser` → `null`; otherwise
  `identity` read with `inspect.getattr_static` and used only when it is a plain value (not a `property` or other
  descriptor), else `type(user).__name__`. Never `display_name`, never `is_authenticated` on a user class.
- Masking (contract §4, verbatim rules): `METADATA_ONLY` → `value` and `principal` `null`; `MASKED` + `mask_secrets` and
  (secret key name **or** normalised key contains `sessionid`, `remoteaddress`, `remoteaddr`, `ipaddress`) →
  `"******"`, `masked: true`; > 256 chars → first 256 + `"..."`, `truncated: true`; ≤ 20 entries sorted by key, then
  `{"name":"...","value":"<n> more entries omitted","masked":false,"truncated":false}`. Paths masked with
  `masker.mask_path` before storage.
- `timestamp` is an ISO-8601 instant string (`2026-11-01T10:15:30.120Z`), not epoch ms (contract; logged §11).
- Hot path (the hook on every response) is a status compare; anything else only on 401/403; overhead budget test.
- `record_security_event` never raises into the app (bad args → one warning, dropped).
- `# ported:` citations. PT018.
- Red is an assertion (R2): each task's red is a **red commit** (subject starts `test:`) with the failing tests plus the
  minimal stubs that make them import; a stub returns a wrong value, never raises `NotImplementedError`. Record its SHA
  per red test in `findings.md` and `handoff.md`; `lane_gate.py` replays each test at that SHA (needs `AssertionError`)
  and at the lane head (must pass). Every "FAIL" step below means this red commit.

## Review Focus

1. **Cross-app leak**: two FastAPI apps, each `install()`ed, an event recorded while handling app A. Expect it only in
   A; outside any request → dropped; sharpit inactive on A → dropped. Pinned in Task 2:
   `test_record_goes_to_the_current_apps_context_only`.
2. **A user object with hostile properties** (`identity` property that raises or does I/O; `display_name` that
   raises; Starlette `SimpleUser`). Expect no user code run and principal `"SimpleUser"`/type name. Pinned in Task 2:
   `test_principal_never_runs_user_properties`.
3. **Secrets in `data`** (`token=`, `password=`, a `session_id`, a client IP, a 10 kB value, 30 keys). Pinned in
   Task 1: `test_masks_sensitive_data_entries` (`# ported: SecurityLogsServiceTests.masksSensitiveDataEntries`) and a
   row in `tests/masking/test_b_security_logs_masking.py` in Task 3.
4. **`after` input**: naive datetime, garbage, `Z`, `+02:00`. Expect 400
   `{"error": "Invalid 'after' parameter: expected an ISO-8601 instant with an offset"}` (never echoing the value) for
   the first two. Pinned in Task 3: `test_invalid_after_is_400` (`# ported: SecurityLogsControllerTests.invalidAfterParameterReturnsBadRequest`).
5. **Burst of 401s** (credential stuffing in a dev loop, 50 000 events). Expect bounded memory (`maxLogs`), newest
   kept, stream coalesced. Pinned in Task 1: `test_buffer_bounded_newest_kept`.

---

### Task 0: Predict and council (spec §8)

- [ ] **Step 1:** `/sharpit:predict` → `.superpowers/sdd/0.4.0/lanes/B-security-logs/predict.md`. **Step 2:**
  `/sharpit:llm-council --tier high` on this plan → `.../B-security-logs/council.md`; apply changes here in a `docs:`
  commit before any code.

### Task 1: `SecurityEventBuffer` and the report

**Files:** `src/sharpit/engine/capture/securitylogs.py`; Test `tests/engine/capture/test_securitylogs.py`.

**Interfaces:** `AUTHENTICATION_FAILURE`, `AUTHORIZATION_FAILURE`, `AUTHENTICATION_SUCCESS` constants;
`SecurityEventBuffer(max_logs: int)` with `add(type: str, principal: str | None, data: Mapping[str, object],
request_id: str | None) -> None`, `changes: ChangeStream`; `security_logs_report(buffer: SecurityEventBuffer | None,
masker: Masker, *, principal: str | None, type: str | None, after_ns: int | None, offset: int | None, limit: int | None,
unavailable_reason: str | None) -> dict[str, Any]` (filter exact/trimmed → newest first → `typeSummaries` count desc,
type asc → page via `engine/paging.py`); `parse_after(raw: str | None) -> int | None` (`datetime.fromisoformat`, offset
required, raises `ValueError`); `clamp_max_logs(n: int) -> int`.

- [ ] **Step 1:** Ported tests (`SecurityLogsServiceTests`): `clampsMaxLogsIntoSafeRange`,
  `sortsNewestFirstSummarizesAndPages`, `masksSensitiveDataEntries`, `filtersByPrincipalTypeAndAfter`,
  `carriesTheRequestIdEachEventWasPublishedUnder`, `passesTraceIdThroughToTheDto` (`traceId` = request id, as
  `exchanges.trace_id` does); plus `test_buffer_bounded_newest_kept`, `test_metadata_only_hides_values_and_principal`,
  `test_twenty_entries_then_overflow_row`, `test_timestamp_is_iso_instant`.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: security event ring buffer and report`.

### Task 2: Sources: the 401/403 hook and `record_security_event`

**Files:** `src/sharpit/engine/capture/securitylogs.py` (`register(ctx)`, `unregister(ctx)`,
`on_security_event(buffer: SecurityEventBuffer, masker: Masker) -> Callable[[Scope, int], None]` (a closure F's
`CaptureWiring.on_security_event` slot holds; `Scope` under `TYPE_CHECKING` only, engine rule 1),
`record_security_event(type: str, principal: str | None = None, **data: object) -> None`, `principal_of(user: object)
-> str | None`); the one assignment of `CaptureState.security_logs` and `CaptureWiring.on_security_event` (F calls the
hook from the `finally` of `CaptureMiddleware.__call__` (`fastapi/capture.py:363` today) **before** `REQUEST.reset(token)` (R12: the hook reads `REQUEST.get()` for the request id, and after the reset it is `None`), where `status` is known);
`src/sharpit/__init__.py` export; Tests in `tests/engine/capture/test_securitylogs.py` and
`tests/fastapi/test_security_logs_api.py`.

**Interfaces:** the hook receives `(scope, status)` and builds data `{"method": scope["method"], "path":
masker.mask_path(scope["path"]), "status": status}`, principal from `scope.get("user")`, request id from
`REQUEST.get()`; 401 → `AUTHENTICATION_FAILURE`, 403 → `AUTHORIZATION_FAILURE`; sharpit's own traffic is already
skipped before the hook (`under(route_path(scope), self.ctx.settings.path)`, `fastapi/capture.py:297`).

- [ ] **Step 1:** Tests: `test_401_becomes_authentication_failure`, `test_403_becomes_authorization_failure`,
  `test_200_records_nothing`, `test_sharpit_403_not_recorded`, `test_record_goes_to_the_current_apps_context_only`,
  `test_record_outside_request_is_noop`, `test_record_when_inactive_is_noop`, `test_principal_never_runs_user_properties`,
  `test_record_bad_args_never_raises`, `test_event_in_request_carries_request_id`
  (`# ported: SecurityLogsControllerTests.anEventPublishedDuringARequestCarriesItsRequestId`),
  `test_hook_raising_is_swallowed` (one `hook_failed` warning, response unchanged).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: security events from 401/403 and record_security_event`.

### Task 3: Routes, stream, MCP, safety, budget

**Files:** `src/sharpit/fastapi/routes/security_logs.py` (F stub), `engine/panels04/security_logs.py`
`IMPLEMENTED = True` (O4); Tests
`tests/fastapi/test_security_logs_api.py`, `tests/fastapi/test_security_logs_overhead.py`,
`tests/safety/test_b_security_logs_safety.py`, `tests/masking/test_b_security_logs_masking.py` (C5).

**Interfaces:** `GET {api}/security-logs?principal=&type=&after=&offset=&limit=`, `GET {api}/security-logs/stream`
(SSE `update`, reuse `fastapi/sse.py:72::sse_response` + `engine/capture/streams.py:221::change_events`; if the shared stream's coalescing differs from
BootUI's 750 ms, log §11 — do not change the shared stream). MCP `get_security_logs` (read, `limit`, default 20).
`actionCapable=False`. Unavailable (capture middleware not attached): `auditEventsPresent: true`, `unavailableReason:
"Request capture is unavailable: install() ran after the app started; only record_security_event() events are shown"`.

- [ ] **Step 1:** Tests: `test_golden_parity` (`assert_parity("security-logs", "report", body)`; per O2 the loader
  reads G0a's `tests/fixtures/bootui/2.2.0/security-logs/captured.json`, else another worker's `provisional.json`
  (result unverified); the lane writes only `nullable.json`), `test_events_newest_first_bounded` (`# ported: SecurityLogsControllerTests.eventsAreNewestFirstAndBoundedByConfiguredMaximum`),
  `test_filters` (`# ported: SecurityLogsControllerTests.filtersByPrincipalTypeAndAfter`), `test_masks_and_metadata_only`
  (`# ported: ...masksSensitiveEventDataAndHidesValuesInMetadataOnlyMode`), `test_unavailable_when_capture_missing`
  (`# ported: ...absentAuditRepositoryReturnsUnavailableReport`, sharpit reason), `test_invalid_after_is_400`,
  `test_get_no_side_effects` (GET + stream), `test_mcp_read_tool_only`, `test_panel_disabled_drops_events`; budget:
  paired on/off over 200-status requests (`tests/overhead.py::paired` + `check_budget`), `BUDGET_NS = 2_000` per
  request added by the hook, a new constant in the new file.
- [ ] **Step 2:** FAIL on assertions (F's unimplemented panel answers 404; never an `ImportError`, C4) → **Step 3:** implement → **Step 4:** PASS + full gate. Commit `feat: security-logs routes, stream and MCP read tool`.

### Task 4: Svelte view, docs, live check, evidence

- [ ] **Step 1:** Replace F's placeholder `ui/src/views/SecurityLogs.svelte`, set `implemented = true` in
  `ui/src/lib/panels04/security_logs.ts` (O4; `nav.ts` untouched); vitest (type summaries, filters, masked badge, refetch on
  `update`). `npm --prefix ui run check` PASS.
- [ ] **Step 2:** `.superpowers/sdd/0.4.0/lanes/B-security-logs/docs.md`: `record_security_event` usage (success
  events only come from it) and the SKILL row; PLAN Step 5 merges it into README/SKILL (O3: no edit to either here).
- [ ] **Step 3:** Live on `examples/fastapi_sqla` with the 401 route F wired (O3; no example edit), else
  tiny-ledger-py; record requests in `handoff.md`
  §Live check (`live-verify.md` is the coordinator's, C2); lowest-direct + no-SQLAlchemy as a local pre-check only. Commit
  `feat: security-logs view and lane evidence`.

## §6.1 → task (spec order; `checklist.md` adds the evidence paths)

| Item | Task |
|---|---|
| 1 golden parity, `nullable.json`, field map (`traceId` = request id; `requestId` = request id) | 1, 3 |
| 2 `# ported:` citations | 1–3 |
| 3 safety + masking (security event data) | 1–3 |
| 4 gatekeeper | `N/A`: no library imported |
| 5 overhead budget | 3 |
| 6 MCP read-only | 3 |
| 7 Svelte view | 4 |
| 8 four gates + lowest-direct + no-SQLAlchemy | 3–4 (gated logs: coordinator) |
| 9 live check | 4 |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/B-security-logs/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open findings, live-check
  requests), `findings.md` (`finding → test → red output`, each row `fixed` + red-test name or `parked` + reason),
  `field-map.md` (the field map above), `checklist.md` (the ten §6.1 items above in the spec's order, each with an evidence
  path or `N/A` + reason). Task 0 adds `predict.md` and `council.md`; `checklist.md` item 5 records the measured overhead. Review includes `ponytail-review` (capture middleware).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`, reviewer id ≠
  implementer id, head SHA), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path (`lane_gate.py` refuses it).
