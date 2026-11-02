# T-unbounded-read findings

Implementer: codex gpt-6-luna

## Red tests

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| F2 fixture capture must be active so the Mapper load event receives request paging context | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_f2_report_names_materialized_rows_and_page_size` | `2e373d7bcf262633b98a961e76d942d0b4796dd2` | `AssertionError: F2 spike did not report an unbounded read` | Fixed in `4681c8b14826d1eebd9c02018fd92cb20f355393` |

## Historical SHA

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Spike F2: ORM materializes 52 Team rows for page size 5 but no unbounded-read finding is reported | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_spike_f2_unbounded_read_found` | `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` | `AssertionError: no sharpit.unbounded-read finding for 52 materialized Team rows and page size 5` | Superseded by lint-clean replacement test |

The replacement red was confirmed by `red_check.py` and replayed in a detached worktree at its recorded SHA with `PYTHONPATH=<red-tree>/src`; it failed at the finding assertion. The fix explicitly enables capture in the fixture app, allowing request context to reach the Mapper listener.
