# T-suite-speed handoff

Implementer: Claude subagent (claude-opus-5-5); protected `scripts/dev/lane_gate.py` by coordinator commits

## Status

Done. Full suite 169-178 s at `-n 8` (no failures in 3 runs), 139-161 s at `-n 12` (budget failures in 2 of 7 runs). The
owner's ~2 min is not reliably reached: see `findings.md`.

## What changed

- `tests/test_patch_targets.py`: one source index per file (9a9b4a8).
- `scripts/dev/lane_gate.py` (coordinator): object-id reads cached without the repo, a tree listing plus changed blobs,
  `worktree prune` only after a failed remove (e229b03, fe3c3f8). `_resolve` is never cached: it proves a sha per repo.
- `tests/scripts/test_red_check.py`: workers share one `verdicts` build; a waiter retries a file Windows still holds
  (0e0788d, c948ab4).
- `tests/scripts/test_lane_gate.py`: fixture copies read git objects through `alternates` (d459bcd).
- `AGENTS.md`, `skills/check/SKILL.md`: the local full suite runs at `-n 8` (`-n auto` is 22 on this box). CI keeps `-n auto`.

No test skipped, deselected, xfailed or marked slow. No budget, `TIMING_MODULES`, `no_side_effects` or `src/` change.

## Open

- PS-007 (`src/sharpit/engine/sources/sqlite.py`) is the next lever, ~180 s summed: owner decision.
- `-n 12` budget failures are not shown to be noise; `-n 8` is what the docs say.
- CI shard weights can refresh only from a CI run: needs a pushed branch (owner question).

## How to resume

`git log release/0.5.0..lane/0.5.0-T-suite-speed`. Gate with `--allow-path scripts/dev/lane_gate.py`.
