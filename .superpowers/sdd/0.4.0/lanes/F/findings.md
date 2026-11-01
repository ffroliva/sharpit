# Lane F findings

| Finding | Test | Red SHA | Assertion message |
|---|---|---|---|
| Route registration helper must preserve order | `test_route_registration_preserves_order` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert app.routes == [first, second]` |
| Tool catalogue exposes the registered tool order | `test_tool_catalogue_matches_registered_tools` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert [tool.name for tool in catalog] == [tool.name for tool in TOOLS]` |
| Session option seam delegates to the current resolver | `test_plugin_session_options_match_resolver` | `869db29d181a3ad98df7eb5ba6201b4cbc0e091f` | `assert actual == expected` |
