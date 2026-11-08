# Spike: `pytest --sharpit` suite-level overhead (bench U7)

Status: verdict only (lane BENCH-0.4.0, Task 4). No budget added or raised; no code changed.

## Question

The bench saw about 1.7x wall time on a query-heavy suite with `--sharpit`. Where does the time go per query
(listener, facts, report), and is there a concrete fix?

## Method (perf-audit protocol: paired, same box)

- Scratch suite outside the repo: SQLite in memory, SQLAlchemy 2.1.6, CPython 3.14, Windows 11. 150 tests, each 40
  `session.get` + one `selectinload` list (2 statements) + 40 filtered `select`: 82 statements per test, 12,300 in all.
  `pytest.mark.sharpit(allow_n_plus_one=True)` so every test passes on both sides.
- Off: `pytest test_heavy.py`. On: the same plus `--sharpit --sharpit-no-advisors --sharpit-allow-unknown
  --sharpit-report=report.json`. Six rounds alternating off/on, separate processes, minimum per side.
- Fixed cost: the same with one test, five rounds.
- Attribution: one `cProfile` run per side, sharpit functions ranked by cumulative time.

## Numbers

| Measurement | off | on | on - off |
|---|---|---|---|
| 150 tests, 12,300 statements (min of 6; spread off 0.92 s, on 2.09 s) | 4.03 s | 6.11 s | 2.08 s (1.52x) |
| 1 test (min of 5): import, plugin attach, report | 1.91 s | 2.19 s | 0.28 s |
| Per statement, (2.08 - 0.28) / 12,300 | | | ~146 µs |

Profiled (`cProfile` inflates every call; read the shares, not the absolute times), on-run sharpit cumulative time:

| Where | Calls | Cumulative | Share of the on - off profile delta (5.3 s) |
|---|---|---|---|
| `engine/testsession/sink.py:on_sql` (per statement) | 12,300 | 3.74 s | 71% |
| of which `sink._mask` -> `masking.mask_text` of the normalized fingerprint | 12,900 | 3.00 s | 57% |
| `masking._mask_token` / `is_secret_value` / `_has_vendor_token` | 127,535 / 114,932 | 2.47 / 1.78 / 0.99 s | (inside `_mask`) |
| `sqla/listeners.py:before_cursor_execute` | 12,300 | 0.44 s | 8% |
| `sink._phase_of` | 12,300 | 0.34 s | 6% |
| `sqla/orm.py:_record_relationship` | 12,300 | 0.29 s | 5% |
| `testsession/filters.py:filtered_rule` | 12,300 | 0.26 s | 5% |
| sharpit import (`sharpit.fastapi` adapter pulled in at plugin load) | 1 | 0.74 s | fixed |
| `report_io.write_report` (report, at session end) | 1 | 0.20 s | fixed |

## Verdict: a concrete fix, as its own follow-up lane (not this lane)

The listener and the facts are cheap; the per-statement cost is dominated by masking the same normalized fingerprint
again on every execution. `sink.on_sql` calls `self._mask(normalized.fingerprint)` (and `_mask(normalized.sql)` on a
group's first sight) with no memo, so a statement repeated 40 times per test is masked 40 times, token by token.
The ORM side already memoizes the same operation (`orm._masked_fingerprint`, `lru_cache(1024)`).

Follow-up lane `P-sink-mask-memo` (proposal):

1. A bounded memo raw-fingerprint -> masked key in the sink (the fingerprint is post-normalization: literals are
   already `?`), cleared at session end.
2. Red first: a per-statement budget test for `sink.on_sql` on repeated statements (paired, `tests/overhead.py`
   shape), set from the measurement; and a masking test proving the memo cannot return an unmasked value when the
   masker's settings differ (a new cache over masked data needs its own failing test first, perf-audit skill).
3. It touches masking-adjacent code that stores captured data: `/sharpit:predict` and `/sharpit:llm-council --tier
   high` before code (AGENTS.md safety model).
4. Expected effect, unmeasured: up to ~57% of the per-statement overhead on repeat-heavy suites.

The fixed 0.28 s (importing the FastAPI adapter at plugin load even with `--sharpit-no-advisors`) is a second,
smaller candidate for the same lane: measure a lazy import before changing anything.

## Not checked

Linux/the bench box (this is one Windows box), PostgreSQL drivers, xdist workers, suites with many distinct statements
(where a memo helps less), and the advisors path (`--sharpit-no-advisors` was on).
