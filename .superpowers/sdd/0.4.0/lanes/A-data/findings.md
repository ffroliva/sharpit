# A-data findings (finding -> test -> red output)

| Finding | Test id | Red SHA | Red output | Status |
|---|---|---|---|---|
| collector lists mapped classes, degrades, never configures | tests/engine/test_data.py (13 reds, see handoff.md) | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 and others | fixed c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| detail lookup | tests/engine/test_data.py (6 reds, see handoff.md) | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None | fixed 482abf764a0d4029ece739ca71156c19eb77d255 |
| list route absent (404) | tests/fastapi/test_data_api.py::test_repositories_lists_the_models | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 | fixed c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| detail route absent | tests/fastapi/test_data_api.py::test_detail_by_name | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 | fixed c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| detail 404 body not empty | tests/fastapi/test_data_api.py::test_detail_404_empty_body | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert b'{"error":"Not Found"}' == b'' | fixed c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| GET must not configure mappers or run SQL | tests/fastapi/test_data_api.py::test_get_never_configures_mappers | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 | fixed c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| disabled panel answers 403 | tests/fastapi/test_data_api.py::test_panel_disabled_403 | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 403 | fixed c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| panel not listed | tests/fastapi/test_data_api.py::test_panel_listed_when_implemented | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert None is not None | fixed c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| MCP read tool missing | tests/fastapi/test_data_api.py::test_mcp_lists_read_tool_only | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 'get_data_repositories' in {...} | fixed c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| view is a placeholder (vitest, not pytest-replayable) | ui/tests/component/data.test.ts (4 tests) | 7b5a0270cfc49c9f58dc3bc39a44a59f15ce5b52 | AssertionError: expected placeholder text to contain 'Owner' | fixed ddfaffb204141385fe66f51f9ac33284e40d6e88 |

`test_repositories_golden_parity` skips until G0a's `data/repositories.captured.json` merges; it is not a named red.

## Fix round 1 (review.md, ponytail-review.md)

| Finding | Test id | Red SHA | Red output | Status |
|---|---|---|---|---|
| review fix | tests/engine/test_data.py::test_cross_registry_new_mapper_is_not_configured | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert ['_check_configure', ...] == [] | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_join_mapped_class_keeps_its_row | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 1 | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_failing_field_drops_only_that_field | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 1 | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_warnings_mask_exception_text | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 'hunter2secret' not in 'Skipping a mapper ...' | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_mapped_class_with_a_mappers_column_is_accepted | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 2 | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_registry_lookup_never_runs_class_descriptors | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert ['run', 'run', 'run'] == [] | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_lazy_is_a_strategy_name[None-noload] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'None' != 'noload' | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_lazy_is_a_strategy_name[True-select] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'True' != 'select' | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_lazy_is_a_strategy_name[False-joined] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'False' != 'joined' | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
| view keys, stale drawer, duplicates, warnings (vitest) | ui/tests/component/data.test.ts (4 new) | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | expected ... to include 'api/data/repositories/app.b.Owner' and others | fixed d97f0160000c90844caf1f2eec9032f502c9b2bd |
