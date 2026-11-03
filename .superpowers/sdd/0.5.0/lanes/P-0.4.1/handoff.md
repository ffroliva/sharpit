# P-0.4.1 handoff

Implementer: Claude subagent (claude-opus-5-5)

## Status

DONE_WITH_CONCERNS. Code head `7363e39785aea4c57523d53278f04420a4e413e1` on `lane/0.5.0-P-0.4.1` (from `base/0.4.1`
7b70ff4); the evidence commit follows it. Never pushed. Concern: one budget test failed under full-suite load (below).

## Tasks

| Task | Commit | What it proved |
|---|---|---|
| 1 pins U4, U5 | `0f7bcae85d6ed864e9ed0a26c4eaf4e72d08a6e3` (`test:`) | Bench twins in `tests/fixtures/apps/bench_twins/`. The clean twin (data-layer tests, `--sharpit` with no `--sharpit-app`) exits 0, rest-api `SKIPPED`, terminal line names `--sharpit-app`. The noisy twin prints only the advisor-notes count line by default and lists rules with `--sharpit-verbose`. All three pass on the base: pins, mutation-proven (M1-M3 in `findings.md`, `mutations-task1.log`). No G6 red, so `apps.py`/`options.py` untouched. |
| 2 U6 gap, red | `051e74170db36ac609f7bf2facba64b2380e0b38` (`test:`) | 4 reds (RED in red_check, replayed in a detached worktree at that SHA). Skeleton: `PhaseFacts.statement_sites` field only. |
| 2 U6 gap, fix | `7363e39785aea4c57523d53278f04420a4e413e1` (`feat:`) | `sqla.py` records `(application site, batched query)` per statement on its first repeat (lazy loads skipped: they keep the relationship message); `apply_relationship_facts` maps it to the masked group; `facts.py` serializes `statementSites`; `_n_plus_one_message` appends `first at <file:line>; batch into one query: select(Model).where(Model.attr.in_(ids)); masked statement: ...` (generic `WHERE ... IN (...)` hint without an ORM entity or a single equality). Fingerprint pin `test_n_plus_one_fingerprint_unchanged` mutation-proven (M4, M5). |

## Gates (at 7363e39)

- `ruff check` 0, `ruff format --check` 502 files formatted, `pyright` 0 errors
  (`0.5.0-integration/.superpowers/sdd/0.5.0/logs/P-0.4.1-static.log`).
- Full suite `-n 4`: 4455 passed, 9 skipped, 1 failed: `tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget`
  (71 µs vs 35 µs, noise 191 µs; the harness says "within the noise: suspect a busy machine"). Rerun in isolation
  3x: green each time (`logs/P-0.4.1-budget-rerun.log`). The lazy-load path gained only an `is None` check
  (lazy loads skip the new site record). Budget constant unchanged.
- Code-scan ratchet: N/A — no SONAR_TOKEN; coordinator runs it.

## Decisions

- Site recorded on the first repeat, not the first execution: keeps `test_first_application_location_is_cached_per_relationship`
  (one stack walk per relationship) green, and a statement that runs once never pays a stack walk. In a loop it is the same line.
- Per-test cap of 256 distinct statements (`MAX_STATEMENT_SITES`, shortcut comment in `sqla.py`).
- The U4 twin uses the bench's `test_crud.py` shape (app module never imported); an imported app is autodetected instead.

## Open items

- Coordinator: lowest-direct and no-SQLAlchemy runs; reviewer; the budget test on a quiet machine.
- Merge after F5-gate, into `release/0.5.0` before F5b (F5b splits `sqla.py`; `_record_statement_site`,
  `_batched_query` and `_statement_sites` move with the statement listener).
