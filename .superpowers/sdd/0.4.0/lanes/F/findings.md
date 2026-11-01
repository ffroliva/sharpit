# Lane F findings

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Route registration helper must preserve order | `tests/test_foundation_split_contracts.py::test_route_registration_preserves_order` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert app.routes == [first, second]` | Fixed in Task 1 split commit |
| Tool catalogue exposes the registered tool order | `tests/test_foundation_split_contracts.py::test_tool_catalogue_matches_registered_tools` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert [tool.name for tool in catalog] == [tool.name for tool in TOOLS]` | Fixed in Task 1 split commit |
| Session option seam delegates to the current resolver | `tests/test_foundation_split_contracts.py::test_plugin_session_options_match_resolver` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert actual == expected` | Fixed in Task 1 split commit |
| Capture setup contract belongs to `fastapi.install` | `tests/test_foundation_split_compat.py::test_capture_configuration_contract_is_owned_by_install_module` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert get_type_hints(_configure_capture)["return"] is CaptureWiring` | Fixed in pending Task 1 refactor commit |
| `tool_dispatch` can be imported independently | `tests/test_foundation_split_compat.py::test_tool_dispatch_import_is_cycle_free` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert result.returncode == 0, result.stderr` | Fixed in pending Task 1 refactor commit |
| Dispatch reads the monkeypatchable tools facade catalogue | `tests/engine/test_tools.py::test_call_tool_uses_facade_catalogue` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert result == {"facade": True}` | Fixed in pending Task 1 refactor commit |
| Dispatch reads the monkeypatchable tools facade gate | `tests/engine/test_tools.py::test_call_tool_uses_facade_tool_gate` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert calls == [expected.name]` | Fixed in pending Task 1 refactor commit |
| Advisor runner uses the monkeypatchable plugin loader | `tests/pytest_plugin/test_plugin_apps.py::test_plugin_loader_facade_remains_monkeypatchable` | `45797333bd99647623073cb8b7b0b6755bd6a3f7` | `assert state.sink.facts.advisor_runs[0].status != "UNKNOWN"` | Fixed in pending Task 1 refactor commit |
