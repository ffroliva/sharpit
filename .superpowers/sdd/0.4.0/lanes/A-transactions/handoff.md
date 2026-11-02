# Handoff: A-transactions

Implementer: Codex (GPT-6)

## Status

In progress. Started at `a766132de82c0305b5cc4a1066a8a1a24cd2745a` on `lane/0.4.0-A-transactions`; no upstream changes merged or rebased.

## Done

- Read the canonical agent rules, the full COMMON brief, spec, global plan, lane plan, council amendments, and F handoff.
- Registered with agentctl as `codex-0-4-0-a-transactions`.
- Task 1 nullable field fixture committed; the captured transaction golden is absent here, so parity remains unverified until coordinator supplies it.

## Next step

Task 2: add assertion reds and the transaction recorder in `engine/capture/transactions.py`, then wire tests against real SQLite connection events. Do not edit `engine/sqla.py`.

## Decisions

- Follow F handoff: `_configure_capture(app, ctx, settings) -> CaptureWiring`; transaction listener arm/removal belongs in `CaptureState.attachers` so late SQLAlchemy imports and lifespan restarts are handled.
- If connection-event slot lacks a commit-failure event, park `test_failed_commit_is_unknown`; never modify `sqla.py`.
- Golden parity is unverified because `tests/fixtures/bootui/2.2.0/transactions/captured.json` is absent.

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| None yet | — | — |

## Commands / gates

Not run yet. Full suite log must be outside this worktree; max xdist workers: 4.

## Live check

Not run. Shared example and ports are out of lane scope.
