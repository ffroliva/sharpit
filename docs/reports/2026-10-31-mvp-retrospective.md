# sharpit MVP: retrospective (2026-10-31)

Outcome and the full list of rulings: [`2026-10-31-mvp-summary.md`](2026-10-31-mvp-summary.md). The SDD ledger is in
`.superpowers/sdd/2026-10-30-sharpit-mvp/progress.md` (git-ignored, worktree only).

## Worked

- **Council review of the spec and the plan.** Codex, Gemini and Claude reviewed both before any code was written. No
  task needed a re-plan.
- **One subagent per task, then a task review.** All 17 tasks plus 3 polish tasks landed sequentially without
  worktree conflicts.
- **Layered final reviews.** The whole-branch review, `/code-review xhigh` and the ponytail review each found real
  defects the others missed. Examples: the token leak with masking off, the trusted-proxy token bypass, `SHARPIT_PATH=/`
  and a misspelled panel flag.
- **Dogfooding on KliperMedia.** It found the 7.6 s config scan and the `--reload` port hold on Windows. The Docker
  lease was coordinated with the KliperMedia agent through agentctl.

## Didn't work

| What | Root cause | Mechanism now in place |
|---|---|---|
| CI had never run on GitHub until the final push. 4 failures surfaced at the end. | Before that, it was validated only by local runs. | CI runs on every push to `mvp`/`master`. The summary now lists it as a gate. |
| A job-level `if: hashFiles(...)` made the workflow invalid. | `hashFiles` is not allowed in a job-level `if`. | The condition is removed. A workflow error fails the run visibly. |
| A vitest test failed on a 12-hour-clock runner. | The test hard-coded a 24-hour format. | The test derives the expected text from the same locale API. |
| The Starlette floor of 0.40 could not run the suite. | The floor was declared, never tested. | A `lowest` CI job resolves the lowest direct versions. The floor is now 0.44. |
| The `lowest` job still ran new Starlette. | A plain `uv run` re-syncs to `uv.lock`. | The job runs `uv run --no-sync`, with a comment saying why. |
| A `&&` chain printed a stale pytest log after ruff failed. | The log was not cleared before the chain. | The log is deleted before each gated run, and the result is read from the task output. |

## Open

Backlog and owner calls: see the summary, sections "Calls for you" and "Backlog".
