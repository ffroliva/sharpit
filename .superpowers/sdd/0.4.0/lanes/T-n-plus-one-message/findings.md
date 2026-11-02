# T-n-plus-one-message findings

Implementer: codex-gpt-6

## Red tests

| Test | Red SHA | Assertion | Disposition |
|---|---|---|---|
| `tests/pytest_plugin/test_plugin_gates.py::test_spike_f5_message_names_relationship` | `d6edaec05a2bedf9014e170512f845089de4b2ba` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 79f4d866dfc1fe908d74f4d2aa49d14e6b9d8443 |
| `tests/pytest_plugin/test_plugin_gates.py::test_async_lazy_load_is_attributed` | `62c4c5f5ed202c23a278541419a00dc199b4cb3e` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 81f36ea4184587f1e4c86ddc26001a96228278a1 |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_names_lazy_relationship_and_loader` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 9e178696857743715ba737c31fe17e29db7cfea4 |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_suggests_joinedload_for_many_to_one` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | `AssertionError: assert 'Performance.player lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 9e178696857743715ba737c31fe17e29db7cfea4 |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_message_includes_masked_statement_and_source` | `985ea7328033bf0a7d8ee0a08719e6ecd4d6b73d` | `AssertionError: assert 'masked statement: SELECT * FROM performances WHERE token = ?' in '6 executions of one SELECT in the call phase'` | Fixed in 9e178696857743715ba737c31fe17e29db7cfea4 |
| `tests/pytest_plugin/test_plugin_gates.py::test_eager_selectinload_batches_are_not_n_plus_one` | `e03d91e19b80d26a228dc0acb772c3008e76c1fa` | `AssertionError: assert not any(item['ruleId'] == 'sharpit.n-plus-one' for item in data['findings'])` | Fixed in 9e178696857743715ba737c31fe17e29db7cfea4 |
| `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_orm_hook_overhead_budget` | `78f1bfa29448ccb2feed65d50eac6a7fbb31c4f9` | `AssertionError: SQLAlchemy ORM hooks: overhead exceeded the zero-budget control` | Fixed in dc4f379c8279dbafb0e31a612d6f87245df0630d |
