# T-n-plus-one-message handoff

Implementer: codex-gpt-6-luna (high)

## Status

BLOCKED. Round-two CI defects and the low-version ORM execution regression are fixed in `d2bf3e3398dea0c7e760ca4e11befb860d2274a1`.
The coordinator cannot merge-gate this head: the full suite has one failure in the historical `test_sqlalchemy_orm_hook_overhead_budget`,
whose locked body references the removed `sqla.do_orm_execute` symbol. The new round-two red test asserts that symbol is absent;
the COMMON rule prohibits changing either red body. See the exact traceback in the full-suite log below.

## Decisions

- Keep `sharpit.n-plus-one` identity based on the existing masked statement fingerprint.
- The SQL sink's per-statement counts provide lazy relationship counts when facts are applied. Relationship metadata
  is stored once per masked fingerprint, avoiding a per-load counter lock.
- Cache statement masking and code-object application-frame classification. Store the first application location once
  per relationship and test.
- Eager relationship batches use the same masked fingerprint and are subtracted before lazy counts are derived.
- The new benchmark uses 1,000 actual lazy relationship loads, `attach_session()` and a TEST call tag; the previous
  `select(1)` budget test remains unchanged and is historical only.
- SQLAlchemy 2.0.38 raises `InvalidRequestError` for the `selectinload(...).execution_options(yield_per=100)` fixture when
  any `Session.do_orm_execute` listener is registered, including a no-op listener. The no-listener control succeeds.
  Relationship details now come from the engine execution context's `_sa_orm_load_options` and compiled `current_path`;
  the sharpit bridge no longer registers or mutates ORM execution options.
- The dead relationship-load counter path was removed; `apply_relationship_facts` now tolerates a missing call phase.

## Round-two red commits and unresolved gate

| test id | red SHA | assertion message | fix SHA |
|---|---|---|---|
| `tests/engine/test_sqla.py::test_relationship_facts_tolerate_missing_call_phase` | `2ef99d77f94036c162e2256d032d7f8d37fae894` | `AssertionError: missing call phase must not raise KeyError` | `d2bf3e3398dea0c7e760ca4e11befb860d2274a1` |
| `tests/engine/test_sqla.py::test_session_capture_does_not_register_orm_execute_listener` | `5e9c9c65181486f7e1c40cfa4479b909713780f3` | `AssertionError: the SQLAlchemy bridge must not install an ORM execution hook` | `d2bf3e3398dea0c7e760ca4e11befb860d2274a1` |

The old budget test's red SHA is `78f1bfa29448ccb2feed65d50eac6a7fbb31c4f9`; its locked body calls
`sqla.do_orm_execute`. Full pytest therefore fails with `AttributeError` after removing the ORM hook. The test and the
new no-hook red test have incompatible expectations about the same symbol. No red test body was edited.

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

- Functional lane tests after the refactor: `92 passed, 11 warnings` (`test_sqla.py`, `testsession/test_gates.py`, `test_plugin_gates.py`).
- No-SQLAlchemy reproduction: `27 passed, 5 deselected, 11 warnings`; direct invocation of the four requested tests: `4 skipped`.
- Lowest-direct reproduction with SQLAlchemy 2.0.38: eager cases `2 passed, 30 deselected`; old `yield_per` case remains enabled and passes.
- `test_code_shape.py::test_complexity_only_goes_down`: `1 passed` after splitting the observer path; no baseline changed.
- New paired workload, `scripts.dev.overhead_check ... --runs 10`: median overhead `18.961 µs/lazy load` against
  `35.000 µs`; 2/10 runs failed within noise; the script classified the set as flaky/noise-limited.
- Final full suite, `uv run --no-sync pytest -q -n 4`: `4212 passed, 9 skipped, 1 failed` in `385.14s`. Failure:
  `test_sqlalchemy_orm_hook_overhead_budget` — `AttributeError` for removed `sqla.do_orm_execute`. The lazy relationship
  budget and SQL Trace budget passed in this run. Full log:
  `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/T-n-plus-one-message-full-final.log`.
- `ruff check`: passed. `ruff format --check`: `469 files already formatted`. `pyright`: `0 errors, 0 warnings, 0 informations`.
- Repeated budget diagnostic log:
  `C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/T-n-plus-one-message-overhead-check2.out`.
- No budget or ratchet was raised. Complexity ratchet passes; no baseline changed. Coordinator ruling is required on the
  historical overhead test/body conflict before this lane can be merge-gated.

## Current commits

- Red: `e1fcc6840bd0ceb65e6490cabf7c904ac9aaaff2`
- Red: `57a614127aca92789b3219bd846d03c1367b46ad`
- Red: `2d5ca9e8fe9913aa7df36f47eb58dbe19c2b4b30`
- Fix: `5c12d61a77609b671bced513590dcad497c0e27c`
- Red: `2ef99d77f94036c162e2256d032d7f8d37fae894`
- Red: `5e9c9c65181486f7e1c40cfa4479b909713780f3`
- Fix: `d2bf3e3398dea0c7e760ca4e11befb860d2274a1`
- Next: coordinator resolves whether to supersede the historical budget test body; then rerun the full lane gate.
