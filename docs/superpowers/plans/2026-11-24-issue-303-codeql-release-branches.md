# Issue #303: CodeQL on pull requests into release branches

**Goal:** a pull request into a release branch gets the CodeQL analysis that a pull request into `main` gets, and the
ship branch is scanned by CodeQL and the code-scan ratchet before the release pull request into `main` opens.

**Branch:** `docs/303-codeql-release`. One documentation pull request, plus one repository setting that the maintainer
applies. Issue #303 describes a workflow edit; this plan replaces it with the setting, which needs the maintainer's
approval. Nothing here is enforced until the setting is on.

**Revision 2** folds in the plan review: release step 8 changes, the pattern's limits, rule layering, the list command,
the settings check and linked evidence.

## What was measured

CodeQL runs as GitHub's default setup. A draft pull request into `release/0.9.0` (#318, 2026-11-24) was measured on three commits:

| State of `release/0.9.0` | Commit | CodeQL analyses |
|---|---|---|
| `release branches` ruleset only, Markdown change | `02859c22` | none |
| `release branches` ruleset only, Python change | `7639d982` | none |
| Ruleset and a classic branch protection rule, Python change | `7b376461` | `actions`, `javascript-typescript`, `python` |

A draft pull request into `main` (#319) on the same day got all three, so draft status is not the cause. In this measurement the ruleset added for
lane H6 did not make default setup treat a branch as protected; the classic branch protection rule did. The rule was
removed after the measurement.

## Design

- The maintainer adds a classic branch protection rule for `release/*` with no required check or review. Default setup
  stays on; no workflow file is added.
- `release/*` matches `release/0.6.0` to `release/0.9.0` and every `release/<version>`. It does not match a nested name
  such as `release/0.10/hotfix`, which the project does not use.
- Default setup does not scan pull requests from forks; those are outside this change.
- Ruleset `27883117` stays. The classic rule adds the same two restrictions (no force-push, no deletion) and leaves
  fast-forward pushes open. Both apply together; administrators bypass each (`isAdminEnforced` is off).
- The setting lives outside the repository, so the release skill checks that it exists before it relies on it.

## Seams

| Seam | What it catches | What it misses |
|---|---|---|
| Pull request #318 | Whether the rule triggers the scan of a pull request | Push scans of a release branch: predicted only |
| The rule check in release step 8 | The rule deleted or renamed in the settings | A change in what default setup scans |

## Tasks

### Task 1: the release skill and the CI documentation

Files: `skills/release/SKILL.md` (step 8), `docs/development/ci.md` (the `release/**` paragraph).

Step 8 reads `refs/heads/chore/release-<version>`, which no scan covers, and `sonar_ratchet.py --branch` passes for any
branch but `main` without querying SonarCloud (`scripts/ci/sonar_ratchet.py`, `main`).

- [ ] Step 8 becomes: check the rule; open a draft pull request from `chore/release-<version>` into
  `release/<version>`; wait for its `sonar` job (the ratchet with `--pull-request`) and its three `Analyze` checks;
  confirm three analyses of the exact head commit; read the alerts; close the draft without merging. Step 9 then opens
  the pull request into `main`.

```bash
gh api graphql -f query='{repository(owner:"ffroliva",name:"sharpit"){branchProtectionRules(first:20){nodes{id pattern}}}}'
gh api "repos/ffroliva/sharpit/code-scanning/analyses?ref=refs/pull/<N>/head" --jq '.[]|[.commit_sha,.category]|@tsv'
gh api "repos/ffroliva/sharpit/code-scanning/alerts?ref=refs/pull/<N>/head&state=open"
```

- [ ] `ci.md`: default setup scans pull requests into `main` and, through the classic rule, into `release/*`; a ruleset
  alone did not trigger it; analyses of a pull request are under `refs/pull/<N>/head`.
- [ ] `tests/docs`: a test that fails while step 8 names `sonar_ratchet.py --branch chore/release-`.

### Task 2 (maintainer): enable the rule

- [ ] Create it, then compare the settings with the design:

```bash
RID=$(gh api graphql -f query='{repository(owner:"ffroliva",name:"sharpit"){id}}' --jq .data.repository.id)
gh api graphql -f query='mutation($r:ID!){createBranchProtectionRule(input:{repositoryId:$r,pattern:"release/*"}){branchProtectionRule{id}}}' -f r=$RID
gh api repos/ffroliva/sharpit/branches/release%2F0.9.0/protection
```

  Expected: no `required_status_checks` and no `required_pull_request_reviews`; `allow_force_pushes`, `allow_deletions`
  and `enforce_admins` disabled. Undo: `deleteBranchProtectionRule` with `branchProtectionRuleId` set to the id.

## Verification

- [ ] `uv run pytest -q -n 4 tests/docs` passes on the branch.
- [ ] After Task 2, a draft pull request into a release branch shows the three `Analyze` checks for its exact head. The
  issue closes then.
