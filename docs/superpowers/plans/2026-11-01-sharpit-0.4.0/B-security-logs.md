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
| **Depends on** | F (the 401/403 hook in `CaptureMiddleware`, `implemented` flag, settings field `security_logs_max_logs`), D1 |
| **May touch** | `src/sharpit/engine/capture/securitylogs.py` (new), F's 401/403 hook body in `src/sharpit/fastapi/capture.py`, `src/sharpit/__init__.py` (one export line: `record_security_event`), `src/sharpit/fastapi/routes/security_logs.py` (F stub), the panel's pre-registered rows, F's MCP stub, `ui/src/views/SecurityLogs.svelte` (+ test), `tests/engine/capture/test_securitylogs.py`, `tests/fastapi/test_security_logs_api.py`, `tests/fastapi/test_security_logs_overhead.py`, goldens, lane folder |
| **Must NOT touch** | §10.3 protected files; `engine/capture/logtail.py` (this is not a log filter); `engine/guard.py`; other lanes' modules |

**Architecture:** `SecurityEventBuffer` (deque, `maxlen = clamp(security_logs_max_logs, 1, 10000)`, default 500) on
`CaptureState`; events stored raw-but-bounded (`timestamp_ns`, `principal`, `type`, `data` dict copied, `request_id`)
and masked **at read** with the live exposure policy (BootUI masks per read). A module-level
`WeakValueDictionary[str, SharpitContext]` keyed by `context_id` is filled at install only when the panel is
implemented and enabled; `record_security_event` looks up `REQUEST.get().context_id` there
(`engine/capture/correlation.py:22`), so it is a no-op outside a request, for an inactive sharpit, or for another app.

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
- `# ported:` citations. Red is an assertion. PT018.

## Review Focus

1. **Cross-app leak**: two FastAPI apps, each `install()`ed, an event recorded while handling app A. Expect it only in
   A; outside any request → dropped; sharpit inactive on A → dropped. Pinned in Task 2:
   `test_record_goes_to_the_current_apps_context_only`.
2. **A user object with hostile properties** (`identity` property that raises or does I/O; `display_name` that
   raises; Starlette `SimpleUser`). Expect no user code run and principal `"SimpleUser"`/type name. Pinned in Task 2:
   `test_principal_never_runs_user_properties`.
3. **Secrets in `data`** (`token=`, `password=`, a `session_id`, a client IP, a 10 kB value, 30 keys). Pinned in
   Task 1: `test_masks_sensitive_data_entries` (`# ported: SecurityLogsServiceTests.masksSensitiveDataEntries`) and a
   masking corpus row in Task 3.
4. **`after` input**: naive datetime, garbage, `Z`, `+02:00`. Expect 400
   `{"error": "Invalid 'after' parameter: expected an ISO-8601 instant with an offset"}` (never echoing the value) for
   the first two. Pinned in Task 3: `test_invalid_after_is_400` (`# ported: SecurityLogsControllerTests.invalidAfterParameterReturnsBadRequest`).
5. **Burst of 401s** (credential stuffing in a dev loop, 50 000 events). Expect bounded memory (`maxLogs`), newest
   kept, stream coalesced. Pinned in Task 1: `test_buffer_bounded_newest_kept`.

---

### Task 0: Predict and council (spec §8)

- [ ] **Step 1:** `/sharpit:predict` → `predict.md`. **Step 2:** `/sharpit:llm-council --tier high` on this plan →
  `council.md`; apply changes here in a `docs:` commit before any code.

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

**Files:** F's hook in `src/sharpit/fastapi/capture.py` (the `finally` of `CaptureMiddleware.__call__`, `:383`
area, where `status` is known); `src/sharpit/engine/capture/securitylogs.py` (`register(ctx)`, `unregister(ctx)`,
`record_security_event(type: str, principal: str | None = None, **data: object) -> None`, `principal_of(user: object)
-> str | None`); `src/sharpit/__init__.py` export; Tests in `tests/engine/capture/test_securitylogs.py` and
`tests/fastapi/test_security_logs_api.py`.

**Interfaces:** hook data `{"method": info.method, "path": info.path, "status": status}`; 401 →
`AUTHENTICATION_FAILURE`, 403 → `AUTHORIZATION_FAILURE`; sharpit's own traffic is already skipped before the hook
(`fastapi/capture.py:295`).

