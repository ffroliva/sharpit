# T-unbounded-read findings

Implementer: codex gpt-6-luna

## Red tests

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| F2: a Python-side slice over 52 materialized Team rows must report page size 5 | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_f2_report_names_materialized_rows_and_page_size` | `2e373d7bcf262633b98a961e76d942d0b4796dd2` | `AssertionError: F2 spike did not report an unbounded read` | Fixed in `4681c8b14826d1eebd9c02018fd92cb20f355393` |
| No `sharpit.install(app)` must produce the documented limitation without a finding | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_without_install_reports_limitation_and_does_not_fire` | `c0a4c86a054f1ab0cc88f216eb628803a8c96af6` | `AssertionError: assert any(...)` (the limitation was absent from report sources) | Fixed in `c10fa047e8a0c7e5c5db30b76cda5a8b0ad19b98` |

Both current reds were checked with `uv run python scripts/dev/red_check.py <node id>` at their recorded SHAs and replayed in detached worktrees with `PYTHONPATH=<red-tree>/src`. The no-install replay failed at `tests/pytest_plugin/test_plugin_unbounded_read.py:121` with an assertion in the test file. The F2 red was also replayed at `cb7fc450ec3429a27ef4a197bf57cf8864d3c022`; it is retained below as the superseded historical spike red.

## Review round 1 reds

| Finding | Test | Red SHA | Red assertion |
|---|---|---|---|
| Core-only SQLAlchemy host must not break `--sharpit` | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_core_only_sqlalchemy_host_does_not_break_sharpit` | `5d99628bdd768495d19c396ff6b2e22b53d5a112` | subprocess pytest exit code was 1 |
| Eager/lazy child rows must not inflate the parent page count | `tests/engine/test_sqla.py::test_relationship_rows_are_not_counted_as_parent_page_rows` | `5d99628bdd768495d19c396ff6b2e22b53d5a112` | initial assertion saw zero facts after the test detached listeners; this was not sufficient proof and is supplemented by the gate-level red below |
| Installed app request must suppress the missing-capture limitation | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_installed_app_request_suppresses_missing_capture_limitation` | `c8b26a66208ca486f01c5f7ad0f94ed198686689` | limitation was present after a captured request |
| Finding message includes first application location | `tests/engine/testsession/test_gates.py::test_unbounded_read_exact_threshold_boundary_flags` | `c8b26a66208ca486f01c5f7ad0f94ed198686689` | `app.py:12` absent from message |

All review red commits passed `red_check.py` for their listed tests and were replayed in detached worktrees with `PYTHONPATH=<red-tree>/src`; replays used `uv run --extra test` so SQLAlchemy and pytester dependencies were present. Review fixes landed in `65cc610`; the overhead-budget follow-up landed in `a2c9cc3`.

## Historical SHA

These tests cover behavior already present in the implementation. Each mutation temporarily broke the named guard in the listed source file at test commit `4541d8e463446148be920cecf831443e651a7e4e`; the test then failed at the shown assertion. Tests with parameters are recorded by their base id.

