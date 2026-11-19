# B1 — SQL runtime insight kinds

Production path: `src/sharpit/engine/collectors/insights/registry.py:KINDS` registers each module; `src/sharpit/engine/collectors/insights/service.py:InsightsService.evaluate` evaluates implemented kinds and assigns observation statuses.

| Scenario | Expected behaviour |
|---|---|
| SQL evidence meets a kind's BootUI threshold | One finding with BootUI's wording and evidence shape, with SQL literals masked |
| SQL evidence is incomplete or a required source is missing | Status reflects `PARTIAL`, `INSUFFICIENT`, or `UNAVAILABLE`; no unsupported negative conclusion |
| Kind cannot be represented from sharpit's recorded evidence | Keep `IMPLEMENTED = False`; record an `n-a` or `partial` deviation |
| SQL text contains a secret literal | Finding text and serialized detail contain no literal secret |

- [ ] **Step 1:** Port and commit repeated-selects tests, then implementation and flag.
- [ ] **Step 2:** Port and commit paged-without-order tests, then implementation and flag.
- [x] **Step 3:** Port and commit unbatched-write-loop tests, then implementation and flag.
- [x] **Step 4:** Stop proxy-bypass as `n-a`: sharpit records no SQL application frames to resolve proxy boundaries.
- [x] **Step 5:** Stop event-loop-blocking as `n-a`: sharpit records no event-loop thread classification.
- [x] **Step 6:** Update parity counts, README, ROADMAP, and CHANGELOG for the implemented kind; run lane gates.
