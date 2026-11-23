# Plan: SQL listener per-statement cuts

## Predict

**Verdict: GO (8/10).** Five review lenses find no safety-model or contract change: the cuts remove repeated work while retaining dialect checks, frame classification, per-recorder masker configuration, journal reentrancy checks, and trace-provider semantics. The highest-risk area is the combined recorder cache and journal fast path; the exact-output tests and SQL masking corpus are mandatory byte-identity gates. No proposed cut is dropped.

- Architect (8/10): changes remain inside existing engine and SQLAlchemy gatekeeper modules; no dependency or boundary changes.
- Security (8/10): Cuts 4 and 5 touch the route by which masked SQL text is cached and stored. `test_a_repeated_statement_is_masked_once`, exact SQL journal dictionary/size tests, and masking corpus must remain byte-identical.
- Contract parity (8/10): no DTO or endpoint fields change; recorded event semantics are invariant.
- Host compatibility (8/10): connection, context, greenlet and OpenTelemetry fallbacks remain covered by targeted tests.
- Devil's advocate (8/10): all seven cuts target distinct measured costs; the combined prototype measured 28.79 to 21.82 µs. No simpler single cut addresses the fleet variance.

## TDD sequence

For each cut in S0 rank order: run its listed tests and the lane regression set; require green before editing; apply only the proposed change; rerun the identical tests without test edits; measure `uv run pytest -q -n 0 tests/fastapi/test_sql_trace_overhead.py`; record the median; run lint, format check and pyright before a separate conventional commit.

1. `perf: resolve SQL event dialect in one pass` — dialect consistency tests in `tests/engine/sqltext/test_resolver.py` and application family dialect tests.
2. `perf: skip internal frames in SQL call-site lookup` — five `call_site` tests in `tests/engine/capture/test_sqltrace.py`.
3. `perf: streamline SQL context routing` — registry, request-context and per-install journal routing tests.
4. `perf: cache recorder statement outputs together` — repeated statement masking, fingerprint, truncation, category, aggregate LRU and signal tests. **Stored SQL bytes must match**; run the SQL masking corpus and recorder masking regression.
5. `perf: fast-path flat journal offers` — reentrancy, low-size accounting and exact SQL journal dictionary/size tests. **Emitted SQL bytes must match**; run the SQL masking corpus and exact journal output tests.
6. `perf: reduce SQL listener bookkeeping` — connection-info fallback, routing, and call-site-off tests.
7. `perf: skip empty OpenTelemetry span lookup` — full `tests/engine/test_otel.py`, trace capture, SQL journal size, and capture wiring tests.

## Final verification

Run the required lane tests, masking corpus gates unchanged, `scripts/dev/profile_sql_listener.py` with its paired interleaved base comparison, and all `tests/fastapi -k overhead` tests with `-n 0`. Never change or raise a budget. Record local and end-to-end medians and any deviations.
