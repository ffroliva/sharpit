---
name: pr-council-review
version: "1.0"
description: >
  Use to review a sharpit pull request (or, in branch mode, a local feature branch) with a council of specialist
  reviewers: safety, contract parity, host-app compatibility, tests, simplicity. Produces a verdict and findings;
  posts to GitHub only in PR mode and only when asked.
---

# `pr-council-review`: council review

One reviewer misses what a council catches. Each persona reads the **whole diff** through its own lens, then the
findings are merged, de-duplicated and ranked.

## 0. Modes

| Mode | Invoked by | Input | Posts? |
|---|---|---|---|
| PR | `/sharpit:pr-council-review <N>` | `gh pr diff <N>`, `gh pr view <N>` | Only if the owner asks |
| Branch | `/sharpit:branch-review [--base <ref>]` | `git diff <base>...HEAD` (default base `origin/master`) | Never |

## 1. Gather

```bash
gh pr view <N> --json title,body,baseRefName,headRefName,files,commits     # PR mode
gh pr diff <N>
git diff --stat <base>...HEAD && git diff <base>...HEAD                   # branch mode
```

Also read: the plan the branch implements (`/sharpit:active`), its scenario note, and for every changed source file
the test file that covers it. Read connected code, not only the hunks: callers of a changed function, the guard chain
around a changed route.

## 2. Pre-flight (blockers before review)

- CI status (`gh pr checks <N>`) or a local `/sharpit:check` result. Red CI → report it and stop.
- No AI attribution in any commit message or the PR body.
- No change to `master`-only files without a reason (`pyproject.toml` version, `src/sharpit/__init__.py` `__version__`).
- The built UI (`src/sharpit/ui/static/`) matches `ui/` if `ui/` changed.

## 3. The council

| Persona | Reads for |
|---|---|
| **Safety** | Fails closed: activation order, guard order (headers → trusted source → Host → cross-site → token → panel access), masking before filtering, no secret in logs or errors, token handling. Any fail-open path is Critical. |
| **Side effects** | Every GET route and MCP tool is pure: no socket, file write, logger level change or `os.environ` change. A new read path without a `no_side_effects` test is High. |
| **Contract parity** | JSON shapes, key names, nulls, epoch ms, error strings vs `docs/reference/BOOTUI-CONTRACT-MVP.md` and the golden fixtures; deviations logged in the spec §14. |
| **Host compatibility** | FastAPI/Starlette internals used defensively (lowest-direct and newest), mount order, `root_path`, sub-apps, lifespan, optional imports guarded, runtime deps still only `starlette` + `packaging`. |
| **Tests** | Red-first evidence for fixes; ported tests carry `# ported:`; assertions pin behaviour, not implementation; no skips, xfails or loosened assertions; scenario Critical/High rows covered. |
| **Simplicity** | Smallest change that solves it; no speculative options; existing helpers reused; pyright strict without `# type: ignore`. |

Each persona returns findings as `severity | file:line | finding | evidence | fix`. Severity: Critical (security or
data exposure, fails open), High (contract break, side effect, broken host app), Medium (bug with a workaround, missing
test), Low (clarity, naming), Nit.

## 4. Verify every finding

Before it enters the report, reproduce or prove it: run the test, write a throwaway probe in the scratchpad, quote the
line. A finding nobody could demonstrate is downgraded to a question.

## 5. Verdict

```
Verdict: APPROVE | APPROVE WITH NITS | REQUEST CHANGES | BLOCK
Critical: n  High: n  Medium: n  Low: n
<ranked findings table>
What was not checked: ...
```

BLOCK for any Critical; REQUEST CHANGES for any High.

## 6. Posting (PR mode, only when asked)

`gh pr review <N> --comment --body-file <file>` (or `--request-changes`). Never `--approve` on the owner's behalf, never
merge. No AI attribution in the body.

## 7. Follow-up

Fix findings on the same branch (TDD), re-run `/sharpit:check`, and re-review only the delta.

## 8. Branch mode

- Base defaults to `origin/master` (`git fetch origin` first); `--base <ref>` overrides.
- **Refuse when the current branch is `master`** (or `main`): there is nothing to review; say so and stop.
- Skip §2's CI check (use `/sharpit:check` output instead) and §6 entirely.
- End with: "Branch review done. Next: open a draft PR, then `/sharpit:pr-council-review <N>`."

For high-stakes changes (activation, guard, masking, a release) escalate to `/sharpit:llm-council`.

Ported from gflow-cli's `pr-council-review`; personas rewritten for sharpit's safety model and BootUI parity.
