# Lane T-suite-speed: the full suite in about 2 minutes, reliably

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `T-suite-speed` (worktree `C:\development\github\sharpit-wt\0.5.0-T-suite-speed`, branch `lane/0.5.0-T-suite-speed`, from `release/0.5.0`) |
| **Goal** | Owner goal: the full suite in about 2 minutes on the 22-logical-core Windows box, reliably, without weakening a test. |
| **Source** | Protocol `skills/optimize` -> `~/.agents/skills/pytest-speed/SKILL.md`. Baseline b3ded65: 444 s wall, 5503 s summed at `-n auto`. Added by the coordinator 2026-11-04. |
| **Worker** | Claude subagent; protected files by coordinator commits; reviewer another family (agy Gemini) |
| **Council** | not required (tests and the coordinator's gate script; no `src/`) |
| **Depends on** | D4 |
| **May touch** | `tests/test_patch_targets.py`, `tests/scripts/test_lane_gate.py`, `tests/scripts/test_red_check.py`, `AGENTS.md` and `skills/check/SKILL.md` (the local `-n` count), the lane folder; `scripts/dev/lane_gate.py` by coordinator commit only (`--allow-path`) |
| **Must NOT touch** | `src/`, budgets, `TIMING_MODULES`, `no_side_effects`, pyproject gate config, `tests/test_durations.json` (CI shards read `tests/shard_weights.json`; a baseline refresh needs a CI source) |

## Must-cover

None: a speed lane adds no behaviour. Every existing test still runs.

## Tasks

- [ ] Each fix has a red pinning a count, never a wall-clock threshold.
- [ ] Paired A/B against the base, interleaved; worker-count table recorded in `findings.md`.
