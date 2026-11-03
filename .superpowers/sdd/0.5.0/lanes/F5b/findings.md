# F5b findings

Implementer: Claude subagent (claude-opus-5-5)

## Red tests

`red_check.py` said RED (assertion under tests/) for every row before its `test:` commit.

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/engine/test_import_boundary.py::test_sqla_package_is_the_only_sqlalchemy_importer | cc008ea4c4b847e92f712a81a14c39829e712203 | `assert ['sharpit/engine/sqla.py'] == []` | Fixed in 8f80ad4bcc7bdb5837addaeb35f5d6fe7b3465d8 |
| tests/engine/test_import_boundary.py::test_planted_sqlalchemy_import_outside_package_fails | cc008ea4c4b847e92f712a81a14c39829e712203 | the violations also list `sharpit/engine/sqla/__init__.py` and `sharpit/engine/sqla/listeners.py` (key was the file `sqla.py`) | Fixed in 8f80ad4bcc7bdb5837addaeb35f5d6fe7b3465d8 |
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_read_only_wrapper_rejects_write | 9f7996026a5c1e4b96bbd2570b3cdd0ddc6eae36 | `assert 'attempt to write a readonly database' in 'The read-only transaction could not be established, so sharpit skipped this read'` | Fixed in bf5370a67b3c14b4fc4e67a102337a6bfcd9e394 |
| tests/engine/test_sqla_read_only_dialects.py::test_read_only_restores_session_state | 9f7996026a5c1e4b96bbd2570b3cdd0ddc6eae36 | `assert ReadOnlyUnavailable('The read-only transaction could not be established, ...') == 1` | Fixed in bf5370a67b3c14b4fc4e67a102337a6bfcd9e394 |
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_read_only_keeps_an_app_query_only_session | 9f7996026a5c1e4b96bbd2570b3cdd0ddc6eae36 | `assert ReadOnlyUnavailable(...) == 0` | Fixed in bf5370a67b3c14b4fc4e67a102337a6bfcd9e394 |
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_restore_failure_invalidates | 9f7996026a5c1e4b96bbd2570b3cdd0ddc6eae36 | `assert False is True` (`conn.invalidated`) | Fixed in bf5370a67b3c14b4fc4e67a102337a6bfcd9e394 |
| tests/engine/test_sqla_read_only_dialects.py::test_mysql_read_only_statement_order | 9e1285527ad09cf37e457019d68655b37f3fe29e | `assert [] == ['SELECT @@version', 'SELECT @@SESSION.autocommit', ...]` | Fixed in f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd |
| tests/engine/test_sqla_read_only_dialects.py::test_mysql_verification_failure_refuses | 9e1285527ad09cf37e457019d68655b37f3fe29e | `assert 'SET SESSION transaction_read_only = 1' in []` | Fixed in f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd |
| tests/engine/test_sqla_read_only_dialects.py::test_mysql_autocommit_refused | 9e1285527ad09cf37e457019d68655b37f3fe29e | `assert 'SELECT @@SESSION.autocommit' in []` | Fixed in f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd |
| tests/engine/test_sqla_read_only_dialects.py::test_mariadb_old_variable_name | 9e1285527ad09cf37e457019d68655b37f3fe29e | `assert 'SET SESSION tx_read_only = 1' in []` | Fixed in f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd |
| tests/engine/test_sqla_read_only_dialects.py::test_mariadb_11_1_uses_transaction_read_only | 9e1285527ad09cf37e457019d68655b37f3fe29e | `assert 'SET SESSION transaction_read_only = 1' in []` | Fixed in f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd |
| tests/engine/test_sqla_read_only_dialects.py::test_mysql_before_5_7_20_uses_tx_read_only | 9e1285527ad09cf37e457019d68655b37f3fe29e | `assert 'SET SESSION tx_read_only = 1' in []` | Fixed in f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd |
| tests/engine/test_sqla_read_only_dialects.py::test_mysql_restore_failure_invalidates | 9e1285527ad09cf37e457019d68655b37f3fe29e | `assert False is True` (`conn.invalidated`) | Fixed in f079a6fe3cc8c6e5ec79bb3513253e947e3e4dbd |

## Superseded reds

The first sqlite red's engine helper used `StaticPool` without `check_same_thread=False`, so once the code was in the
read failed in its worker thread (`sqlite3.ProgrammingError`), not on the behaviour. The red reason at d81eab2 was the
right one (`ReadOnlyUnavailable`), but the helper was fixed and the four tests re-redded at 9f79960 (implementation
held back, `red_check` RED), which is the Red SHA above.

