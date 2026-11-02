# T-n-plus-one-message handoff

Implementer: codex-gpt-6-luna (high)

## Status

DONE_WITH_CONCERNS. The three round-1 findings are fixed and committed. The coordinator can review and merge-gate
the lane. The final full suite completed with two overhead-budget failures; both overshoots were within the measured
noise. No functional tests failed.

## Decisions

- Keep `sharpit.n-plus-one` identity based on the existing masked statement fingerprint.
- The SQL sink's per-statement counts provide lazy relationship counts when facts are applied. Relationship metadata
  is stored once per masked fingerprint, avoiding a per-load counter lock.
- Cache statement masking and code-object application-frame classification. Store the first application location once
  per relationship and test.
- Eager relationship batches use the same masked fingerprint and are subtracted before lazy counts are derived.
- The new benchmark uses 1,000 actual lazy relationship loads, `attach_session()` and a TEST call tag; the previous
  `select(1)` budget test remains unchanged and is historical only.

## Round-1 review reds

| test id | red SHA | assertion message |
|---|---|---|
| `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget` | `2d5ca9e8fe9913aa7df36f47eb58dbe19c2b4b30` | `AssertionError: SQLAlchemy lazy relationship hooks: overhead 47.497 µs/lazy load; budget 35.000 µs/lazy load` |
| `tests/engine/test_sqla.py::test_first_application_location_is_cached_per_relationship` | `e1fcc6840bd0ceb65e6490cabf7c904ac9aaaff2` | `AssertionError: expected one source stack walk for one relationship, got 20` |
| `tests/engine/test_sqla.py::test_relationship_facts_use_masked_statement_fingerprint` | `57a614127aca92789b3219bd846d03c1367b46ad` | `AssertionError: assert None == ('Payment.refunds', True)` |

Fix commit for all three: `5c12d61a77609b671bced513590dcad497c0e27c` (`fix: reduce SQLAlchemy relationship hook overhead`).

## Earlier lane reds and fixes

| test id | red SHA | assertion message | fix SHA |
|---|---|---|---|
| `tests/pytest_plugin/test_plugin_gates.py::test_spike_f5_message_names_relationship` | `d6edaec05a2bedf9014e170512f845089de4b2ba` | relationship absent from N+1 message | `79f4d866dfc1fe908d74f4d2aa49d14e6b9d8443` |
| `tests/pytest_plugin/test_plugin_gates.py::test_spike_f5_full_count_1018` | `f274907528094c3d8b3176ff814156a521cba6c9` | expected relationship message with 1,018 loads | `d3741077769a1191b6df077808558e3c39ae8ef9` |
| `tests/pytest_plugin/test_plugin_gates.py::test_async_lazy_load_is_attributed` | `62c4c5f5ed202c23a278541419a00dc199b4cb3e` | async relationship absent from N+1 message | `81f36ea4184587f1e4c86ddc26001a96228278a1` |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_names_lazy_relationship_and_loader` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | relationship message absent | `9e178696857743715ba737c31fe17e29db7cfea4` |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_suggests_joinedload_for_many_to_one` | `618ff47af164e43c9b25ff8a9748d71c8970e01d` | many-to-one loader hint absent | `9e178696857743715ba737c31fe17e29db7cfea4` |
| `tests/engine/testsession/test_gates.py::test_n_plus_one_message_includes_masked_statement_and_source` | `985ea7328033bf0a7d8ee0a08719e6ecd4d6b73d` | masked statement absent | `9e178696857743715ba737c31fe17e29db7cfea4` |
| `tests/pytest_plugin/test_plugin_gates.py::test_eager_selectinload_batches_are_not_n_plus_one` | `e03d91e19b80d26a228dc0acb772c3008e76c1fa` | eager batches incorrectly failed as N+1 | `9e178696857743715ba737c31fe17e29db7cfea4` |

The previous budget red, `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_orm_hook_overhead_budget` at
`78f1bfa29448ccb2feed65d50eac6a7fbb31c4f9`, is historical and superseded: `select(1)` did not invoke the relationship
load path.

## Verification

- Lane tests: `90 passed, 11 warnings` (`test_sqla.py`, `testsession/test_gates.py`, `test_plugin_gates.py`).
- New paired workload, `scripts.dev.overhead_check ... --runs 10`: median overhead `18.961 µs/lazy load` against
  `35.000 µs`; 2/10 runs failed within noise; the script classified the set as flaky/noise-limited.
- Final full suite, `uv run pytest -q -n 4`: `4209 passed, 9 skipped, 2 failed` in `980.90s`. The new lazy-load
  budget failure was `98.738 µs` with `66.697 µs` noise against `35 µs`; SQL Trace was `67.590 µs` with `64.145 µs`
  noise against `50 µs`. Both overshoots were within noise. Full log:
  `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/T-n-plus-one-message-full-pytest-final.out`.
- `ruff check`: passed. `ruff format --check`: `469 files already formatted`. `pyright`: `0 errors, 0 warnings, 0 informations`.
- Repeated budget diagnostic log:
  `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/T-n-plus-one-message-overhead-check2.out`.
- No budget or ratchet was raised. No remaining implementation work; review and lane gate remain for the coordinator.

## Current commits

- Red: `e1fcc6840bd0ceb65e6490cabf7c904ac9aaaff2`
- Red: `57a614127aca92789b3219bd846d03c1367b46ad`
- Red: `2d5ca9e8fe9913aa7df36f47eb58dbe19c2b4b30`
- Fix: `5c12d61a77609b671bced513590dcad497c0e27c`
- Next: lane review and coordinator gate.
