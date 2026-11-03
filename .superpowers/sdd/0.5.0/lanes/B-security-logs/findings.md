# B-security-logs findings

Implementer: Claude subagent (claude-opus-5-5)

Every red below was checked with `scripts/dev/red_check.py` before its `test:` commit: all `RED (assertion under tests/)`.

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/capture/test_securitylogs.py::test_clamps_max_logs_into_safe_range | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | a zero maximum must clamp up to 1 | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_sorts_newest_first_summarizes_and_pages | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | events must be newest first, then paged | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_type_summaries_tie_sorted_by_type | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | type summaries tie-sorted by type | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_masks_sensitive_data_entries | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | the event must be reported | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_long_value_truncated | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | the event must be reported | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_full_exposure_shows_values | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | the event must be reported | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_filters_by_principal_type_and_after | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | exact trimmed filters, strictly after | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_carries_the_request_id_each_event_was_published_under | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | request ids newest first | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_passes_trace_id_through_to_the_dto | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | traceId is the request id | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_buffer_bounded_newest_kept | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | newest kept | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_metadata_only_hides_values_and_principal | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | the event must be reported | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_twenty_entries_then_overflow_row | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | the event must be reported | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_timestamp_is_iso_instant | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | millis print 3 digits | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_report_timestamp_is_iso_instant | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | report timestamps are ISO instants | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_parse_after_requires_an_offset | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | Z is UTC | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_unavailable_report_shape | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | unavailable report shape | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/engine/capture/test_securitylogs.py::test_add_signals_the_change_stream | d5506b8e052b6f19707cb15ec59bfca5b2c83018 | each event signals the update stream | Fixed in bb7c21ef2c4c83856d8581eee49ff80842865192 |
| tests/fastapi/test_security_logs_api.py::test_401_becomes_authentication_failure | 7796847fe91bd2477f12c027726e450f51ac23fb | a 401 is an authentication failure | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_403_becomes_authorization_failure | 7796847fe91bd2477f12c027726e450f51ac23fb | a 403 is an authorization failure | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_200_records_nothing | 7796847fe91bd2477f12c027726e450f51ac23fb | the panel's buffer exists | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_sharpit_403_not_recorded | 7796847fe91bd2477f12c027726e450f51ac23fb | the panel's buffer exists | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_record_goes_to_the_current_apps_context_only | 7796847fe91bd2477f12c027726e450f51ac23fb | app A recorded its event | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_record_outside_request_is_noop | 7796847fe91bd2477f12c027726e450f51ac23fb | the panel's buffer exists | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_record_bad_args_never_raises | 7796847fe91bd2477f12c027726e450f51ac23fb | three record_security_event warnings | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_event_in_request_carries_request_id | 7796847fe91bd2477f12c027726e450f51ac23fb | the event carries its request's id | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/engine/capture/test_securitylogs.py::test_principal_never_runs_user_properties | 7796847fe91bd2477f12c027726e450f51ac23fb | a property identity falls back to the type name | Fixed in 78c84589bd2cc6f10949360649449719865ce704 |
| tests/fastapi/test_security_logs_api.py::test_report_golden_parity | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | the panel serves its report | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_events_newest_first_bounded | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | the panel serves its report | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_filters | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | the panel serves its report | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_masks_and_metadata_only | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | the panel serves its report | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_unavailable_when_capture_missing | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | the panel serves its report | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_invalid_after_is_400 | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | 400 for a naive instant | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_security_event_values_masked_everywhere | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | the panel serves its report | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_stream_guarded | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | a local caller gets the stream | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/fastapi/test_security_logs_api.py::test_mcp_tools_list_has_only_get | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | one read tool | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/safety/test_b_security_logs_safety.py::test_security_logs_get_no_side_effects | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | the security-logs GET route serves the buffered report | Fixed in 191bbaad306ff671f833354689328e561f728b93 |
| tests/engine/capture/test_securitylogs.py::test_stored_event_strings_are_bounded | 37a005dcc939f2bd1ed3a7c4332c5507faa09191 | the stored principal is cut to 256 characters (council-claude medium: 1049 MiB in 500 events) | Fixed in 31e1500760ec4ab64ead0f4f49ba094befefe971 |
| tests/engine/capture/test_securitylogs.py::test_long_values_are_masked_before_they_are_cut | 37a005dcc939f2bd1ed3a7c4332c5507faa09191 | a token straddling the cut is masked, never stored half (the same fix must not leak) | Fixed in 31e1500760ec4ab64ead0f4f49ba094befefe971 |

