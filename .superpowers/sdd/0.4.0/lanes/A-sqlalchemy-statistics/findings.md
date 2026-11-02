# Findings

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| SQL recorder keeps no lifetime totals | `tests/engine/capture/test_sqltrace_totals.py::test_totals_survive_eviction` | `eb914c9bc546babaa3df145c3f080ec9c5a195b3` | `assert -1 == 12` | Fixed in `1b1e47dd` |
| Statistics report missing | `tests/engine/test_sqlastats.py::test_counts_are_lifetime_n_plus_one_is_window` | `f42ebc4a453d13f0e3aa9c807ea802e831778850` | `assert -1 == 500` | Fixed in `3316b806` |
| Panel unimplemented (404) | `tests/fastapi/test_sqlalchemy_statistics_api.py::test_get_delegates` | `387bf66368802f6a4719d215ae7d60a217bff2c9` | `assert 404 == 200` | Fixed in `5bb3ae9d` |
