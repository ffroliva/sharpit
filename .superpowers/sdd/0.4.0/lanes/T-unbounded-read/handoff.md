# T-unbounded-read handoff

Implementer: codex gpt-6-luna

## Status

DONE_WITH_CONCERNS. Worktree is `lane/0.4.0-T-unbounded-read`, based on the merged predecessor chain at `3ddeaea`.
The F2 spike now passes. The requested full edge-case matrix remains incomplete and is listed below.

## Done / next

- Read canonical instructions, COMMON.md, lane plan, global plan, council fixes and cited spec sections.
- Registered with `agentctl` as `codex-0-4-0-t-unbounded-read`.
- The fixture exercises a Python-side slice over 52 Team rows with page size 5. Replacement red `2e373d7bcf262633b98a961e76d942d0b4796dd2` replays as an AssertionError; original red `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` is historical and unchanged.
- Fixed the fixture to explicitly enable capture in pytest's non-reload process. The spike test passes.
- Fixed fixture conftest shadowing. Full collection now reports 4,386 collected with no errors.
- Compared the previous safety-sweep and capture-overhead failures against release `3ddeaea`; both passed there (2 passed).
- Remaining tests: per-statement/request ORM count controls; lazy paging after route match; no-install limitation; LIMIT/FETCH, non-paged, lookup-query, threshold, marker, report-only and baseline controls. These must be added red-first before considering this lane complete.

## Decisions / limits

- SQLite `StaticPool` shares the in-memory schema with TestClient's thread.
- `engine/sqla.py` ownership gate is satisfied by the merged predecessor chain; no intersecting lane is registered active.
- No held-out benchmark path was accessed.

## Red SHAs

- Replacement F2: `2e373d7bcf262633b98a961e76d942d0b4796dd2` — assertion red verified by `red_check.py` and detached replay.
- Historical F2: `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` — superseded and retained unchanged.

## Gates

- Focused plugin, paging, SQLAlchemy, gate, import-boundary and code-shape tests: 79 passed.
- Collection: 4,386 tests collected, no errors.
- Release-base regression comparison: 2 passed.
- Current lint, format, pyright and final full-suite results are pending their background logs.

## Resume

Add the remaining edge tests red-first within the lane's May-touch list. Logs stay outside this worktree.
