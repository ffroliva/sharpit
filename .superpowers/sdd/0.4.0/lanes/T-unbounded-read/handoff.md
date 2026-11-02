# T-unbounded-read handoff

Implementer: codex gpt-6-luna

## Status

DONE_WITH_CONCERNS. Worktree is `lane/0.4.0-T-unbounded-read`, based on the merged predecessor chain at `3ddeaeae`.
The Task 1 red is valid and replayed, but the implementation is incomplete: the real pytester spike remains red at head.

## Done / next

- Read canonical `C:\Users\ffrol\AGENTS.md`, COMMON.md, lane plan, global plan, council fixes and the cited spec sections.
- Registered with `agentctl` as `codex-0-4-0-t-unbounded-read`.
- Task 1: fixture app executes the Python-side slice over all 52 Team rows; red `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` replays as an AssertionError in a detached worktree.
- Implemented a first cut of paging context, ORM load facts, gate, factor and marker. Unit paging and existing gate/import/code-shape checks passed, but the pytester integration still emits no finding.
- Next: diagnose why the nested pytest runtime does not carry the recorded Mapper facts through `apply_unbounded_read_facts`; then add per-statement/request controls and rerun the spike. Keep the `May touch` list as a hard boundary.

## Decisions / limits

- The fixture uses SQLite `StaticPool` so its in-memory schema is shared with TestClient's thread.
- `engine/sqla.py` ownership gate is satisfied by the merged predecessor chain; no intersecting lane is registered active.
- No held-out benchmark path was accessed.

## Red SHAs

- Task 1: `cb7fc450ec3429a27ef4a197bf57cf8864d3c022` — assertion red verified by `red_check.py` and detached replay.

## Gates

Targeted run: `77 passed, 1 failed`; the sole failure is the F2 spike assertion (implementation unresolved). `tests/engine/test_import_boundary.py`, `tests/test_code_shape.py`, gate tests, and paging tests passed in that run. Full suite and repository-wide ruff/format/pyright are still pending.

## Resume

Run targeted tests only during the inner loop plus import-boundary and code-shape checks. Background the one final full suite, then run ruff, ruff format check and pyright. Logs must remain outside this worktree.