| Test | Historical SHA | Why superseded |
|---|---|---|
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_read_only_wrapper_rejects_write | d81eab2c79024bc57f3d285ff06f1d6690d35d0a | helper `_sqlite_engine` fixed (worker thread) |
| tests/engine/test_sqla_read_only_dialects.py::test_read_only_restores_session_state | d81eab2c79024bc57f3d285ff06f1d6690d35d0a | same |
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_read_only_keeps_an_app_query_only_session | d81eab2c79024bc57f3d285ff06f1d6690d35d0a | same |
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_restore_failure_invalidates | d81eab2c79024bc57f3d285ff06f1d6690d35d0a | same (helper not used by it; recorded with its siblings) |

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/test_patch_targets.py::test_patch_targets_are_defined_where_called | cc008ea4c4b847e92f712a81a14c39829e712203 | M0: `capture/activity.py` binds `from sharpit.engine.sqla import unavailable_reason` and calls it bare | `assert problems == []`: "test_activity.py:40 patches sharpit.engine.sqla.unavailable_reason; activity.py:63 looks it up through sharpit.engine.capture.activity" |
| tests/engine/test_sqla_read_only_dialects.py::test_mysql_autocommit_execution_option_refused_before_any_statement | 9e1285527ad09cf37e457019d68655b37f3fe29e | M6: the execution-options `AUTOCOMMIT` check removed (`mutations-task3.log`) | `assert isinstance(result, sqla.ReadOnlyUnavailable)` |
| tests/engine/test_sqla_read_only_dialects.py::test_other_dialect_read_only_unavailable | 9e1285527ad09cf37e457019d68655b37f3fe29e | M7: every non-sqlite, non-postgresql dialect takes the MySQL branch | `assert conn.queries == []` |
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_read_back_not_on_refuses | 6a2d8cf7e7cd1e4dfa2d3fcaf9c05308d042554c | M8 (council F5b finding 1): the `PRAGMA query_only` read-back check deleted from `_sqlite_read_only` (`mutations-fix1.log`) | `assert isinstance(result, sqla.ReadOnlyUnavailable)` |
| tests/engine/test_sqla_read_only_dialects.py::test_sqlite_read_back_failure_refuses | 6a2d8cf7e7cd1e4dfa2d3fcaf9c05308d042554c | M8: same mutation (the read-back is never executed, so `fn` runs) | `assert isinstance(result, RuntimeError)` |

## pin: retargeted patches (Task 1 step 2; `mutations-task1.log`)

Each mutation puts one retargeted patch back on the package (`sqla`) at 8f80ad4.

| Patch | Mutation | What failed |
|---|---|---|
| pin: test_dispatch.py `_named` → `sqla.listeners` | back on `sqla` | patch-target test + `test_before_returns_early_without_targets_or_sink` (AttributeError: package has no `_named`) |
| pin: test_sqla.py `_relationship_path` → `sqla.orm` | back on `sqla` | patch-target test + `test_repeated_lazy_load_inspects_relationship_and_fingerprint_once` |
| pin: test_sqla.py `_masked_fingerprint` → `sqla.orm` | back on `sqla` | patch-target test + same test |
| pin: test_sqla.py `_first_application_location` (2) → `sqla.orm` | back on `sqla` | patch-target test + `test_listener_failure_does_not_change_query_result`, `test_first_application_location_is_cached_per_relationship` |
| pin: test_sqla.py `id` (2, `raising=False`) → `sqla.orm` | back on `sqla` | ONLY the patch-target test ("sharpit.engine.sqla never uses the builtin 'id'"): the two tests still pass with a patch that does nothing, which is the hole this check closes |
| pin: test_sqla_read_only.py `bounded` → `sqla.readonly` | back on `sqla` | patch-target test ("readonly.py:130 looks it up through sharpit.engine.sqla.readonly") + `test_default_path_unchanged` |
| pin: test_sqla_read_only.py `bounded_read_only` → `sqla.readonly` | back on `sqla` | patch-target test + `test_separate_wall_and_statement_timeouts` |

Patches left on the package, correct because the name is defined there and every caller looks it up through it:
`unavailable_reason`, `sqlalchemy_module` (defined in `sqla/__init__.py`; submodules call `_sqla.sqlalchemy_module()`)
and `add` (`listeners.add`, re-exported; its only caller, `fastapi/capture.py`, calls `sqla.add`).
