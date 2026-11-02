# Lane F findings

## Red table (gate format; full SHAs from `git rev-parse`)

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/test_foundation_split_compat.py::test_capture_configuration_contract_is_owned_by_install_module` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert get_type_hints(_configure_capture)["return"] is CaptureWiring` |
| `tests/test_foundation_split_compat.py::test_tool_dispatch_import_is_cycle_free` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert result.returncode == 0, result.stderr` |
| `tests/pytest_plugin/test_plugin_apps.py::test_plugin_loader_facade_remains_monkeypatchable` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert state.sink.facts.advisor_runs[0].status != "UNKNOWN"` |
| `tests/test_foundation_structure.py::test_install_facade_reexports_install_module_implementation` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert adapter.install is install_module.install` |
| `tests/test_foundation_structure.py::test_adapter_install_uses_route_builder_module` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert called == [True]` |
| `tests/test_foundation_structure.py::test_option_registration_is_owned_by_options_module` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert plugin.pytest_addoption is options.pytest_addoption` |
| `tests/test_foundation_structure.py::test_gate_hook_is_owned_by_session_module` | `dcd50c7ec8b3643461eab99b6852e8917d4c1ec9` | `assert plugin.pytest_runtest_makereport is session.pytest_runtest_makereport` |
| `tests/test_foundation_capture_setup.py::test_configure_capture_attaches_wiring` | `d0ea233ea90a7e2f5cd800a6df7582a6ae114d1e` | `assert isinstance(wiring, CaptureWiring)` |
| `tests/test_foundation_structure.py::test_install_uses_adapter_route_compatibility_target` | `3ff293b0f49a325e25d31e743febfe9cea3c91f2` | `assert calls == [True]` |
| `tests/test_foundation_structure.py::test_installed_routes_use_adapter_read_capped_compatibility_target` | `3ff293b0f49a325e25d31e743febfe9cea3c91f2` | `assert response.status_code == 413` |
| `tests/test_foundation_capture_setup.py::test_configure_capture_stores_wiring_on_context` | `82b9177fc659abc6691712d9e706b8186e34329c` | `assert ctx.capture.wiring is not None` |
| `tests/test_foundation_capture_setup.py::test_configure_capture_stores_returned_wiring` | `3075c9104fd1cc4939baefc2e7071e370fe6e635` | `assert ctx.capture.wiring is wiring` |
| `tests/test_foundation_structure.py::test_http_probe_route_name_is_preserved` | `46bebf286295760495f24117f44d95765c4b8b02` | `assert str(path) == "/sharpit/api/http-probe"` |
| `tests/engine/test_import_boundary.py::test_pytest_gatekeeper_allows_every_plugin_submodule` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert violations == ["sharpit/engine/rogue.py imports pytest: only ['sharpit/pytest_plugin'] may import pytest"]` |
| `tests/test_foundation_runtime_types.py::test_install_return_type_resolves_at_runtime` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert hints.get("return") is SharpitHandle` |
| `tests/test_foundation_runtime_types.py::test_tool_call_types_resolve_at_runtime` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert hints.get("call") is CallContext` |
| `tests/test_foundation_runtime_types.py::test_tool_gate_context_and_via_types_resolve_at_runtime` | `359fbe92310fb07b5fdb9553786086ca3303a7a3` | `assert hints.get("ctx") is SharpitContext` |
| `tests/engine/test_import_boundary.py::test_opentelemetry_stays_behind_engine_otel_gatekeeper` | `7df27495026acd28f9ba0e8e60e7028113b8cf70` | `assert violations == [...]` (`sharpit/engine/tools.py imports opentelemetry.trace`) |
| `tests/engine/advisors/test_registry.py::test_0_4_advisor_specs_are_registered_and_gated` | `acbccbbdea8ce6798151a1a61b534c6fdf1a9ffb` | `assert all(by_id[advisor_id].implemented is IMPLEMENTED[advisor_id] for advisor_id in advisor_ids)` |
| `tests/fastapi/test_unimplemented_panel_surface.py::test_panel_implemented_defaults_true` | `c11ed911b56c9460d64ad3253809cf729f6622b7` | `assert panel.implemented is True` |
| `tests/engine/test_panel04_registry.py::test_0_4_panels_are_registered_but_unimplemented` | `fbcd986f5ae7cdaf4b501afe1a5a9cd60cbbd700` | `assert set(panels) == PANEL_IDS` |
| `tests/test_golden.py::test_golden_id_mapping_covers_panel_ids` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert set(ids.values()) == {panel.id for panel in PANELS}` |
| `tests/test_golden.py::test_golden_loader_reads_nullable_reasons` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert no_reason is not None` |
| `tests/test_golden.py::test_provisional_fixture_is_not_counted_as_parity` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert [w.category for w in provisional] == [UnverifiedParityWarning]` |
| `tests/test_golden.py::test_golden_loader_rejects_missing_key_and_wrong_type` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert missing is not None` |
| `tests/test_golden.py::test_golden_loader_prefers_named_capture` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert named is not None` |
| `tests/test_golden.py::test_golden_loader_requires_a_fixture` | `746299ee10585f362092a91ca796c1b6e890a33f` | `assert absent is not None` |
| `tests/test_foundation_extension_slots.py::test_0_4_settings_defaults` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert {name: getattr(s, name, None) for name in SETTINGS_0_4} == SETTINGS_0_4` |
| `tests/test_foundation_extension_slots.py::test_0_4_settings_env_parsers` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(s, field, None) == expected` |
| `tests/test_foundation_extension_slots.py::test_models_hook_stores_models_without_side_effects` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert len(models) == 2` |
| `tests/test_foundation_extension_slots.py::test_models_hook_accepts_a_lone_declarative_base` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(handle.context, "models", None) == (Base,)` |
| `tests/test_foundation_extension_slots.py::test_dismissed_pairs_is_inert_empty_set` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert store.dismissed_pairs() == set()` |
| `tests/test_foundation_extension_slots.py::test_capture_slots_default_inert` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert getattr(state, "security_logs", "missing") is None` |
| `tests/test_foundation_extension_slots.py::test_security_event_hook_sees_request_id` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert seen == [("GET", "/s401", 401, True), ("GET", "/s403", 403, True)]` |
| `tests/test_foundation_extension_slots.py::test_uninstall_runs_teardowns_in_reverse_even_if_one_fails` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert ran == ["third", "second", "first"]` |
| `tests/test_foundation_extension_slots.py::test_connection_listener_slot_attaches_and_removes` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert calls == ["begin"]` |
| `tests/test_foundation_extension_slots.py::test_connection_listener_slot_rejects_unknown_event` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert message == "unknown connection event 'execute'"` |
| `tests/test_foundation_extension_slots.py::test_report_only_options_are_accepted_and_inert` | `55a6eac71ab4c4afde30eed6f70721aeb4614c1c` | `assert with_options.ret == plain.ret` (usage error 4 before the options exist) |
| `tests/test_example_app.py::test_sqla_sample_passes_its_models_to_install` | `99c1cf8fa8f28b67a2f806b554c314b88aa23315` | `assert app.state.sharpit.context.models == (Base,)` |
| `tests/test_example_app.py::test_sqla_sample_otel_provider_only_with_the_sdk` | `99c1cf8fa8f28b67a2f806b554c314b88aa23315` | `assert (provider is not None) == bool(has_sdk)` |
| `tests/pytest_plugin/test_plugin_gates.py::test_plugin_hook_raises_session_continues[terminal_summary-False-False]` | `ba095efd548889bea12df614b3e2935ddda3eff9` | `assert 'pass' == 'unknown'` |
| `tests/pytest_plugin/test_plugin_gates.py::test_plugin_hook_raises_session_continues[worker_advisors-True-True]` | `ba095efd548889bea12df614b3e2935ddda3eff9` | `assert 'pass' == 'unknown'` |
| `tests/test_foundation_review_fixes.py::test_models_hook_rejects_a_string` | `46ee2477daa57bc7c826c780074dcd7e1ffb09f3` | `assert message == f"models must be a model class or an iterable of models, not {type(models).__name__}"` |
| `tests/test_foundation_round2.py::test_panel_surface_follows_its_flag[flag-true-postgresql]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert (panel_id in listed) is implemented` |
| `tests/test_foundation_round2.py::test_panel_surface_follows_its_flag[flag-true-transactions]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert (panel_id in listed) is implemented` |
| `tests/test_foundation_round2.py::test_panel_settings_follow_the_flag[flag-true]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert error is None` |
| `tests/test_foundation_round2.py::test_panel_env_for_an_unimplemented_panel_is_ignored[flag-false]` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert warned is implemented` |
| `tests/test_foundation_round2.py::test_lane_attacher_survives_lifespan_restart` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert calls == [1, 1]` |
| `tests/test_foundation_round2.py::test_connection_listener_says_when_sqlalchemy_is_not_imported` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert sqla.add_connection_listener("begin", lambda *_: None) is None` |
| `tests/test_foundation_round2.py::test_lane_attacher_retries_after_a_late_sqlalchemy_import` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert calls == [1]` |
| `tests/test_foundation_round2.py::test_reserved_options_help_promises_no_behaviour` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert f"--sharpit-report-only {reserved}" in out` |
| `tests/test_foundation_round2.py::test_golden_loader_prefers_named_provisional_over_shared_capture` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert error is None` |
| `tests/test_foundation_round2.py::test_lane_tool_colliding_with_a_base_tool_is_refused` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `assert _merge_error((clash,), {}) == f"lane tool name(s) collide with existing tools: {clash.name}"` |

## Review round 1: finding → test → red SHA → fix

| Finding (review.md) | Test | Red SHA | Fix |
|---|---|---|---|
| 1 major: no `routes/sql_trace.py` / `tools04/sql_trace.py`, and discovery skipped `sql-trace` | `test_sql_trace_route_and_tool_modules_are_discovered` | `46ee2477daa57bc7c826c780074dcd7e1ffb09f3` | `4c3828b` |
| 2 minor: `install(models="Base")` stored characters | `test_models_hook_rejects_a_string` (str, bytes, mapping) | `46ee2477daa57bc7c826c780074dcd7e1ffb09f3` | `4c3828b` |
| 3 minor: unimplemented 0.4 ids accepted and listed as known panels | `test_unknown_panel_message_lists_only_implemented_panels` | `46ee2477daa57bc7c826c780074dcd7e1ffb09f3` | `4c3828b` |
| 4 minor: vacuous MCP/CLI disjointness | control `test_planted_tool_in_an_unimplemented_panel_stays_absent` | none (control) | `4c3828b` |
| 5 minor: report-only inertness unproven under `--sharpit` | control `test_report_only_options_leave_the_sharpit_report_unchanged` | none (control) | `4c3828b` |
| 6, 7 minor | open, see handoff "Open minors" | — | — |

## Not a red (no replayable red; kept out of the red table)

- `tests/engine/test_tools.py::test_call_tool_uses_facade_catalogue` (recorded at `45797333bd99647623073cb8b7b0b6755bd6a3f7`): at that SHA it fails with `RpcError`, not an `AssertionError`, so it is a characterisation test of the tools facade seam, not a red. It passes at head and stays as a characterisation test.
- `tests/test_safety_matrix.py::test_disabled_panel_denies_its_endpoints` (scoped in `337d690`): a test-scope correction, not a defect red. The 12 unimplemented 0.4 panels answer 404 by design and are covered by `test_unimplemented_panel_has_no_surface`. In `4c3828b`, three safety-matrix/capture inputs that disable "every panel" now pass only implemented ids, because an unimplemented id is now an unknown panel (review finding 3).
- `tests/fastapi/test_capture_hooks.py::test_unimplemented_security_logs_does_not_add_capture_middleware` and `::test_unimplemented_database_panels_do_not_enable_discovery`: Codex added `skipif` decorators after their red commit `acbccbb`, and the gate requires the red body unchanged. The change only skipped the tests once an owner flips a flag, so `55eac19` restores the red version byte-for-byte (`git checkout acbccbb -- tests/fastapi/test_capture_hooks.py`). An owner lane that flips `security-logs`/`transactions` or a database panel replaces the matching test with its own positive test.
- Review minors 4 and 5: controls that pass on arrival, so no red. `tests/test_foundation_review_fixes.py::test_planted_tool_in_an_unimplemented_panel_stays_absent` and `::test_report_only_options_leave_the_sharpit_report_unchanged` (`4c3828b`).


## Review round 2 (ponytail-review.md + coordinator): finding → test → red SHA → fix

| Finding | Test | Red SHA | Fix |
|---|---|---|---|
| 1 flag-flip-fragile tests | `test_panel_surface_follows_its_flag`, `test_panel_settings_follow_the_flag` (red); `test_panel_tools_follow_its_flag`, `test_capture_middleware_follows_the_panel_flag`, `test_engine_discovery_follows_the_panel_flag` (pass on arrival) | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305`: `Panel.implemented` and `AdvisorSpec.implemented` are properties reading `panels04.IMPLEMENTED` at call time |
| 2 one-shot teardowns / silent no-op listener | `test_lane_attacher_survives_lifespan_restart`, `test_lane_attacher_retries_after_a_late_sqlalchemy_import`, `test_connection_listener_says_when_sqlalchemy_is_not_imported` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305`: `CaptureState.attachers`, re-run at install/startup/first request; `add_connection_listener` returns `None` without SQLAlchemy |
| 3 inert options' help promised behaviour | `test_reserved_options_help_promises_no_behaviour` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305` |
| 4 golden order | `test_golden_loader_prefers_named_provisional_over_shared_capture` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305` |
| 5 lane tool collisions; reversed COMMANDS example | `test_lane_tool_colliding_with_a_base_tool_is_refused` (red); `test_sql_trace_modules_are_discovered` (replacement) | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305`: `tools.merge_lane_tools` raises at import |
| 6 half-applied `max_results` fallback | `tests/engine/test_tools.py::test_call_tool_uses_the_given_tool_gate` (replacement double; no behaviour red) | — | `4650305` |
| 7 env for an unimplemented id warned | `test_panel_env_for_an_unimplemented_panel_is_ignored` | `c2e385d740fb70e209d3fc89e0d2840163f45c30` | `4650305` |
| lean | deleted `engine/tool_registry.py`, `fastapi/route_registry.py`, `session.resolve_options`, their 3 tests; one `panel_is_implemented` (= `panels04.module_implemented`) | — | `4650305` |