- [ ] **Step 1:** Tests: `test_401_becomes_authentication_failure`, `test_403_becomes_authorization_failure`,
  `test_200_records_nothing`, `test_sharpit_403_not_recorded`, `test_record_goes_to_the_current_apps_context_only`,
  `test_record_outside_request_is_noop`, `test_record_when_inactive_is_noop`, `test_principal_never_runs_user_properties`,
  `test_record_bad_args_never_raises`, `test_event_in_request_carries_request_id`
  (`# ported: SecurityLogsControllerTests.anEventPublishedDuringARequestCarriesItsRequestId`),
  `test_hook_raising_is_swallowed` (one `hook_failed` warning, response unchanged).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: security events from 401/403 and record_security_event`.

### Task 3: Routes, stream, MCP, safety, budget

**Files:** `src/sharpit/fastapi/routes/security_logs.py` (F stub), flag flip; Tests
`tests/fastapi/test_security_logs_api.py`, `tests/fastapi/test_security_logs_overhead.py`, safety-matrix and corpus rows.

**Interfaces:** `GET {api}/security-logs?principal=&type=&after=&offset=&limit=`, `GET {api}/security-logs/stream`
(SSE `update`, reuse `fastapi/sse.py::sse_response` + `change_events`; if the shared stream's coalescing differs from
BootUI's 750 ms, log §11 — do not change the shared stream). MCP `get_security_logs` (read, `limit`, default 20).
`actionCapable=False`. Unavailable (capture middleware not attached): `auditEventsPresent: true`, `unavailableReason:
"Request capture is unavailable: install() ran after the app started; only record_security_event() events are shown"`.

- [ ] **Step 1:** Tests: `test_golden_parity`, `test_events_newest_first_bounded` (`# ported: SecurityLogsControllerTests.eventsAreNewestFirstAndBoundedByConfiguredMaximum`),
  `test_filters` (`# ported: SecurityLogsControllerTests.filtersByPrincipalTypeAndAfter`), `test_masks_and_metadata_only`
  (`# ported: ...masksSensitiveEventDataAndHidesValuesInMetadataOnlyMode`), `test_unavailable_when_capture_missing`
  (`# ported: ...absentAuditRepositoryReturnsUnavailableReport`, sharpit reason), `test_invalid_after_is_400`,
  `test_get_no_side_effects` (GET + stream), `test_mcp_read_tool_only`, `test_panel_disabled_drops_events`; budget:
  paired on/off over 200-status requests, `BUDGET_NS = 2_000` per request added by the hook.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS + full gate. Commit `feat: security-logs routes, stream and MCP read tool`.

### Task 4: Svelte view, docs, live check, evidence

- [ ] **Step 1:** `ui/src/views/SecurityLogs.svelte` + vitest (type summaries, filters, masked badge, refetch on
  `update`). `npm --prefix ui run check` PASS.
- [ ] **Step 2:** `skills/sharpit/SKILL.md` + README: `record_security_event` usage (success events only come from it).
- [ ] **Step 3:** Live on tiny-ledger-py / `examples/fastapi_sample` (a 401 route) → `live-verify.md`. Commit
  `feat: security-logs view, docs and lane evidence`.

## §6.1 → task

1 parity + field map (`traceId` = request id; `requestId` = request id): 1, 3 · 2 citations: 1–3 · 3 safety/masking
(security event data): 1–3 · 4 gatekeeper: n/a (no library) · 5 budget: 3 · 6 MCP read-only: 3 · 7 Svelte: 4 ·
8 gates: 3–4 · 9 live: 4 · 10 handoff.

## Lane evidence checklist (`.superpowers/sdd/0.4.0/lanes/B-security-logs/`)

`predict.md` · `council.md` · `handoff.md` · `field-map.md` · `checklist.md` (incl. measured overhead) · `findings.md` ·
`review.md` (`VERDICT: APPROVE`, reviewer ≠ implementer, head SHA, plus `ponytail-review`) · `gate/` (four gates, lowest-direct, no-SQLAlchemy logs, each naming the head SHA) ·
`live-verify.md`.
