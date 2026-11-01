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
| **Depends on** | F (PLAN.md). Consumes F's F1a table (`F-foundation.md`): the 401/403 hook in `fastapi/capture.py`, `fastapi/routes/security_logs.py`, the `implemented` flag, the settings field `security_logs_max_logs`, the MCP stub module, `tests/golden.py::assert_parity`, the `ui/src/views/SecurityLogs.svelte` placeholder, the `tests/safety/` + `tests/masking/` helpers. **Ordering:** if both run, this lane merges **before D2** (both edit `fastapi/capture.py`; D2 rebases onto it) |
| **May touch** | `src/sharpit/engine/capture/securitylogs.py` (new), F's 401/403 hook body in `src/sharpit/fastapi/capture.py`, `src/sharpit/__init__.py` (one export line: `record_security_event`), `src/sharpit/fastapi/routes/security_logs.py` (F stub), the panel's pre-registered rows, F's MCP stub, `ui/src/views/SecurityLogs.svelte` (replace F's placeholder) + `.test.ts`, `tests/engine/capture/test_securitylogs.py`, `tests/fastapi/test_security_logs_api.py`, `tests/fastapi/test_security_logs_overhead.py`, `tests/safety/test_b_security_logs_safety.py`, `tests/masking/test_b_security_logs_masking.py`, `tests/fixtures/bootui/2.2.0/security-logs/*`, `skills/sharpit/SKILL.md` + `README.md` (Task 4 usage only), the implementer files in the lane folder (C2) |
| **Must NOT touch** | §10.3 protected files; `engine/capture/logtail.py` (this is not a log filter); `engine/guard.py`; `fastapi/capture.py` beyond F's 401/403 hook body; other lanes' modules; `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5); any `review.md` or `gate/` path |

**Architecture:** `SecurityEventBuffer` (deque, `maxlen = clamp(security_logs_max_logs, 1, 10000)`, default 500) on
`CaptureState` (`engine/capture/__init__.py:26`; the slot is in F's F1a table); events stored raw-but-bounded (`timestamp_ns`, `principal`, `type`, `data` dict copied, `request_id`)
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

**Files:** F's hook in `src/sharpit/fastapi/capture.py` (the `finally` of `CaptureMiddleware.__call__`, `:363`
today, where `status` is known; F's F1a table names its post-F location); `src/sharpit/engine/capture/securitylogs.py` (`register(ctx)`, `unregister(ctx)`,
`record_security_event(type: str, principal: str | None = None, **data: object) -> None`, `principal_of(user: object)
-> str | None`); `src/sharpit/__init__.py` export; Tests in `tests/engine/capture/test_securitylogs.py` and
`tests/fastapi/test_security_logs_api.py`.

**Interfaces:** hook data `{"method": info.method, "path": info.path, "status": status}`; 401 →
`AUTHENTICATION_FAILURE`, 403 → `AUTHORIZATION_FAILURE`; sharpit's own traffic is already skipped before the hook
(`under(route_path(scope), self.ctx.settings.path)`, `fastapi/capture.py:297`).

- [ ] **Step 1:** Tests: `test_401_becomes_authentication_failure`, `test_403_becomes_authorization_failure`,
  `test_200_records_nothing`, `test_sharpit_403_not_recorded`, `test_record_goes_to_the_current_apps_context_only`,
  `test_record_outside_request_is_noop`, `test_record_when_inactive_is_noop`, `test_principal_never_runs_user_properties`,
  `test_record_bad_args_never_raises`, `test_event_in_request_carries_request_id`
  (`# ported: SecurityLogsControllerTests.anEventPublishedDuringARequestCarriesItsRequestId`),
  `test_hook_raising_is_swallowed` (one `hook_failed` warning, response unchanged).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS. Commit `feat: security events from 401/403 and record_security_event`.

### Task 3: Routes, stream, MCP, safety, budget

**Files:** `src/sharpit/fastapi/routes/security_logs.py` (F stub), flag flip; Tests
`tests/fastapi/test_security_logs_api.py`, `tests/fastapi/test_security_logs_overhead.py`,
`tests/safety/test_b_security_logs_safety.py`, `tests/masking/test_b_security_logs_masking.py` (C5).

**Interfaces:** `GET {api}/security-logs?principal=&type=&after=&offset=&limit=`, `GET {api}/security-logs/stream`
(SSE `update`, reuse `fastapi/sse.py:72::sse_response` + `engine/capture/streams.py:221::change_events`; if the shared stream's coalescing differs from
BootUI's 750 ms, log §11 — do not change the shared stream). MCP `get_security_logs` (read, `limit`, default 20).
`actionCapable=False`. Unavailable (capture middleware not attached): `auditEventsPresent: true`, `unavailableReason:
"Request capture is unavailable: install() ran after the app started; only record_security_event() events are shown"`.

- [ ] **Step 1:** Tests: `test_golden_parity` (`assert_parity("security-logs", "report", body)`; fixture
  `tests/fixtures/bootui/2.2.0/security-logs/report.json` + `nullable.json`, C3), `test_events_newest_first_bounded` (`# ported: SecurityLogsControllerTests.eventsAreNewestFirstAndBoundedByConfiguredMaximum`),
  `test_filters` (`# ported: SecurityLogsControllerTests.filtersByPrincipalTypeAndAfter`), `test_masks_and_metadata_only`
  (`# ported: ...masksSensitiveEventDataAndHidesValuesInMetadataOnlyMode`), `test_unavailable_when_capture_missing`
  (`# ported: ...absentAuditRepositoryReturnsUnavailableReport`, sharpit reason), `test_invalid_after_is_400`,
  `test_get_no_side_effects` (GET + stream), `test_mcp_read_tool_only`, `test_panel_disabled_drops_events`; budget:
  paired on/off over 200-status requests (`tests/overhead.py::paired` + `check_budget`), `BUDGET_NS = 2_000` per
  request added by the hook, a new constant in the new file.
- [ ] **Step 2:** FAIL on assertions (F's unimplemented panel answers 404; never an `ImportError`, C4) → **Step 3:** implement → **Step 4:** PASS + full gate. Commit `feat: security-logs routes, stream and MCP read tool`.

### Task 4: Svelte view, docs, live check, evidence

- [ ] **Step 1:** Replace F's placeholder `ui/src/views/SecurityLogs.svelte`, flip the panel's `implemented` in F's
  `ui/src/lib/nav.ts` wiring (flag only); vitest (type summaries, filters, masked badge, refetch on
  `update`). `npm --prefix ui run check` PASS.
- [ ] **Step 2:** `skills/sharpit/SKILL.md` + README: `record_security_event` usage (success events only come from it).
- [ ] **Step 3:** Live on tiny-ledger-py / `examples/fastapi_sample` (a 401 route); record requests in `handoff.md`
  §Live check (`live-verify.md` is the coordinator's, C2); lowest-direct + no-SQLAlchemy as a local pre-check only. Commit
  `feat: security-logs view, docs and lane evidence`.

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
