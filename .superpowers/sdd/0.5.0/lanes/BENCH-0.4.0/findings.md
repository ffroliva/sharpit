# BENCH-0.4.0 findings

Implementer: Claude subagent (claude-opus-5-5)

## Red tests

| Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| tests/pytest_plugin/test_plugin_swallowed_bench.py::test_db_error_swallow_twin_fails_the_gate | 3b40c2043858440319c69b3c5bfd91e8d7b8d988 | `AssertionError: assert 'INFO' == 'HIGH'` (`found[0]["severity"]`) | Fixed in 5ea93745aae983c3381509c098685adbb8dc3b39 |
| tests/pytest_plugin/test_plugin_bench_pins.py::test_lazy_load_n_plus_one_names_the_first_app_frame | 04e1942595584a8e59a73510cc3c0074fe1a8c6d | `AssertionError: assert 'serialize_app.py:25' in 'Player.performances lazy-loaded 10 times; selectinload(Player.performances); first lazy load at unknown; ...'` | Fixed in 7c66d49c89c207d601e8ca2ea8894fa1806a4374 |

`red_check.py` said `RED (assertion under tests/)` for each before its `test:` commit. Neither red needed a skeleton:
the base code already returned the wrong value (INFO severity; `unknown` site).

## Pins (pass on the base; mutation-proven, never claimed as reds)

| Test | Historical SHA | Mutation | Assertion it then failed on |
|---|---|---|---|
| tests/pytest_plugin/test_plugin_bench_pins.py::test_selectinload_and_in_batch_never_count_as_n_plus_one | 614e7152670e496c799acc846d81cc5aed2012c4 | M1: `orm.apply_relationship_facts` drops the eager batches (`eager_batches = {}`), so selectinload's five `IN` batches count as repeats | `assert result.ret == 0` (ret was 1) |
| tests/pytest_plugin/test_plugin_bench_pins.py::test_selectinload_and_in_batch_never_count_as_n_plus_one | 614e7152670e496c799acc846d81cc5aed2012c4 | M2: `gates._n_plus_one_findings` threshold `count >= 1`, so the single explicit `IN` batch counts | `assert result.ret == 0` (ret was 1) |

## New rules, removed in a scratch copy

| Rule | Removed | Test that fails |
|---|---|---|
| `gates.DATABASE_ERRORS` gates a swallowed PEP 249 error | the base (parent of 5ea9374) is the rule removed | `test_db_error_swallow_twin_fails_the_gate` (`'INFO' == 'HIGH'`) |
| `orm._declared_outside` names the declaration when no app frame is on the stack | the base (parent of 7c66d49) is the rule removed | `test_lazy_load_n_plus_one_names_the_first_app_frame` (`first lazy load at unknown`) |

## Task 1 root cause (U1/U2, D13 at INFO)

Ran the D13 twin (`tests/fixtures/apps/bench_twins/counts_app.py`): the finding is produced, target `counts_app.py:13`,
type `OperationalError`, severity INFO. The cause is not a library log line (the brief's suspect; SQLAlchemy logs
nothing here and `test_library_warn_does_not_hide_app_swallow` already pins that rule): the 0.4.0 gate (spec 0.4.0 §5.5
F1, `gates.py` `_swallowed_findings`) fails the test only for programming-error types, and `OperationalError` is not
one. The fix adds the PEP 249 error class names (`OperationalError`, `ProgrammingError`, `IntegrityError`, ...) to the
gating set in `gates.py`; the fact's `programmingError` report field stays accurate (false). The recognised-sink rule
from T-swallowed-2 is untouched. This widens the 0.4.0 §5.5 F1 gating list: the coordinator should confirm it with the
owner (a suite with a broad handler swallowing a DB error now fails; `sharpit(allow_swallowed=True)` relaxes it).

## Task 2 root cause (U6, "first lazy load at unknown")

Probe on a D01-shaped FastAPI twin: the lazy loads run inside pydantic's serializer (`response_model`, from_attributes)
on TestClient's worker thread after the route returned, so no application frame is on the stack and the walk returns
None. When app code itself triggers the load through a helper (sync route calling a helper that reads the
collection), the base already names the helper line; that is D07's shape, which the bench scored 3/3. The fix keeps
the once-per-relationship walk and, only when it finds nothing, names the relationship's declaration line in the
mapped class (parsed once per class and key, lru-cached):
`first lazy load outside application code (Player.performances declared at .../serialize_app.py:25)`.

## Task 2 paired budget (lazy-relationship hook, `tests/engine/test_n_plus_one_overhead.py`, budget 35 µs unchanged)

Same box, alternating head (7c66d49) and base (834c83b sources of `orm.py`/`gates.py`), `SHARPIT_OVERHEAD_LOG`:

| Run | head overhead (noise) | base overhead (noise) |
|---|---|---|
| 1 | 14.6 µs (8.7) | 15.7 µs (4.0) |
| 2 | 13.4 µs (15.6) | 20.2 µs (37.6) |
| 3 | 14.0 µs (8.4) | 13.2 µs (19.3) |

All six `verdict: ok`. The budget's lazy loads come from the test body (an application frame), so the fallback never
runs there; the difference is inside the noise.

## Task 3 decision (U8)

A realistic batch (one selectinload over 2,500 parents = five identical `IN` batches, one explicit `IN`) is never
N+1 on the base: pin above. Observed and kept: the same `IN` statement executed >= 5 times in one test (chunked or
per-parent `IN`) is counted, because the normalizer collapses `IN (?, ?)` to `IN (?)` and an `IN` per parent is a real
N+1 that an exemption would hide. Not a red; noted for the coordinator.
