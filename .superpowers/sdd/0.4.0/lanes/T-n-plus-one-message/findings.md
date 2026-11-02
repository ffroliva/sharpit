# T-n-plus-one-message findings

Implementer: codex-gpt-6

## Red tests

| Test | Red SHA | Assertion | Disposition |
|---|---|---|---|
| `tests/pytest_plugin/test_plugin_gates.py::test_spike_f5_message_names_relationship` | `d6edaec05a2bedf9014e170512f845089de4b2ba` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 79f4d866dfc1fe908d74f4d2aa49d14e6b9d8443 |
| `tests/pytest_plugin/test_plugin_gates.py::test_spike_f5_full_count_1018` | `f274907528094c3d8b3176ff814156a521cba6c9` | `AssertionError: assert 'Player.performances lazy-loaded 1018 times' in '1018 executions of one SELECT in the call phase'` | Fixed in d3741077769a1191b6df077808558e3c39ae8ef9 |
| `tests/pytest_plugin/test_plugin_gates.py::test_async_lazy_load_is_attributed` | `62c4c5f5ed202c23a278541419a00dc199b4cb3e` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 81f36ea4184587f1e4c86ddc26001a96228278a1 |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_names_lazy_relationship_and_loader` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 9e178696857743715ba737c31fe17e29db7cfea4 |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_suggests_joinedload_for_many_to_one` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | `AssertionError: assert 'Performance.player lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` | Fixed in 9e178696857743715ba737c31fe17e29db7cfea4 |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_message_includes_masked_statement_and_source` | `985ea7328033bf0a7d8ee0a08719e6ecd4d6b73d` | `AssertionError: assert 'masked statement: SELECT * FROM performances WHERE token = ?' in '6 executions of one SELECT in the call phase'` | Fixed in 9e178696857743715ba737c31fe17e29db7cfea4 |
| `tests/pytest_plugin/test_plugin_gates.py::test_eager_selectinload_batches_are_not_n_plus_one` | `e03d91e19b80d26a228dc0acb772c3008e76c1fa` | `AssertionError: assert not any(item['ruleId'] == 'sharpit.n-plus-one' for item in data['findings'])` | Fixed in d2bf3e3398dea0c7e760ca4e11befb860d2274a1 |
| `tests/engine/test_sqla.py::test_first_application_location_is_cached_per_relationship` | `e1fcc6840bd0ceb65e6490cabf7c904ac9aaaff2` | `AssertionError: expected one source stack walk for one relationship, got 20` | Fixed in 5c12d61a77609b671bced513590dcad497c0e27c |
| `tests/engine/test_sqla.py::test_relationship_facts_use_masked_statement_fingerprint` | `57a614127aca92789b3219bd846d03c1367b46ad` | `AssertionError: assert None == ('Payment.refunds', True)` | Fixed in 5c12d61a77609b671bced513590dcad497c0e27c |
| `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget` | `2d5ca9e8fe9913aa7df36f47eb58dbe19c2b4b30` | `AssertionError: SQLAlchemy lazy relationship hooks: overhead 47.497 µs/lazy load; budget 35.000 µs/lazy load` | Fixed in 5c12d61a77609b671bced513590dcad497c0e27c |
| `tests/engine/test_sqla.py::test_relationship_facts_tolerate_missing_call_phase` | `2ef99d77f94036c162e2256d032d7f8d37fae894` | `AssertionError: missing call phase must not raise KeyError` | Fixed in d2bf3e3398dea0c7e760ca4e11befb860d2274a1 |
| `tests/engine/test_sqla.py::test_session_capture_does_not_register_orm_execute_listener` | `5e9c9c65181486f7e1c40cfa4479b909713780f3` | `AssertionError: the SQLAlchemy bridge must not install an ORM execution hook` | Fixed in d2bf3e3398dea0c7e760ca4e11befb860d2274a1 |

## Historical Red Tests

| Test | Historical SHA | Assertion | Disposition |
|---|---|---|---|

## Superseded reds (coordinator, round 2)

| Test id | Historical SHA | Reason |
|---|---|---|
| `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_orm_hook_overhead_budget` | 78f1bfa29448ccb2feed65d50eac6a7fbb31c4f9 | removed: it timed the `sqla.do_orm_execute` hook that fix round 2 deleted; the budget is enforced by test_sqlalchemy_lazy_relationship_hook_overhead_budget (round 1) |
