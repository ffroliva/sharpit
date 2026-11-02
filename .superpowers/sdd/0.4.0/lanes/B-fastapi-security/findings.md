# Findings (lane gate input)

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| No rule classification | tests/engine/test_appsecurity.py::test_rule_classification_table | 369dc4bb06eec787738382ed5ba467fe5b824f41 | `assert ('unknown', False, [], False) == ('unsecured', ...)` | Fixed in `0d353cb` |
| Custom guard must not imply secured | tests/engine/test_appsecurity.py::test_custom_guard_is_not_secured | 95136a909eda60bc76c5ba01f280ca80c96f194c | `assert True is False` | Fixed in `ed98dca` |
| No chain DTO | tests/engine/test_appsecurity.py::test_single_chain_lists_middleware_outermost_first | 369dc4bb06eec787738382ed5ba467fe5b824f41 | `assert [] == [{'order': 0, ...}]` | Fixed in `0d353cb` |
| Mounted chains missing | tests/engine/test_appsecurity.py::test_two_mounted_apps_two_chains_in_order | 369dc4bb06eec787738382ed5ba467fe5b824f41 | `assert [] == [(0, 'any request', []), ...]` | Fixed in `0d353cb` |
| Auth types missing | tests/engine/test_appsecurity.py::test_auth_provider_types_listed | 369dc4bb06eec787738382ed5ba467fe5b824f41 | `assert None == {'authenticationProviderTypes': [...]}` | Fixed in `0d353cb` |
| Present app reported absent | tests/engine/test_appsecurity.py::test_no_auth_providers_empty_lists | 369dc4bb06eec787738382ed5ba467fe5b824f41 | `assert False is True` | Fixed in `0d353cb` |
| auth null on a present app | tests/engine/test_appsecurity.py::test_configured_username_is_null | 369dc4bb06eec787738382ed5ba467fe5b824f41 | `assert None is not None` | Fixed in `0d353cb` |
| No endpoint rows | tests/engine/test_appsecurity.py::test_endpoints_sorted_by_pattern_then_method | 369dc4bb06eec787738382ed5ba467fe5b824f41 | `assert [] == [('/a', 'GET', 'authenticated', False), ...]` | Fixed in `0d353cb` |
| Nothing read from the app | tests/fastapi/test_introspector_security.py::test_get_never_calls_dependencies | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == [('/items', ('GET',), ((...TrapScheme, True, ()),))]` | Fixed in `3859499` |
| Nested scheme not found | tests/fastapi/test_introspector_security.py::test_scheme_found_in_nested_dependency | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == [('/me', ...), ('/open', ...)]` | Fixed in `3859499` |
| Scopes not read | tests/fastapi/test_introspector_security.py::test_security_scopes_read | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == [('/items/{item_id}', ('DELETE',), ...)]` | Fixed in `3859499` |
| Route-level guard not seen | tests/fastapi/test_introspector_security.py::test_route_level_dependency_without_scheme_is_unknown | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == [('/guarded', True), ('/plain', False)]` | Fixed in `3859499` |
| Middleware/backend not read | tests/fastapi/test_introspector_security.py::test_middleware_and_backend_types_read | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == [('starlette...AuthenticationMiddleware', ...)]` | Fixed in `3859499` |
| Sub-app chain missing | tests/fastapi/test_introspector_security.py::test_mounted_sub_app_middleware_is_its_own_chain | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == [(None, ()), ('/admin', ...)]` | Fixed in `3859499` |
| Host routes missing | tests/fastapi/test_introspector_security.py::test_sharpit_mount_hidden | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == ['/items']` | Fixed in `3859499` |
| No reason for a Starlette app | tests/fastapi/test_introspector_security.py::test_plain_starlette_app_not_present | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert () == ('FastAPI security dependencies are not available: ...',)` | Fixed in `3859499` |
| Drift not reported | tests/fastapi/test_introspector_security.py::test_internals_drift_degrades | 6ca004487dca812b8d927e0a09e047262e8bd5c0 | `assert [] == [('/items', True)]` | Fixed in `3859499` |
| Panel answers 404 | tests/fastapi/test_fastapi_security_api.py::test_report_golden_parity | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert 404 == 200` | Fixed in `0460657` |
| Panel answers 404 | tests/fastapi/test_fastapi_security_api.py::test_endpoints_golden_parity | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert 404 == 200` | Fixed in `0460657` |
| Panel answers 404 | tests/fastapi/test_fastapi_security_api.py::test_endpoints_rules | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert 404 == 200` | Fixed in `0460657` |
| No explain route | tests/fastapi/test_fastapi_security_api.py::test_explain_matches_route | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert 404 == 200` | Fixed in `0460657` |
| No explain route | tests/fastapi/test_fastapi_security_api.py::test_explain_defaults_to_get_root | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert 404 == 200` | Fixed in `0460657` |
| Explain lacks rule/roles/pattern | tests/fastapi/test_fastapi_security_api.py::test_explain_absent_is_unmatched | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `Right contains 3 more items: {'pattern': None, 'roles': [], 'rule': None}` | Fixed in `0460657` |
| Explain input not validated | tests/fastapi/test_fastapi_security_api.py::test_explain_input_edges | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert [404, 404, 404, 404, 404] == [400, 400, 200, 200, 200]` | Fixed in `0460657` |
| Middleware names absent | tests/fastapi/test_fastapi_security_api.py::test_middleware_values_never_exposed | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert '"SessionMiddleware"' in '{"error":"Not Found"}'` | Fixed in `0460657` |
| No MCP tool | tests/fastapi/test_fastapi_security_api.py::test_mcp_read_tool_only | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert [] == ['get_fastapi_security']` | Fixed in `0460657` |
| GETs unreachable | tests/safety/test_b_fastapi_security_safety.py::test_get_no_side_effects | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert [404, 404, 404] == [200, 200, 200]` | Fixed in `0460657` |
| Backend type absent | tests/masking/test_b_fastapi_security_masking.py::test_middleware_options_never_appear | 6060ab66d31eaaaa9b31e096844d1ce9c6df82cf | `assert '"test_b_fastapi_security_masking.JwtBackend"' in '{"error":"Not Found"}...'` | Fixed in `0460657` |

`tests/fastapi/test_fastapi_security_api.py::test_panel_disabled_403` passed at its first run (the guard denies a disabled panel once the flag is true): a regression pin, not a red.

## Historical SHA

| Superseded test | Red SHA | Reason and replacement |
|---|---|---|
| tests/engine/test_appsecurity.py::test_route_level_unknown_dependency_is_custom | 369dc4bb06eec787738382ed5ba467fe5b824f41 | Review requires scheme-less custom guards to remain best effort and unsecured. Superseded by `test_custom_guard_is_not_secured` and `test_route_level_unknown_dependency_is_custom_but_unsecured`. |
| tests/fastapi/test_fastapi_security_api.py::test_custom_route_never_touched_by_any_get | 95136a909eda60bc76c5ba01f280ca80c96f194c | The committed POST line exceeded Ruff's limit. Superseded by the lint-clean identical-intent `test_custom_route_never_touched_by_any_get_lint_clean`; its assertion still checks all GET and MCP reads leave the trap untouched. |

## Review-driven expectation replacement

`tests/fastapi/test_introspector_routes.py::test_failing_include_router_expansion_yields_fallback_row` expected the old `effective_candidates()` method to be called and fail. Calling it can execute route or converter code. It is replaced by `test_lazy_include_router_expansion_never_calls_candidates`, which asserts no candidate method call and confirms `/v1/ping` remains discoverable.

## UI reds

| Test | Commit | Assertion message |
|---|---|---|
| `ui/tests/component/fastapiSecurity.test.ts::lists the middleware stack outermost first with its CORS tag` | eb03313d4ae417e13300e9165ca8495ec46cc091 | `expected 'FastAPI SecurityThis panel's view is…' to contain 'TrustedHostMiddleware'` |
| `ui/tests/component/fastapiSecurity.test.ts::filters the endpoint table by rule` | eb03313d4ae417e13300e9165ca8495ec46cc091 | `expected +0 to be 3` |
| `ui/tests/component/fastapiSecurity.test.ts::marks a best-effort endpoint` | eb03313d4ae417e13300e9165ca8495ec46cc091 | `expected +0 to be 3` |
| `ui/tests/component/fastapiSecurity.test.ts::the explain form sends method and path and shows the rule` | eb03313d4ae417e13300e9165ca8495ec46cc091 | `expected null not to be null` |
| `ui/tests/component/fastapiSecurity.test.ts::an app without FastAPI security shows the reason` | eb03313d4ae417e13300e9165ca8495ec46cc091 | `expected the placeholder text to contain the reason` |

## Fix round 1 dispositions

| Finding | Red SHA | Disposition |
|---|---|---|
| Custom route descriptors or candidate methods can execute user code | 95136a9 | Fixed in `ed98dca`; exact-type handling and static lazy-router expansion |
| Scheme-less dependencies must not prove secured | 95136a9 | Fixed in `ed98dca`; custom guards are unsecured and best effort |
| Mount capture and skipped unreadable route affect explain | 95136a9 | Fixed in `ed98dca`; explain respects captured Mount order and limitations |
| Every enclosing app and Mount middleware belongs to the chain | 95136a9 | Fixed in `ed98dca`; chains follow mount identity and nested middleware wrappers |
| Parameter-level scheme-less and nested optional auth are best effort | 95136a9 | Fixed in `ed98dca`; focused tests pass |
| UI keys unique and empty explain values use defaults | 95136a9 | Fixed in `4bf1302`; full UI suite passes |
| include_router limitation text | 95136a9 | Fixed in `ed98dca`; static expansion retains a visible fallback on drift |

Round 2 full-suite verification is recorded in `handoff.md`.
