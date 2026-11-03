# Lane B-security findings

Every red below was replayed at its red SHA in a detached worktree with `scripts/dev/red_check.py` (all
`RED (assertion under tests/)`); the assertion column is the first `E` line of that replay (`pytest --tb=line`).

## Reds

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/collectors/security/test_contract.py::test_report_golden_parity | 298faee2f89cd9f7097f1cfa10a1f65df7289998 | `AssertionError: security/captured.json parity: filterChains: missing from payload; filterChainsAnalyzed: missing from payload; scan.filterChainsAnalyzed: mis...` | Fixed in `b6c29d1` |
| tests/test_security_docs_table.py::test_docs_table_matches_registry | 298faee2f89cd9f7097f1cfa10a1f65df7289998 | `AssertionError: assert {'SEC-AUTH-00... 'HIGH'), ...} == {}` | Fixed in `b6c29d1` |
| tests/engine/collectors/security/test_rules_transport.py::test_session_cookie_without_https_only | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], []] == [['SessionMiddleware'], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_session_cookie_same_site_none | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], []] == [['SessionMiddleware'], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_session_secret_shorter_than_32_characters | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], []] == [['SessionMiddleware'], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_session_secret_message_has_no_secret | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `assert [] != []` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_cors_wildcard_without_credentials | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], [], []] == [['CORSMiddleware'], [], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_cors_wildcard_with_credentials | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], []] == [['CORSMiddleware'], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_cors_broad_origin_regex | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], []] == [['CORSMiddleware'], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_openid_connect_url_over_http | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], [], []] == [['OpenIdConn...Url'], [], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_oauth2_flow_url_over_http | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [] == ['OAuth2Autho...orizationUrl']` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_host_header_not_restricted | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], [], []] == [['ASGI middl...dleware'], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_transport.py::test_proxy_headers_trusted_from_any_host | a5d6f3be564349854c76a2ee663fffac96a4d3f9 | `AssertionError: assert [[], []] == [['ProxyHeade...dleware'], []]` | Fixed in `eb75c3f` |
| tests/engine/collectors/security/test_rules_auth.py::test_http_basic_without_https | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [[], []] == [['GET /items'], []]` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_password_form_login_without_https | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [[], []] == [['GET /items'], []]` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_unsecured_write_route_in_a_secured_app | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [] == ['POST /public']` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_scopes_floor_and_newest_classify_same | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [] == ['POST /public']` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_blanket_permit_all | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [[], []] == [['application'], []]` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_csrf_for_cookie_credentials | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [[], [], []] == [['POST /items'], [], []]` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_csrf_for_http_basic | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [[], []] == [['PUT /items'], []]` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_public_openapi_for_a_secured_api | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [[], [], []] == [['/openapi.json'], [], []]` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_optional_scheme_is_the_only_check | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [[], []] == [['GET /items'], []]` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_auth.py::test_route_mixes_authentication_schemes | c8e019a132ebe2372b59b9931c05add437b61694 | `AssertionError: assert [] == ['GET /mixed']` | Fixed in `e445775` |
| tests/engine/collectors/security/test_rules_config.py::test_debug_mode_returns_tracebacks | 96ebb759d0c83a6accff78ef43909c1727ae54b7 | `AssertionError: assert [[], []] == [['application'], []]` | Fixed in `e537f77` |
| tests/engine/collectors/security/test_rules_config.py::test_flags_missing_https_enforcement_in_production | 96ebb759d0c83a6accff78ef43909c1727ae54b7 | `AssertionError: assert [[], [], []] == [['ASGI middl...ack'], [], []]` | Fixed in `e537f77` |
| tests/engine/collectors/security/test_rules_config.py::test_forwarded_headers_do_not_prove_https_enforcement | 96ebb759d0c83a6accff78ef43909c1727ae54b7 | `AssertionError: assert [] == ['ASGI middleware stack']` | Fixed in `e537f77` |
| tests/engine/collectors/security/test_rules_config.py::test_framework_debug_logging_in_production | 96ebb759d0c83a6accff78ef43909c1727ae54b7 | `AssertionError: assert [[], []] == [['logger sql...uvicorn'], []]` | Fixed in `e537f77` |
| tests/engine/collectors/security/test_rules_config.py::test_literal_secret_default | 96ebb759d0c83a6accff78ef43909c1727ae54b7 | `AssertionError: assert [] == ['shop/settings.py:3']` | Fixed in `e537f77` |
| tests/engine/collectors/security/test_rules_config.py::test_literal_secret_default_message_has_no_value | 96ebb759d0c83a6accff78ef43909c1727ae54b7 | `assert [] != []` | Fixed in `e537f77` |
| tests/engine/collectors/security/test_rules_source.py::test_plaintext_password_context | fc4a915b9118090d02bc9cb355092844a51bdd77 | `AssertionError: assert [] == ['shop/hashing.py:3']` | Fixed in `442a29b` |
| tests/engine/collectors/security/test_rules_source.py::test_legacy_default_password_scheme | fc4a915b9118090d02bc9cb355092844a51bdd77 | `AssertionError: assert [] == ['shop/hashing.py:4']` | Fixed in `442a29b` |
| tests/engine/collectors/security/test_rules_source.py::test_bcrypt_work_factor_below_10 | fc4a915b9118090d02bc9cb355092844a51bdd77 | `AssertionError: assert [] == ['shop/hashin...hashing.py:7']` | Fixed in `442a29b` |
| tests/engine/collectors/security/test_rules_source.py::test_literal_secret_in_source | fc4a915b9118090d02bc9cb355092844a51bdd77 | `AssertionError: assert [] == ['shop/keys.p...op/keys.py:2']` | Fixed in `442a29b` |
| tests/engine/collectors/security/test_rules_source.py::test_literal_secret_in_source_message_has_no_value | fc4a915b9118090d02bc9cb355092844a51bdd77 | `assert [] != []` | Fixed in `442a29b` |
| tests/engine/collectors/security/test_scan.py::test_scan_disabled_when_the_app_is_not_fastapi | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `AssertionError: assert ('SCANNED', '', 0) == ('DISABLED', ... inspect.', 0)` | Fixed in `086a6e7` |
| tests/engine/collectors/security/test_scan.py::test_scan_message_counts_middleware_stacks | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `AssertionError: assert ('SCANNED', '') == ('SCANNED', '...eware stack.')` | Fixed in `086a6e7` |
| tests/engine/collectors/security/test_scan.py::test_scan_reports_violating_rules | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `AssertionError: assert [] == ['SEC-AUTHZ-0...SEC-FAPI-001']` | Fixed in `086a6e7` |
| tests/engine/collectors/security/test_scan.py::test_missing_inventory_makes_scan_partial | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `AssertionError: assert ('SCANNED', False) == ('PARTIAL', False)` | Fixed in `086a6e7` |
| tests/engine/collectors/security/test_scan.py::test_rule_errors_are_analysis_errors | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `AssertionError: assert [] == [('SEC-AUTH-0...02', 'ERROR')]` | Fixed in `086a6e7` |
| tests/engine/collectors/security/test_scan.py::test_unreadable_source_is_a_limitation | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `AssertionError: assert 0 == (27 - 5)` | Fixed in `086a6e7` |
| tests/engine/collectors/security/test_scan.py::test_scan_uses_the_one_package_root_resolver | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `AssertionError: assert [] == [(<fastapi.ap...9D0>, 'shop')]` | Fixed in `086a6e7` |
| tests/engine/collectors/security/test_scan.py::test_view_reads_profiles_and_levels_without_creating_loggers | e030f19c212f9d811b396c22ac1cf42ccd042bf5 | `assert (False, False) == (True, False)` | Fixed in `086a6e7` |
| tests/fastapi/test_security_api.py::test_scan_through_the_route_finds_wildcard_credentials | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `assert 404 == 200` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_get_renders_the_last_scan | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `AssertionError: {"error":"Not Found"}` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_scan_reads_only_app_package | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `assert 404 == 200` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_read_only_blocks_scan | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `assert [404, 404, 404] == [403, 403, 200]` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_mcp_tools_list_has_only_get | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `AssertionError: assert [] == ['get_securit...e_violations']` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_mcp_report_and_violations | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `AssertionError: {"error":"Not Found"}` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_cli_scan_tool | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `assert 404 == 200` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_trap_route_untouched_by_every_introspecting_surface | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `AssertionError: assert '/sharpit/api/security' in ['/sharpit', '/sharpit/', '/sharpit/assets/app.js', '/sharpit/api/panels', '/sharpit/api/overview', '/sharp...` | Fixed in `1e058a8` |
| tests/masking/test_b_security_masking.py::test_violation_never_contains_literal_secret | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `AssertionError: {"error":"Not Found"}` | Fixed in `1e058a8` |
| tests/safety/test_b_security_safety.py::test_security_get_no_side_effects | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | `AssertionError: {"error":"Not Found"}` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_get_after_scan_opens_no_source_file | a7924adf5c500cbd9db2ea8acd4f4210fce570c4 | `AssertionError: {"error":"Not Found"}` | Fixed in `1e058a8` |
| tests/fastapi/test_security_api.py::test_violations_page_counts_the_rule_after_scan | a7924adf5c500cbd9db2ea8acd4f4210fce570c4 | `AssertionError: {"error":"Not Found"}` | Fixed in `1e058a8` |

## UI reds

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| ui/tests/component/security.test.ts::before the first scan: "Not scanned yet" and nothing is scanned on open | 5c5236e65f71357864f28ddf71dc69e3de5a3200 | `AssertionError: expected 'securityThis panel's view is not bui…' to contain 'Not scanned yet'` | Fixed in `2f13fd1` |
| ui/tests/component/security.test.ts::Scan posts security/scan and shows the finding and the stacks scanned | 5c5236e65f71357864f28ddf71dc69e3de5a3200 | `AssertionError: expected 'securityThis panel's view is not bui…' to contain 'Not scanned yet'` | Fixed in `2f13fd1` |
| ui/tests/component/security.test.ts::View violations reads the paged endpoint with the scan id | 5c5236e65f71357864f28ddf71dc69e3de5a3200 | `AssertionError: expected 'securityThis panel's view is not bui…' to contain 'SEC-CORS-002'` | Fixed in `2f13fd1` |
| ui/tests/component/security.test.ts::dismiss goes through dismissed-rules and the reloaded report hides the finding | 5c5236e65f71357864f28ddf71dc69e3de5a3200 | `AssertionError: expected 'securityThis panel's view is not bui…' to contain 'SEC-CORS-002'` | Fixed in `2f13fd1` |
| ui/tests/component/security.test.ts::read-only: Scan disabled with the reason | 5c5236e65f71357864f28ddf71dc69e3de5a3200 | `AssertionError: expected 'securityThis panel's view is not bui…' to contain 'SEC-CORS-002'` | Fixed in `2f13fd1` |
| ui/tests/component/security.test.ts::shows the error state | 5c5236e65f71357864f28ddf71dc69e3de5a3200 | `AssertionError: the given combination of arguments (undefined and string) is invalid for this assertion` | Fixed in `2f13fd1` |

## Superseded reds and pins

| Test | Historical SHA | Why | Proof |
|---|---|---|---|
| tests/fastapi/test_security_api.py::test_violations_page_after_scan | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | read `total`, a key the page DTO does not have; renamed and superseded by `test_violations_page_counts_the_rule_after_scan` at `a7924ad` | red at a7924ad |
| tests/fastapi/test_security_api.py::test_get_after_scan_opens_no_source_file | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | also counted the dismissal store's own state file; body replaced at `a7924ad` (must-cover name kept), whose red is the one in the table above | red at a7924ad |
| tests/engine/collectors/security/test_contract.py::test_post_scan_golden_parity | 298faee2f89cd9f7097f1cfa10a1f65df7289998 | skips: post-scan golden absent (G0); the gate reports it `unverified` | - |
| tests/test_security_docs_table.py::test_every_bootui_rule_has_a_row | 298faee2f89cd9f7097f1cfa10a1f65df7289998 | pin (passed at red) | deleting the SEC-HEAD-010 row: `AssertionError: assert ['SEC-HEAD-010'] == []` |
| tests/test_security_docs_table.py::test_dropped_and_new_rows_say_why | 298faee2f89cd9f7097f1cfa10a1f65df7289998 | pin | emptying SEC-HEAD-010's reason: `AssertionError: assert ['SEC-HEAD-010'] == []` |
| tests/engine/collectors/security/test_rules_auth.py::test_wrapped_host_and_static_files_are_never_called_permit_all | c8e019a132ebe2372b59b9931c05add437b61694 | pin (the stub returned []) | dropping `unknown` from `_blanket_permit_all`: `assert [('applicatio... installed.')] == []` |
| tests/safety/test_b_security_safety.py::test_inactive_security_paths_404 | 0f50d8e776277c9b00eb11c0dfbf5bfb721e11d5 | pin (activation already 404s) | forcing `ActivationStatus(True, ...)` in activation.py: `assert [200, 400, 200, 200] == [404, 404, 404, 404]` |
| tests/fastapi/test_security_api.py::test_host_route_behind_hand_written_wrapper_is_classified | 56022e45d708cce8220ef45c4191583c3f50e090 | pin (R-fastapi-security council follow-up) | `_opaque_route` treating every mount as served: limitation missing, AssertionError |
| tests/fastapi/test_security_api.py::test_hand_written_wrapper_around_static_files_is_served_as_is | 56022e45d708cce8220ef45c4191583c3f50e090 | pin (follow-up) | `_opaque_route` never served: `assert 'SEC-AUTHZ-002' in ['SEC-FAPI-001']` |

## Rule removal

Each of the 27 rules has its own test in `test_rules_{auth,transport,config,source}.py`; every one of them is RED at
its red SHA, where the rule did not exist, which is the "remove it and a named test fails" proof.

## Observations (not defects of this lane)

| Observation | Status |
|---|---|
| `app_package="examples.fastapi_sqla"` scans the whole top-level `examples` package, so the live check reports `examples/fastapi_sample/app.py` literals: `appsource.resolve_package_root` returns the top-level package by design (F5a, must-not-touch) | for the coordinator |

## Fix round 1 (council-claude, council-gemini, review-gemini-r1)

Reds replayed at `f377fbe` (`red_check.py`: 10 RED, 2 pins); fix `7253641`.

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/collectors/security/test_fix_round1.py::test_mounted_sub_app_cors_with_credentials_is_flagged | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert [] == ['CORSMiddleware at /api']` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_mounted_sub_app_cors_message_names_the_mount | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `assert [] == ['CORSMiddlew...s reflected.']` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_mounted_trusted_host_allowing_any_host_is_flagged | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert [] == ['TrustedHost...ware at /api']` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_middleware_instance_wrapping_a_mount_is_a_limitation | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert 'CORSMiddleware options on the app mounted at /w were not read.' in ()` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_literal_secret_as_keyword_dict_value_default_or_field | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert [] == ['shop/wiring.../wiring.py:8']` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_literal_secret_shapes_message_has_no_value | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `assert [] != []` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_unsecured_write_with_an_ordinary_dependency_is_flagged | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert [] == ['POST /items']` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_cors_origins_as_set_or_frozenset_are_read | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert [[], []] == [['CORSMiddle...SMiddleware']]` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_short_session_secret_wrapped_in_secret_types_is_flagged | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert [[], []] == [['SessionMid...nMiddleware']]` | Fixed in `7253641` |
| tests/engine/collectors/security/test_fix_round1.py::test_bcrypt_zero_rounds_is_flagged | f377fbe9fe284fb4498f21b53a80d22131e656e7 | `AssertionError: assert [] == ['shop/hashin...hashing.py:2']` | Fixed in `7253641` |

| Test | Historical SHA | Why | Proof |
|---|---|---|---|
| tests/engine/collectors/security/test_fix_round1.py::test_mounted_trusted_host_does_not_cover_the_root_app | f377fbe9fe284fb4498f21b53a80d22131e656e7 | pin: guards the new mounted reads (a sub-app's TrustedHost must not satisfy the root) | `_host_header` back to `if not trusted:`: `assert [] == ['ASGI middleware stack']` |
| tests/engine/collectors/security/test_fix_round1.py::test_long_session_secret_wrapped_in_secret_types_is_not_flagged | f377fbe9fe284fb4498f21b53a80d22131e656e7 | pin: guards the Secret unwrap (a long wrapped key is fine) | `_secret_text` returning `""`: `assert [['SessionMid...nMiddleware']] == [[], []]` |

| Review item | Resolution |
|---|---|
| claude #1 mounted middleware | `FastApiIntrospector._mounted_middleware` reads each mounted Starlette app's `user_middleware` with the same readers (`MiddlewareFacts.mount`); a middleware instance wrapping a mount is a limitation; findings name the mount; `SEC-FAPI-001` absence counts only the root's TrustedHost |
| claude #2 literal shapes | `_named_values`: keyword arguments, string dict keys, parameter defaults, `Field(default=...)`/`Field(...)` |
| gemini Medium / claude #3 | `_unsecured_writes` no longer skips `unchecked_dependency`; docs row says an ordinary dependency does not count |
| claude #4 / gemini minor 3 | `_secret_text` unwraps Starlette `Secret` (`_value`) and pydantic `SecretStr` (`_secret_value`) from the instance dict, no `str()` |
| gemini minor 2 | `_strings` accepts exact `set`/`frozenset` |
| gemini minor 1 | `_first_int` keeps `0` |
