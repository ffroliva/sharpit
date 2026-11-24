# Scenario: SQL listener per-statement cuts

## Coverage map

The change is confined to SQLAlchemy listener, SQL capture, routing, journal, stream, and trace-ID hot paths. Masking is covered because recorder cache composition and journal admission can affect stored SQL text. Activation, request guards, endpoint contracts, network scans, and host introspection are unchanged and are skipped.

## Worst-case trace

Input: a repeated SQL statement containing an inline credential that has already been masked and normalized. The recorder computes its shape in `engine/capture/sqltrace.py`, stores shaped text in its per-recorder cache, emits a `SqlEvent` through `engine/sources/dispatch.py`, and offers a flat journal record through `engine/capture/journal.py`. Cuts 4 and 5 must retain the same masker, cache lifetime, SQL truncation, and event dictionary; any discrepancy is caught by `tests/engine/capture/test_sqltrace.py::test_a_repeated_statement_is_masked_once`, `tests/engine/capture/test_sql_journal.py::test_sql_journal_event_content_is_this_exact_dict`, `tests/engine/capture/test_sql_journal.py::test_sql_journal_event_size_is_what_the_flat_walk_charges`, and the SQL masking corpus (`tests/masking/sql_corpus.py`, `tests/test_masking_corpus.py`).

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | Dialect consistency | Connection dialect differs from a replaced engine dialect | High | Preserve fail-closed unsupported resolution | `test_engine_dialect_follows_a_replaced_dialect` |
| 2 | Call-site tracing | Child greenlet has no application frame before its parent | High | Same application call site; no crash on shallow stack | `test_call_site_follows_greenlet_parent` |
| 3 | Routing | Several installed contexts own distinct engines | High | Only registered contexts receive the statement | `test_statement_outside_request_routed_by_registry` |
| 4 | Masking and cache | Repeated SQL is normalized and masked once; truncation boundary is stable | Critical | Stored and emitted SQL bytes are unchanged | `test_a_repeated_statement_is_masked_once`; masking corpus |
| 5 | Journal admission | Reentrant flat offer while journal lock is owned | High | Refuse and count without corrupting journal | `test_an_offer_made_while_this_thread_reads_under_the_lock_is_refused_and_counted` |
| 6 | Timing handoff | Missing context marker falls back to connection info | Medium | Start marker is consumed exactly once | `test_conn_info_fallback_without_request` |
| 7 | Trace correlation | Provider absent or active | High | Preserve `None` without provider and current span ID with provider | `tests/engine/test_otel.py` |

## Must-cover before merge

All high and critical tests listed above must pass unchanged, including the SQL masking corpus. No test edits are allowed for these cuts.

## Deferred

None.

## Known-issues cross-reference

`docs/development/overhead-budgets.md` SQL trace budget row.
