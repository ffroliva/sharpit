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
