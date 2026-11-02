# Findings

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| SQL recorder keeps no lifetime totals | `tests/engine/capture/test_sqltrace_totals.py::test_totals_survive_eviction` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 12` | Fixed in `1b1e47dd` |
| Statistics report missing | `tests/engine/test_sqlastats.py::test_counts_are_lifetime_n_plus_one_is_window` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 == 500` | Fixed in `3316b806` |
| Panel unimplemented (404) | `tests/fastapi/test_sqlalchemy_statistics_api.py::test_get_delegates` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 404 == 200` | Fixed in `5bb3ae9d` |
| Review round (see handoff.md) | `tests/engine/capture/test_sqltrace_totals.py::test_max_sql_masks_a_double_quoted_secret_with_parameter_capture` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 'sk_live_4eC...arjtT1zdp7dc' not in 'select * fr...rjtT1zdp7dc"'` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/capture/test_sqltrace_totals.py::test_max_time_counts_selects_only` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 50 == 5` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/capture/test_sqltrace_totals.py::test_max_sql_is_a_select` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 'update t set a = ?' == 'select a from t where id = ?'` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/capture/test_sqltrace_totals.py::test_clear_resets_max_time` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 9 == 0` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/capture/test_sqltrace_totals.py::test_clear_resets_max_sql` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 'select ?' is None` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/capture/test_sqltrace_totals.py::test_max_after_clear_is_the_next_select` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 9 == 3` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/test_sqlastats.py::test_n_plus_one_carries_the_request_path` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert None == '/pets'` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/test_sqlastats.py::test_long_statements_with_varying_literals_are_one_shape` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 0 == 1` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/test_sqlastats.py::test_get_does_not_normalize` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert ['select * fr...owner_id = ?'] == []` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/test_sqlastats.py::test_route_lookup_does_not_scan_per_group` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert ['r1'] == []` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/test_sqlastats.py::test_unavailable_when_sql_trace_panel_disabled` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 'SQL tracing ...ENABLED=false' == 'Panel is dis...ENABLED=false'` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/test_sqlastats.py::test_paused_recording_is_a_warning` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert None == ['']` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/engine/test_sqlastats.py::test_null_reason_matches_nullable_json` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert {'SQLAlchemy ...tions panel)'} == {'SQLAlchemy ...y operations'}` | Fixed in `44e30a35` |
| Review round (see handoff.md) | `tests/fastapi/test_sqlalchemy_statistics_api.py::test_n_plus_one_link_finds_the_request_in_http_exchanges` | bf3c9a3e137fdcd3c8907f0a6ad4836407c8ff77 | `assert 0 >= 1` | Fixed in `44e30a35` |
