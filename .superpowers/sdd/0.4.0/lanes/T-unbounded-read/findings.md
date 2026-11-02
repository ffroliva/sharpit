# T-unbounded-read findings

Implementer: codex gpt-6-luna

## Red tests

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| Spike F2: ORM materializes 52 Team rows for page size 5 but no unbounded-read finding is reported | `tests/pytest_plugin/test_plugin_unbounded_read.py::test_spike_f2_unbounded_read_found` | `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` | `AssertionError: no sharpit.unbounded-read finding for 52 materialized Team rows and page size 5` | Parked: the pytester spike still fails at the current head; direct ORM listener check records load facts, so request/plugin integration remains unresolved |

The red was confirmed by `red_check.py` and replayed in a detached worktree at the recorded SHA with `PYTHONPATH=<red-tree>/src`. The replay failed at the test assertion above; the nested app test itself passed.
