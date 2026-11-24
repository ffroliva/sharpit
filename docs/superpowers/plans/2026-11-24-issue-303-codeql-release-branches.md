# Issue #303: CodeQL on pull requests into release branches

**Goal:** a pull request into a release branch gets the CodeQL analysis that a pull request into `main` gets.

**Branch:** `docs/303-codeql-release`, from `origin/main`. One pull request, documentation only, plus one repository
setting that the maintainer applies.

**Method:** the setting was measured on a probe pull request before this plan; the pull request documents it.

## What was measured

CodeQL runs as GitHub's default setup. A draft pull request into `release/0.9.0` was pushed three times:

| State of `release/0.9.0` | Commit | CodeQL analyses |
|---|---|---|
| `release branches` ruleset only, Markdown change | `02859c22` | none |
| `release branches` ruleset only, Python change | `7639d982` | none |
| Ruleset and a classic branch protection rule, Python change | `7b376461` | `actions`, `javascript-typescript`, `python` |

A draft pull request into `main` on the same day got all three, so draft status is not the cause. The ruleset added for
lane H6 does not make default setup treat a branch as protected; a classic branch protection rule does. The rule was
removed after the measurement.

## Design

- The maintainer adds a classic branch protection rule for `release/*` with every requirement off. It blocks
  force-pushes and deletion, which the ruleset already blocks, and requires no check or review, so direct pushes to a
  release branch keep working.
- Default setup stays on. No workflow file is added.

## Seams

| Seam | What it catches | What it misses |
|---|---|---|
| The probe above | Whether the rule triggers the scan of a pull request | Push scans of a release branch: predicted, confirmed on the first push to `release/0.10.0` |

## Tasks

### Task 1: document the rule

Files: `docs/development/ci.md` (the `release/**` paragraph under the job table).

- State that CodeQL default setup scans pull requests into `main` and, through the classic rule, into `release/*`;
  that a ruleset alone does not trigger it; and the commands that create the rule and list it.
- `skills/release/SKILL.md` step 8 (scan the ship branch) is unchanged: it already reads the analyses before the alerts.

### Task 2 (maintainer): enable the rule

```bash
RID=$(gh api graphql -f query='{repository(owner:"ffroliva",name:"sharpit"){id}}' --jq .data.repository.id)
gh api graphql -f query='mutation($r:ID!){createBranchProtectionRule(input:{repositoryId:$r,pattern:"release/*"}){branchProtectionRule{id}}}' -f r=$RID
```

Undo: `deleteBranchProtectionRule` with the returned id.

## Verification

- `uv run pytest -q -n 4 tests/docs` and `scripts/ci/no_superpowers.py` pass on the branch.
- After Task 2, a pull request into a release branch shows the three `Analyze` checks. The issue closes then.
