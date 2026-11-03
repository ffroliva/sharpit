# B-security-logs field map (BootUI `SecurityLogsReport` → sharpit)

Source: `src/sharpit/engine/capture/securitylogs.py` (`security_logs_report`, `context_report`).

| BootUI field | sharpit source | Notes |
|---|---|---|
| `auditEventsPresent` | `True` while the panel's `SecurityEventBuffer` exists; `False` only without a buffer | contract [AMBIG]: always available when capture runs |
| `unavailableReason` | `None`; `CAPTURE_UNAVAILABLE_REASON` (= `fastapi/capture.py` `CAPTURE_TOO_LATE_REASON`) when the capture middleware was not added | the contract's "capture's own reason"; pinned equal by `test_unavailable_when_capture_missing` |
| `maxLogs` | `clamp_max_logs(SHARPIT_SECURITY_LOGS_MAX_LOGS)`, 1..10000, default 500 | |
| `typeSummaries[].type` / `.count` | `Counter` over the filtered, kept events; count desc, type asc | |
| `events[].timestamp` | `format_instant(time.time_ns())` at record time: Java `Instant.toString()` (3/6/9 fraction digits, none on a whole second) | ISO string, not epoch ms (contract) |
| `events[].principal` | 401/403 hook: `principal_of(scope["user"])` (plain `identity` attribute via `inspect.getattr_static`, else the type name; `UnauthenticatedUser`/absent → null); `record_security_event(principal=...)` | null under `METADATA_ONLY` |
| `events[].type` | `AUTHENTICATION_FAILURE` (401), `AUTHORIZATION_FAILURE` (403), or the caller's `type` (`AUTHENTICATION_SUCCESS` only from `record_security_event`, spec §14) | |
| `events[].data[]` | hook: `{method, path (masker.mask_path), status}`; record: the caller's `data` mapping; sorted by key, ≤ 20 rows, then the `"..."` overflow row | values stringified at record time |
| `events[].data[].value` / `.masked` | `Masker.mask` (key name, secret value, sharpit token), then the contract's normalised-key markers (`sessionid`, `remoteaddress`, `remoteaddr`, `ipaddress`) under MASKED + mask-secrets, then `Masker.mask_text` (sharpit widening: `Bearer <jwt>`, `token=...` inside text); null under `METADATA_ONLY` | |
| `events[].data[].truncated` | value > 256 chars → first 256 + `"..."` | |
| `events[].traceId` | the sharpit request id (no trace id exists here; `nullable.json` records the golden's null) | |
| `events[].requestId` | `REQUEST.get().id` when the event was recorded (null outside a request) | |
| `page` | `engine/paging.py::paged` (offset<0→0, limit null → all, else 1..1000) | |
