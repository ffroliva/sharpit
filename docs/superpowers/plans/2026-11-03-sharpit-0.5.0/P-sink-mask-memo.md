# Lane P-sink-mask-memo: memoise masking of repeated SQL in the pytest sink (bench U7 follow-up)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `P-sink-mask-memo` (worktree `C:\development\github\sharpit-wt\0.5.0-P-sink-mask-memo`, branch `lane/0.5.0-P-sink-mask-memo`, from `release/0.5.0`) |
| **Goal** | Cut the `pytest --sharpit` per-statement overhead on repeat-heavy suites (~57% is re-masking the same normalized fingerprint on every execution) without ever returning an unmasked value. |
| **Source** | Spike `docs/superpowers/spikes/2026-11-04-pytest-plugin-overhead.md` (lane BENCH-0.4.0, Task 4): `sink.on_sql` 71% of the suite overhead, `sink._mask` -> `masking.mask_text` of the normalized fingerprint 57%; `orm._masked_fingerprint` already memoises the same operation (`lru_cache(1024)`). Added by the coordinator 2026-11-04. |
| **Worker** | Claude subagent; reviewer another family (agy Gemini) |
| **Council** | required (AGENTS.md safety model 3: a cache over masked data) |
| **Depends on** | BENCH-0.4.0 (the spike) |
| **May touch** | `src/sharpit/engine/testsession/sink.py`, `tests/engine/testsession/test_sink*.py`, `tests/engine/testsession/test_sink_overhead.py` (new budget module), the lane folder |
| **Must NOT touch** | `engine/masking.py` (the masker itself), `engine/sqla/`, existing budget constants; `tests/conftest.py` (the coordinator adds the new budget module to `TIMING_MODULES`) |

## Must-cover

`tests/engine/testsession/test_sink.py::test_masked_fingerprint_memo_never_returns_an_unmasked_value`,
`tests/engine/testsession/test_sink.py::test_masked_fingerprint_memo_keys_on_masker_settings`,
`tests/engine/testsession/test_sink_overhead.py::test_sink_on_sql_repeated_statement_overhead_budget`.

## Tasks

### Task 1: safety reds first
- [ ] `test_masked_fingerprint_memo_never_returns_an_unmasked_value`: a fingerprint holding a secret-shaped literal
      that survived normalisation is masked on the first and on every repeated call (red against a naive memo of the
      raw string, or a pin if the current code already masks every time: mutation-prove it).
- [ ] `test_masked_fingerprint_memo_keys_on_masker_settings`: the same fingerprint under two maskers with different
      settings (exposure / patterns) never shares a cached result.

### Task 2: the memo
- [ ] A bounded memo (raw fingerprint + masker identity/settings) -> masked text in the sink, the same bound as
      `orm._masked_fingerprint` (1024) or smaller; per sink, never module-global across sessions with different settings.

### Task 3: the budget
- [ ] `test_sink_on_sql_repeated_statement_overhead_budget` in a new module (the `tests/overhead.py` paired shape,
      many short rounds): the budget is set from the measured memo'd cost with headroom, red against the un-memo'd code
      (or recorded as a new budget with the measurement in findings.md). Ask the coordinator in handoff.md to add the
      module to `TIMING_MODULES`. Never raise an existing budget.
- [ ] Re-measure the spike's scratch suite (paired) and record the before/after wall time in findings.md.
