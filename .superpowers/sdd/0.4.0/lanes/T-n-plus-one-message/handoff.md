# T-n-plus-one-message handoff

Implementer: codex-gpt-6

## Status

Implementation complete; final four gates remain. Three tasks are committed as red/fix pairs. The coordinator can resume with the gates and branch review.

## Decisions

- Keep `sharpit.n-plus-one` identity based on the existing normalized statement fingerprint.
- Relationship facts are collected only while the pytest session listener is attached; test SQL remains the source of the N+1 count.
- Eager relationship loads tagged by `do_orm_execute` with no `lazy_loaded_from` are removed from N+1 statement counts after call phase collection. This keeps repeated `selectinload` IN batches out of the N+1 gate (U8).
- Reported SQL is the sink's normalized, masked statement. No parameter values are kept. The relationship identity remains supplemental to the stable statement fingerprint.

## Red evidence

| Test | Red SHA | Assertion |
|---|---|---|
| `tests/pytest_plugin/test_plugin_gates.py::test_spike_f5_message_names_relationship` | `d6edaec05a2bedf9014e170512f845089de4b2ba` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` |
| `tests/pytest_plugin/test_plugin_gates.py::test_async_lazy_load_is_attributed` | `62c4c5f5ed202c23a278541419a00dc199b4cb3e` | `AssertionError: assert 'Player.performances lazy-loaded 6 times' in '6 executions of one SELECT in the call phase'` |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_names_lazy_relationship_and_loader` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | relationship message absent |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_suggests_joinedload_for_many_to_one` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | many-to-one loader hint absent |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_message_includes_masked_statement_and_source` | `985ea7328033bf0a7d8ee0a08719e6ecd4d6b73d` | masked statement absent |
| `tests/pytest_plugin/test_plugin_gates.py::test_eager_selectinload_batches_are_not_n_plus_one` | `e03d91e19b80d26a228dc0acb772c3008e76c1fa` | repeated eager batches incorrectly failed as N+1 |
| `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_orm_hook_overhead_budget` | `78f1bfa29448ccb2feed65d50eac6a7fbb31c4f9` | zero-budget control failed with `AssertionError` |

## Commits

- Task 1 fix: `79f4d866dfc1fe908d74f4d2aa49d14e6b9d8443` (`feat: capture SQLAlchemy lazy relationship loads`).
- Task 2 fix: `9e178696857743715ba737c31fe17e29db7cfea4` (`fix: explain SQLAlchemy N+1 relationship loads`).
- Task 3 fix: `dc4f379c8279dbafb0e31a612d6f87245df0630d` (`test: pin SQLAlchemy ORM hook budget`).
- Async follow-up fix: `81f36ea4184587f1e4c86ddc26001a96228278a1` (`fix: attach ORM hooks for async lazy loads`).

## Last verification

- Focused tests after Tasks 1–2: `58 passed` (SQLAlchemy bridge, relationship gates, F5 message, eager selectinload batches).
- F6 budget: `1 passed`; workload `1,000 SELECTs × 5 paired rounds`, on/off via the production ORM callback. Most recent measured overhead `7.696 µs/statement`, noise `22.747 µs`, budget `35 µs`; the spread was noise-limited on this shared machine. The budget was confirmed to fail after a temporary 100 µs sleep was injected into the listener, then the injection was removed.
- Gates: final full-tree runs still pending.

## Fix SHAs per red

| Test | Fix SHA |
|---|---|
| `tests/pytest_plugin/test_plugin_gates.py::test_spike_f5_message_names_relationship` | `79f4d866dfc1fe908d74f4d2aa49d14e6b9d8443` |
| `tests/pytest_plugin/test_plugin_gates.py::test_async_lazy_load_is_attributed` | `81f36ea4184587f1e4c86ddc26001a96228278a1` |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_names_lazy_relationship_and_loader` | `9e178696857743715ba737c31fe17e29db7cfea4` |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_suggests_joinedload_for_many_to_one` | `9e178696857743715ba737c31fe17e29db7cfea4` |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_message_includes_masked_statement_and_source` | `9e178696857743715ba737c31fe17e29db7cfea4` |
| `tests/pytest_plugin/test_plugin_gates.py::test_eager_selectinload_batches_are_not_n_plus_one` | `9e178696857743715ba737c31fe17e29db7cfea4` |
| `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_orm_hook_overhead_budget` | `dc4f379c8279dbafb0e31a612d6f87245df0630d` |

## Needs from coordinator

- None currently.
