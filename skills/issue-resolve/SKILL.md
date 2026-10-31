---
name: issue-resolve
version: "1.0"
description: >
  Use when asked to fix a sharpit GitHub issue end to end: worktree from master, a failing test that reproduces it,
  the fix, the gates, and a draft PR. Never merges.
---

# `issue-resolve`: fix an issue in a worktree with TDD

Load and follow `superpowers:using-git-worktrees`, `superpowers:systematic-debugging` and
`superpowers:test-driven-development`. This skill adds sharpit's specifics.

## 1. Assess first

Run `/sharpit:issue-assessment <N>` unless it already ran this session. If the fix size is M or L, stop and recommend
`/sharpit:predict` + `/sharpit:plan` instead.

## 2. Worktree

```bash
git fetch origin
git worktree add ../sharpit-<N>-<slug> -b fix/<N>-<slug> origin/master
cd ../sharpit-<N>-<slug> && uv sync --extra test      # background it
```

Never fix on a shared checkout, on `master`, or on another agent's branch.

## 3. Red

Write the test that reproduces the issue, in the test file that owns the module (mirror `src/sharpit/<path>` under
`tests/`). Run only it and watch it fail **for the reported reason**. Safety issues get the stronger test: assert the
fail-closed behaviour (404, masked value, no side effect via `no_side_effects`), not just the absence of the symptom.

## 4. Green

The smallest change in the module that owns the cause. If the code ports BootUI, check the Java original
(`bootui-*/src/main/java/...`) so the fix keeps parity; if it must diverge, log it in the spec §14.

## 5. Gates

`/sharpit:check` (full suite in the background). Then `/sharpit:live-verify` if an endpoint or the UI changed.

## 6. Commit and draft PR

```bash
git add <explicit paths>
git commit -m "fix: <what was wrong> (#<N>)"
git push -u origin fix/<N>-<slug>             # only when the owner allows pushing in this session
gh pr create --draft --base master --title "fix: ... (#<N>)" --body "Fixes #<N> ..."
```

PR body: cause (with evidence), the red test name and its failing output, the fix, gates run. No AI attribution
anywhere in commits or the PR. If pushing is not allowed in this session, stop after the commit and print the commands.

## 7. Review

`/sharpit:pr-council-review <PR>`. Never merge; the owner merges.

Ported from gflow-cli's `issue-resolve`; base branch is `master`, gates are sharpit's.