| Finding | Test | Historical SHA | Mutation proof / assertion message | Status |
|---|---|---|---|---|
| Superseded F2 spike red | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_spike_f2_unbounded_read_found` | `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` | Detached `red_check.py` replay: assertion that no `sharpit.unbounded-read` finding exists | Superseded by lint-clean F2 test at `2e373d7bcf262633b98a961e76d942d0b4796dd2` |
| Counts separate statements by QueryContext | `tests/engine/test_sqla.py::test_load_counts_are_per_statement` | `4541d8e463446148be920cecf831443e651a7e4e` | Mutate `query_id = id(context)` to one constant → `AssertionError: len(info.loads) == 2` (got 1) | Mutation-proven |
| Facts retain request identity | `tests/engine/test_sqla.py::test_load_counts_are_scoped_to_request` | `4541d8e463446148be920cecf831443e651a7e4e` | Remove request id from fact key → `AssertionError: len(rows) == 2` (got 1) | Mutation-proven |
| Counts keep mapper entities separate | `tests/engine/test_sqla.py::test_multiple_entities_count_separately` | `4541d8e463446148be920cecf831443e651a7e4e` | Replace mapper type name with a constant → expected `Team` and `Owner`, got `Entity` | Mutation-proven |
| Mapper recognizes SQL LIMIT/FETCH clauses | `tests/engine/test_sqla.py::test_select_with_limit_or_fetch_is_not_flagged` | `4541d8e463446148be920cecf831443e651a7e4e` | Ignore `_fetch_clause` → `AssertionError: all(fact.has_limit ...)` for `[fetch]` | Mutation-proven |
| Non-paged route never enters the rule | `tests/engine/test_sqla.py::test_non_paged_route_is_not_flagged` | `4541d8e463446148be920cecf831443e651a7e4e` | Treat `search` as a paging alias → `AssertionError: info.loads == {}` | Mutation-proven |
| No bound page size is never guessed | `tests/engine/test_sqla.py::test_paging_route_without_bound_page_size_does_not_guess` | `4541d8e463446148be920cecf831443e651a7e4e` | Remove the `page_size is None` guard → `AssertionError: info.loads == {}` | Mutation-proven |
| SQL literal values are masked and parameters dropped | `tests/engine/test_sqla.py::test_unbounded_read_fact_drops_sql_values` | `4541d8e463446148be920cecf831443e651a7e4e` | Store raw SQL → `AssertionError: "hunter2-secret" not in payload` | Mutation-proven |
| Mapper listener does not alter query results | `tests/engine/test_sqla.py::test_listener_does_not_change_query_results` | `4541d8e463446148be920cecf831443e651a7e4e` | Mutate loaded `target.id` → `AssertionError: [record.id ...] == [1, 2]` | Mutation-proven |
| Load listener attaches once and detaches | `tests/engine/test_sqla.py::test_mapper_load_listener_attaches_once_and_detaches` | `4541d8e463446148be920cecf831443e651a7e4e` | Remove `event.contains` guard → `AssertionError: loaded == 1` (got 2) | Mutation-proven |
| Identity-map hits are documented as undercounts | `tests/engine/test_sqla.py::test_identity_map_hits_are_not_counted` | `4541d8e463446148be920cecf831443e651a7e4e` | Increment each load count twice → `AssertionError: first_count == 2` (got 4) | Mutation-proven |
| Exact factor boundary is inclusive | `tests/engine/testsession/test_gates.py::test_unbounded_read_exact_threshold_boundary_flags` | `4541d8e463446148be920cecf831443e651a7e4e` | Change `<` to `<=` → `AssertionError: len(found) == 1` (got 0) | Mutation-proven |
| Gate excludes SQL LIMIT/FETCH facts | `tests/engine/testsession/test_gates.py::test_select_with_limit_or_fetch_is_not_flagged` | `4541d8e463446148be920cecf831443e651a7e4e` | Ignore `fact.has_limit` → `AssertionError: evaluate_test(...) == []` for base id (both parameter cases failed) | Mutation-proven |
| Marker relax suppresses only this rule | `tests/engine/testsession/test_gates.py::test_allow_unbounded_read_marker` | `4541d8e463446148be920cecf831443e651a7e4e` | Remove marker early return → `AssertionError: evaluate_test(...) == []` | Mutation-proven |
| Factor defaults to 2 and accepts an override | `tests/engine/testsession/test_gates.py::test_unbounded_read_factor_default_and_override` | `4541d8e463446148be920cecf831443e651a7e4e` | Ignore `budget_for` factor argument → `AssertionError: override.unbounded_read_factor == 3` | Mutation-proven |
| Facts and factor survive xdist JSON transport | `tests/engine/testsession/test_gates.py::test_unbounded_read_facts_and_budget_survive_json_round_trip` | `4541d8e463446148be920cecf831443e651a7e4e` | Rename the serialized fact key or force factor 2 → fact equality or factor assertion fails | Mutation-proven |
| Lookup query cannot add to a page statement count | `tests/engine/testsession/test_gates.py::test_lookup_query_does_not_add_to_count` | `4541d8e463446148be920cecf831443e651a7e4e` | Aggregate counts across facts → `AssertionError: len(found) == 1` (got 2) | Mutation-proven |
| Baseline marks an existing finding non-failing | `tests/engine/testsession/test_gates.py::test_unbounded_read_respects_report_only_and_baseline` | `4541d8e463446148be920cecf831443e651a7e4e` | Reverse baseline count comparison → `AssertionError: baseline_state == "existing"` (got `new`) | Mutation-proven |
| Bound `page_size` is accepted | `tests/fastapi/test_capture_paging.py::test_paging_context_uses_bound_page_size` | `4541d8e463446148be920cecf831443e651a7e4e` | Omit `page_size` from the accepted names → `AssertionError: result.page_size == 7` | Mutation-proven |
| Declared paging without a bound size does not guess | `tests/fastapi/test_capture_paging.py::test_paging_route_without_bound_page_size_does_not_guess` | `4541d8e463446148be920cecf831443e651a7e4e` | Stop recognizing declared `page` parameter → `AssertionError: result is not None` | Mutation-proven |
| Invalid, zero, duplicate and oversized values are conservative | `tests/fastapi/test_capture_paging.py::test_page_size_binding_validation_is_conservative` | `4541d8e463446148be920cecf831443e651a7e4e` | Accept zero (`>= 0`) → `AssertionError: result.page_size is None` (got 0) | Mutation-proven |
| Request context resets after an exception | `tests/fastapi/test_capture_paging.py::test_paging_context_reset_after_exception` | `4541d8e463446148be920cecf831443e651a7e4e` | Omit `REQUEST.reset(token)` → `AssertionError: observed == [None, None]` | Mutation-proven |
| Paging is derived after route matching | `tests/fastapi/test_capture_paging.py::test_paging_computed_lazily_after_route_match` | `4541d8e463446148be920cecf831443e651a7e4e` | Make `paging_of` always return `None` → `AssertionError: observed[1] is not None` | Mutation-proven |
| Report-only keeps the finding while test remains passed | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_unbounded_read_report_only_does_not_fail_test` | `4541d8e463446148be920cecf831443e651a7e4e` | Ignore report-only option → `AssertionError: result.ret == 0` (nested pytest failed on the gate) | Mutation-proven |
| Environment factor reaches the pytest gate | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_unbounded_read_factor_environment_override_reaches_gate` | `4541d8e463446148be920cecf831443e651a7e4e` | Hardcode factor 2 in session hook → `AssertionError: result.ret == 0` (nested gate flagged F2) | Mutation-proven |

### Historical SHA

These adapted pre-existing tests are not valid red claims at `59cf19c9927cfb9eb17917cfb004785ce8a1d115`: one fails on a stale internal-shape expectation and one raises `TypeError`. Both tests were mutation-proven at the lane head `5c514bfd19cb1738ebdf8303e54b1c8256a4b5d0`.

| Test | Historical SHA | Reason |
|---|---|---|
| `tests/engine/test_sqla.py::test_multiple_entities_count_separately` | `59cf19c9927cfb9eb17917cfb004785ce8a1d115` | Failed with unrelated key-set mismatch at red SHA (expected `{'Team', 'Owner'}`, got `{'rows'}`); mutation-proven at `5c514bfd19cb1738ebdf8303e54b1c8256a4b5d0`: replace `type(target).__name__` with constant `"Entity"` → `AssertionError: assert {'Entity'} == {'Owner', 'Team'}` |
| `tests/engine/test_sqla.py::test_identity_map_hits_are_not_counted` | `59cf19c9927cfb9eb17917cfb004785ce8a1d115` | Crashed with `TypeError` at red SHA (`list indices must be integers or slices, not str` while treating the load list as a dict); mutation-proven at `5c514bfd19cb1738ebdf8303e54b1c8256a4b5d0`: increment each load count by 2 → `AssertionError: assert 4 == 2` |
| `tests/engine/test_sqla.py::test_unbounded_read_facts_keep_request_identity_when_context_ids_are_reused_current` | `38660742f2143c0b0cae3a4f214bcec896917e7f` | mutation-proven at `38660742f2143c0b0cae3a4f214bcec896917e7f`: `src/sharpit/engine/sqla.py:290` remove `info.id` from `row_key` → `AssertionError: assert 1 == 2` |
| `tests/engine/test_sqla.py::test_load_compiles_and_masks_statement_once_current` | `38660742f2143c0b0cae3a4f214bcec896917e7f` | mutation-proven at `38660742f2143c0b0cae3a4f214bcec896917e7f`: `src/sharpit/engine/sqla.py:262` normalize the statement twice → `AssertionError: assert 2 == 1` |
| `tests/engine/test_sqla.py::test_relationship_loads_do_not_create_unbounded_findings_current` | `38660742f2143c0b0cae3a4f214bcec896917e7f` | mutation-proven at `38660742f2143c0b0cae3a4f214bcec896917e7f`: `src/sharpit/engine/sqla.py:240` make `_is_primary_mapper_load` always return `True` → `AssertionError: assert not True` |

## Mutation run notes

The mutation runs were temporary working-tree edits only; all guarded source lines were restored. Current historical tests pass at the lane head. The final targeted run was 106 passed (`C:\development\github\sharpit-wt\T-targeted-final.log`); the one full suite was 4,404 passed and 9 skipped (`C:\development\github\sharpit-wt\T-full-pytest.log`). Repo gates: Ruff and format passed; Pyright reported 0 errors, 0 warnings, 0 informations.
