# A-data findings (finding -> test -> red output)

| Finding | Test id | Red SHA | Red output | Disposition |
|---|---|---|---|---|
| collector/detail red | tests/engine/test_data.py::test_lists_one_row_per_mapped_class | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_no_models_is_unavailable | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'pass models= to sharpit.install' | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_empty_registry | eb6497d0b447b21b64abf030c177773bb278ed41 | assert False is True | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_configured_mapper_lists_relationships | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_models_forms_dedupe | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 1 | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_a_registry_alone_is_accepted | eb6497d0b447b21b64abf030c177773bb278ed41 | assert [] == [<sqlalchemy.orm.decl_api.registry ...>] | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_only_strangers_is_unavailable | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'models= holds no declarative base or registry' | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_one_bad_mapper_drops_only_its_row | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 1 | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_sqlalchemy_absent | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'SQLAlchemy is not imported by this application' | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_sqlalchemy_older_than_two | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'SQLAlchemy 1.4.50 is imported, but sharpit needs 2.0 or later' | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| collector/detail red | tests/engine/test_data.py::test_detail_by_bean_name | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None | Fixed in 482abf764a0d4029ece739ca71156c19eb77d255 |
| collector/detail red | tests/engine/test_data.py::test_detail_by_fq_name | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None | Fixed in 482abf764a0d4029ece739ca71156c19eb77d255 |
| collector/detail red | tests/engine/test_data.py::test_detail_by_simple_name | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None | Fixed in 482abf764a0d4029ece739ca71156c19eb77d255 |
| collector/detail red | tests/engine/test_data.py::test_detail_unknown_is_none | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None | Fixed in 482abf764a0d4029ece739ca71156c19eb77d255 |
| collector/detail red | tests/engine/test_data.py::test_detail_simple_name_collision | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None | Fixed in 482abf764a0d4029ece739ca71156c19eb77d255 |
| list route absent (404) | tests/fastapi/test_data_api.py::test_repositories_lists_the_models | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 | Fixed in c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| disabled panel answers 403 | tests/fastapi/test_data_api.py::test_panel_disabled_403 | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 403 | Fixed in c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| MCP read tool missing | tests/fastapi/test_data_api.py::test_mcp_lists_read_tool_only | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 'get_data_repositories' in {...} | Fixed in c781bae0ee2cc0a38915e89e8a6d6b20273329ec |

`test_repositories_golden_parity` skips until G0a's `data/repositories.captured.json` merges; it is not a named red.

## Fix round 1 (review.md, ponytail-review.md)

| Finding | Test id | Red SHA | Red output | Disposition |
|---|---|---|---|---|
| review fix | tests/engine/test_data.py::test_cross_registry_new_mapper_is_not_configured | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert ['_check_configure', ...] == [] | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_join_mapped_class_keeps_its_row | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 1 | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_failing_field_drops_only_that_field | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 1 | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_warnings_mask_exception_text | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 'hunter2secret' not in 'Skipping a mapper ...' | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_mapped_class_with_a_mappers_column_is_accepted | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 2 | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_registry_lookup_never_runs_class_descriptors | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert ['run', 'run', 'run'] == [] | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_lazy_is_a_strategy_name[None-noload] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'None' != 'noload' | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_lazy_is_a_strategy_name[True-select] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'True' != 'select' | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
| review fix | tests/engine/test_data.py::test_lazy_is_a_strategy_name[False-joined] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'False' != 'joined' | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |

## Fix round 2

| Finding | Test id | Red SHA | Red output | Disposition |
|---|---|---|---|---|
| registry subclass bypassed the _new_mappers check | tests/engine/test_data.py::test_registry_subclass_new_mapper_is_not_configured | 3ee9fe924d371ac21a821cc6c7d1fd8ae3228d9d | assert ['_check_configure', '_configure_registries'] == [] | Fixed in 3464bbdeff142dacd9dc5df6fe3626c2fe9d3aae |

Minors: vitest mock now uses the real detail DTO shape (no relationships key); dead lazy alias and list-based walk simplified.

## Historical reds (test or fixture changed after the red commit)

| Finding | Test id | Historical SHA | Red output | Fixed in |
|---|---|---|---|---|
| superseded red | tests/engine/test_data.py::test_unconfigured_mapper_is_not_configured | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| superseded red | tests/engine/test_data.py::test_a_mapper_added_after_configure_is_not_configured | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 3 | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| superseded red | tests/engine/test_data.py::test_broken_registry_degrades | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 | Fixed in c092d59c41ec9086cecaffc65216d1d36d9ca6d9 |
| superseded red | tests/engine/test_data.py::test_detail_unconfigured_has_no_methods | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None | Fixed in 482abf764a0d4029ece739ca71156c19eb77d255 |
| superseded red | tests/fastapi/test_data_api.py::test_get_never_configures_mappers | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 | Fixed in c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| superseded red | tests/fastapi/test_data_api.py::test_panel_listed_when_implemented | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert None is not None | Fixed in c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| superseded red | tests/fastapi/test_data_api.py::test_detail_by_name | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 | Fixed in c781bae0ee2cc0a38915e89e8a6d6b20273329ec |
| superseded red | tests/fastapi/test_data_api.py::test_detail_404_empty_body | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert b'{"error":"Not Found"}' == b'' | Fixed in c781bae0ee2cc0a38915e89e8a6d6b20273329ec |

## UI reds (vitest)

| Finding | Test id | Red SHA | Red output | Disposition |
|---|---|---|---|---|
| view is a placeholder (vitest, not pytest-replayable) | ui/tests/component/data.test.ts (4 tests) | 7b5a0270cfc49c9f58dc3bc39a44a59f15ce5b52 | AssertionError: expected placeholder text to contain 'Owner' | Fixed in ddfaffb204141385fe66f51f9ac33284e40d6e88 |
| view keys, stale drawer, duplicates, warnings (vitest) | ui/tests/component/data.test.ts (4 new) | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | expected ... to include 'api/data/repositories/app.b.Owner' and others | Fixed in d97f0160000c90844caf1f2eec9032f502c9b2bd |
