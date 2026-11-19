# B1 — SQL runtime insight kinds

Production path: `src/sharpit/engine/collectors/insights/registry.py:KINDS` registers each module; `src/sharpit/engine/collectors/insights/service.py:InsightsService.evaluate` evaluates implemented kinds and assigns observation statuses.

| Scenario | Expected behaviour |
|---|---|
| SQL evidence meets either shipped kind's BootUI threshold | One finding with BootUI's wording and evidence shape, with SQL literals masked |
| SQL evidence is incomplete or a required source is missing | Status reflects `PARTIAL`, `INSUFFICIENT`, or `UNAVAILABLE`; no unsupported negative conclusion |
| `paged-without-order` has no BootUI row-limit and SQL-shape analysis port | Keep `IMPLEMENTED = False`; record as deferred with the reason |
| SQL text contains a secret literal | Finding text and serialized detail contain no literal secret |

- [x] **Step 1:** Port repeated-selects, including route denominators, request-id gating, incomplete evidence, monotonic ordering and the default-list floor.
- [x] **Step 2:** Defer paged-without-order until BootUI's SQL row-limit and shape analysis is ported.
- [x] **Step 3:** Port unbatched-write-loop, including route denominators, unreadable evidence, batch sizes and duration limits.
- [x] **Step 4:** Stop proxy-bypass as `n-a`: sharpit records no SQL application frames to resolve proxy boundaries.
- [x] **Step 5:** Stop event-loop-blocking as `n-a`: sharpit records no event-loop thread classification.
- [x] **Step 6:** Update parity counts, README, ROADMAP, and CHANGELOG for the two implemented kinds; run lane gates.