## UI reds

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| ui/tests/component/SecurityLogs.test.ts > renders type summaries, the masked badge, and refetches on a stream update | b62dbdc66963208988d5a9741ef58f86060b131a | expected the placeholder text to contain 'BadCredentialsException' | Fixed in 1ef18735c5b1cd89a889fafe484026a284d430cb |
| ui/tests/component/SecurityLogs.test.ts > filters by a type summary | b62dbdc66963208988d5a9741ef58f86060b131a | expected the placeholder text to contain 'AUTHENTICATION_SUCCESS · 1' | Fixed in 1ef18735c5b1cd89a889fafe484026a284d430cb |
| ui/tests/component/SecurityLogs.test.ts > shows the unavailable reason | b62dbdc66963208988d5a9741ef58f86060b131a | expected the placeholder text to contain 'Request capture is unavailable' | Fixed in 1ef18735c5b1cd89a889fafe484026a284d430cb |

## Pins (pass at their commit; mutation-proven)

| Test | Historical SHA | Mutation (scratch worktree at 1ef1873, reverted) | Failure under the mutation |
|---|---|---|---|
| tests/fastapi/test_security_logs_api.py::test_hook_raising_is_swallowed | 7796847fe91bd2477f12c027726e450f51ac23fb | `try/except` around `wiring.on_security_event(scope, sent)` in `fastapi/capture.py` removed | `RuntimeError: secret-bearing message` escapes to the client |
| tests/fastapi/test_security_logs_api.py::test_record_when_inactive_is_noop | 7796847fe91bd2477f12c027726e450f51ac23fb | none: the global fail-closed activation (an inactive install never configures capture; also `tests/test_safety_matrix.py::test_inactive_is_404_everywhere`) | N/A |
| tests/fastapi/test_security_logs_api.py::test_panel_disabled_drops_events | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | `attach` drops the `ctx.settings.panels[PANEL].enabled` check | `AssertionError: a disabled panel keeps no buffer` |
| tests/safety/test_b_security_logs_safety.py::test_inactive_security_logs_paths_404 | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | none: the global fail-closed guard (`test_inactive_is_404_everywhere`) | N/A |
| tests/masking/test_b_security_logs_masking.py::test_security_event_data_masked_before_output | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | `_row` skips `masker.mask` (`shown, masked = value, False`) | `AssertionError: secret values must be masked before output` |
| tests/fastapi/test_security_logs_overhead.py::test_security_logs_hook_overhead_budget | b76a93228dd86ff55fd534d5eb693ffe8b1f70fc | `attach` returns `None` instead of the hook | `AssertionError: the on side measures the attached hook` |
| tests/fastapi/test_security_logs_overhead.py::test_200_request_runs_no_security_logs_code | ad1274dd85ec8b37ac258e7f37eb39d1b3f8ffd7 | the capture middleware's guard `sent in (401, 403)` → `sent is not None` (the hook runs on a 200) | `AssertionError: a 200 runs no security-logs code (only the capture middleware's status compare)` |

## New rules mutation-proven (scratch worktree at 1ef1873, reverted)

| Rule | Mutation | Failing test |
|---|---|---|
| contract normalised-key markers (`sessionid`, `remoteaddress`, `ipaddress`) | `if masks_keys and any(` → `if False and any(` | `test_masks_sensitive_data_entries`: `AssertionError: sessionId` |
| text scrub (`Bearer <jwt>` inside a value) | `masker.mask_text(...)` → `str(shown)` | `test_masks_sensitive_data_entries`: `a bearer token inside a value must be masked` |
| METADATA_ONLY hides the principal | principal always shown | `test_metadata_only_hides_values_and_principal`: `METADATA_ONLY hides the principal` |
| the current request's context only | `ctx = list(_contexts.values())[-1]` | `test_record_goes_to_the_current_apps_context_only`: `app A recorded its event` |
| principal via `inspect.getattr_static` | `getattr(user, "identity", None)` | `test_principal_never_runs_user_properties`: `RuntimeError: identity ran` |
| the 400 never echoes `after` | message carries the value | `test_invalid_after_is_400`: `the error never echoes the value` |
| hook failure swallowed | try/except removed | `test_hook_raising_is_swallowed` (above) |

A weaker first mutation, `ctx = next(iter(_contexts.values()))`, survived: with two fresh apps the first registered
is app A. The newest-registered mutation above is the one the test is meant to catch. The first text-scrub mutation
against the masking file also survived (its `note` value is already masked whole by `Masker.mask`); the engine test
above catches it.

## Overhead

Paired runs, each test alone on an idle machine (logs `0.5.0-integration/.superpowers/sdd/0.5.0/logs/B-ovh-*.jsonl`).

`tests/fastapi/test_capture_overhead.py` (budget 0.200 ms, unchanged), base `ae0c227` (scratch worktree) vs head:

| Run | Base overhead / noise (ms) | Base on-side min (ms) | Head overhead / noise (ms) | Head on-side min (ms) |
|---|---|---|---|---|
| 1 | 0.251 / 0.048 (OVER) | 0.366 | 0.149 / 0.060 | 0.280 |
| 2 | 0.163 / 0.048 | 0.255 | 0.064 / 0.076 | 0.171 |
| 3 | 0.194 / 0.010 | 0.271 | 0.156 / 0.037 | 0.260 |

The on side (every capture panel, now including security-logs) is no slower at head than at base: the lane adds no
per-request work on a 200 (the hook is behind F's existing `sent in (401, 403)` compare). Caveat: at head the off side
also carries the middleware, because `CAPTURE_PANELS` in that test lacks `security-logs` (handoff question 2), so the
head "overhead" column understates capture; compare the on-side minimums. Base run 1 went OVER on its own: the budget
is load-sensitive on this machine.

`tests/fastapi/test_security_logs_overhead.py` (new, `BUDGET_NS = 2_000`, both sides with the middleware, only the
panel differs), after 27ef24b (40 rounds × 250 requests), five runs: overhead +1.0, +8.9 (OVER, noise 21.2), +0.3,
-0.4, -3.3 µs on a ~155 µs request; noise 3.6–25 µs. Under the full suite: +33.7 µs, noise 88 µs (OVER). On a 200 both
sides execute identical code, so the true difference is zero; a 2 µs budget sits below this harness's resolution
(noise is 2–12x the budget). Not raised; flagged for the coordinator (handoff question 4).

### After the perf audit (coordinator Q4 ruling; `0.5.0-integration/.superpowers/sdd/0.5.0/lanes/B-security-logs/perf-audit.md`)

The budget test is a pin, not a recorded red, so it changed in place (ad1274d): `ROUNDS, REQUESTS = 1000, 10` (rounds
shorter than a load wave, PR #56), budget unchanged at 2 µs. New exact pin
`test_200_request_runs_no_security_logs_code`: `sys.setprofile` counts zero calls into `securitylogs.py` over a round
of 200 requests and sees `hook` on a round of 401s; mutation-proven above.

Five runs of the budget file alone at ad1274d (log `B-ovh-1000.jsonl`), overhead / noise in µs on a ~77 µs request:
+2.68 / 5.21 (OVER, within noise), +0.66 / 2.54, -0.91 / 3.18, +0.07 / 4.66, -0.75 / 8.59. The exact pin passed 5/5.
