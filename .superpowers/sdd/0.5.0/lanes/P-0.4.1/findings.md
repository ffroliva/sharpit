# P-0.4.1 findings

Implementer: Claude subagent (claude-opus-5-5)

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/pytest_plugin/test_plugin_bench_pins.py::test_n_plus_one_without_relationship_names_location_and_fix | 051e74170db36ac609f7bf2facba64b2380e0b38 | `assert f"query_loop_app.py:{line}" in message`: the message was only `30 executions of one SELECT in the call phase` | Fixed in 7363e39785aea4c57523d53278f04420a4e413e1 |
| tests/pytest_plugin/test_plugin_bench_pins.py::test_n_plus_one_without_entity_names_location_and_generic_fix | 051e74170db36ac609f7bf2facba64b2380e0b38 | `assert f"query_loop_app.py:{line}" in message`: the message was only `30 executions of one SELECT in the call phase` | Fixed in 7363e39785aea4c57523d53278f04420a4e413e1 |
| tests/engine/testsession/test_gates.py::test_n_plus_one_message_names_first_site_and_batched_query | 051e74170db36ac609f7bf2facba64b2380e0b38 | `AssertionError: assert 'first at app/crud.py:27' in '30 executions of one SELECT in the call phase'` | Fixed in 7363e39785aea4c57523d53278f04420a4e413e1 |
| tests/engine/testsession/test_gates.py::test_statement_sites_survive_json_round_trip | 051e74170db36ac609f7bf2facba64b2380e0b38 | `AssertionError: assert {} == {'fp': ('app/crud.py:27', 'select(Performance).where(Performance.performance_id.in_(ids))')}` | Fixed in 7363e39785aea4c57523d53278f04420a4e413e1 |

`red_check.py` said RED for all four before the `test:` commit, and again on the replay in a detached worktree at
051e741 with `PYTHONPATH=<tree>/src`. The red skeleton is the `PhaseFacts.statement_sites` field (not serialized, not
filled, not read): every red fails on its own assertion.

## Pins (pass on the base; mutation-proven, never claimed as reds)

Mutations ran in a detached scratch worktree with `PYTHONPATH=<tree>/src`; outputs in `mutations-task1.log` and
`mutations-task2.log` in this folder.

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/pytest_plugin/test_plugin_bench_pins.py::test_bench_clean_app_without_sharpit_app_is_green | 0f7bcae85d6ed864e9ed0a26c4eaf4e72d08a6e3 | M1: `apps.no_app_run` always returns None (the 0.3.0 no-application unknown, U4/F3) | `assert result.ret == 0` (ret was 1) |
| tests/pytest_plugin/test_plugin_bench_pins.py::test_bench_advisor_notes_hidden_by_default | 0f7bcae85d6ed864e9ed0a26c4eaf4e72d08a6e3 | M2: `terminal._write_summary` shows every finding (`shown = data["findings"]`, U5/F4) | `assert "  RAPI-" not in stdout` |
| tests/pytest_plugin/test_plugin_bench_pins.py::test_bench_advisor_notes_with_verbose | 0f7bcae85d6ed864e9ed0a26c4eaf4e72d08a6e3 | M3: `options.resolve` never sets `verbose` from `--sharpit-verbose` | `assert all(f"  {rule}: " in stdout for rule in rules)` |
| tests/engine/testsession/test_gates.py::test_n_plus_one_fingerprint_unchanged | 7363e39785aea4c57523d53278f04420a4e413e1 | M4: `Finding.fingerprint` hashes the message instead of the identity; M5: the N+1 identity is the message | `assert sited.fingerprint == plain.fingerprint` (both) |

## Observations

- U4 twin: when a test imports the module that defines the app, autodetect picks it (`sharpit: using app ...
  (pass --sharpit-app to choose)`) and rest-api runs; exit is still 0. The twin reproduces the bench's `test_crud.py`
  shape (data layer only, `main.py` never imported), the case F3 reported, so rest-api is `SKIPPED` with the hint.
  No G6 red found: nothing in `apps.py`/`options.py` was touched.
- U6: the site is recorded on a statement's first repeat, not its first execution, so a statement that runs once
  never pays a stack walk (`tests/engine/test_sqla.py::test_first_application_location_is_cached_per_relationship`
  pins one walk per relationship and stayed green). In a loop the first repeat is the same line as the first run.
- Lazy loads keep the relationship message (the statement-site path skips them); `sharpit.n-plus-one` fingerprints
  and identities are unchanged.