## Superseded reds (test deleted; its row left the red table)

| Test | Red SHA (historical) | Why |
|---|---|---|
| test_foundation_split_contracts.py::test_route_registration_preserves_order | was 869db29 | deleted with `fastapi/route_registry.py` (lean: the wrapper only re-stated `app.routes.extend`) |
| test_foundation_split_contracts.py::test_tool_catalogue_matches_registered_tools | was 869db29 | deleted with `engine/tool_registry.py` (lean: `catalogue()` returned `tools.TOOLS`) |
| test_foundation_split_contracts.py::test_plugin_session_options_match_resolver | was 869db29 | deleted with the pure alias `session.resolve_options` (the plugin facade re-exports `options.resolve`) |
| engine/test_tools.py::test_call_tool_uses_facade_tool_gate | was 4579733 | replaced by `tests/engine/test_tools.py::test_call_tool_uses_the_given_tool_gate` (the double now has `max_results`, so production reads `gate.max_results` only) |
| fastapi/test_capture_hooks.py::test_unimplemented_security_logs_does_not_add_capture_middleware | was acbccbb | replaced by `tests/test_foundation_round2.py::test_capture_middleware_follows_the_panel_flag` (flag set both ways) |
| fastapi/test_capture_hooks.py::test_unimplemented_database_panels_do_not_enable_discovery | was acbccbb | replaced by `tests/test_foundation_round2.py::test_engine_discovery_follows_the_panel_flag` (flag set both ways) |
| fastapi/test_unimplemented_panel_surface.py::test_unimplemented_panel_has_no_surface | was c11ed91 | replaced by `tests/test_foundation_round2.py::test_panel_surface_follows_its_flag` and `::test_panel_tools_follow_its_flag` (the old body read today's flags and asserted a tautology) |
| test_foundation_review_fixes.py::test_sql_trace_route_and_tool_modules_are_discovered | was 46ee247 | replaced by `tests/test_foundation_round2.py::test_sql_trace_modules_are_discovered` (COMMANDS maps tool name -> CLI path, as `_BASE_COMMANDS`); route mounting is covered by `test_panel_surface_follows_its_flag`'s per-panel route loop |
| test_foundation_review_fixes.py::test_unknown_panel_message_lists_only_implemented_panels | was 46ee247 | replaced by `tests/test_foundation_round2.py::test_panel_settings_follow_the_flag` (flag set both ways, no hard-coded panel list) |

## UI reds (manual replay; not pytest node ids)

Replay: `git checkout <sha> -- ui && npm --prefix ui run test -- <file>` in a scratch copy, then restore.

| Vitest test | Red SHA | Observed red output |
|---|---|---|
| `ui/tests/unit/nav.test.ts::keeps every 0.4 panel unimplemented and out of navigation` | `c11ed911b56c9460d64ad3253809cf729f6622b7` | `expect(Object.values(PANEL_04_IMPLEMENTED)).toEqual(PANEL_04_IDS.map(() => false))` |
| `ui/tests/component/panels04.test.ts::renders the <id> placeholder with its panel title` | `f4b55d64cbb63494a7d35c59e96660c208a5244b` | `expect(h.target.textContent).toContain('<View> title')` (empty stub view) |
| `ui/tests/component/panels04.test.ts::routes every 0.4 placeholder in App.svelte only behind its implemented flag` | `f4b55d64cbb63494a7d35c59e96660c208a5244b` | `expect(app, view).toContain("import Data from './views/Data.svelte';")` |
