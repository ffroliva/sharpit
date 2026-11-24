# Issue #303: CodeQL on pull requests into release branches

**Goal:** a pull request into a release branch gets the CodeQL analysis that a pull request into `main` gets, and the
ship branch is scanned by CodeQL and the code-scan ratchet before the release pull request into `main` is ready for
review.

**Branch:** `docs/303-codeql-release` (the implementation branch differs from this plan's branch,
`docs/plan-303-codeql-release`). One documentation pull request, plus one repository setting that the maintainer
applies. Issue #303 describes a workflow edit; this plan replaces it with the setting, and replaces "before the release
pull request opens" with "before it is ready for review", a deviation the maintainer approves. Nothing here is enforced
until the setting is on.

## What was measured

CodeQL runs as GitHub's default setup. A draft pull request into `release/0.9.0`
([#318](https://github.com/ffroliva/sharpit/pull/318), 2026-11-24) was measured across four commits (the fourth commit,
`a099d12a`, was an empty commit after the classic branch protection rule was enabled and triggered no language scan):

| State of `release/0.9.0` | Commit | CodeQL analyses |
|---|---|---|
| `release branches` ruleset only, Markdown change | `02859c22` | none |
| `release branches` ruleset only, Python change | `7639d982` | none |
| Ruleset and classic protection rule, empty commit | `a099d12a` | none |
| Ruleset and classic protection rule, Python change | `7b376461` | `actions`, `javascript-typescript`, `python` |

A draft pull request into `main` ([#319](https://github.com/ffroliva/sharpit/pull/319)) on the same day got all three,
so draft status is not the cause. In this measurement the ruleset added for lane H6 did not make default setup treat a
branch as protected; the classic branch protection rule did. The rule was removed after the measurement.

## Design

- The maintainer adds a classic branch protection rule for `release/*` with no required check or review. Default setup
  stays on; no workflow file is added.
- `release/*` matches `release/0.6.0` to `release/0.9.0` and every `release/<version>`. It does not match a nested name
  such as `release/0.10/hotfix`, which the project does not use.
- Default setup does not scan pull requests from forks; those are outside this change.
- Ruleset `27883117` stays. The classic rule adds the same two restrictions (no force-push, no deletion) and leaves
  fast-forward pushes open. Both apply together. Unverified: administrator bypass under the classic rule
  (`isAdminEnforced` is off, not exercised) and whether the classic rule blocks deleting a `release/<version>` branch.
- The setting lives outside the repository, so the release skill checks that it exists before it relies on it.
- Opening a draft pull request from `chore/release-<version>` into `release/<version>` would scan only the version bump
  (CodeQL on a pull request is diff-informed, and `sonar_ratchet.py --pull-request` counts only new issues against the
  base branch), and `release/<version>` may not exist. Instead, step 8 opens step 9's pull request from
  `chore/release-<version>` into `main` as a draft (`gh pr create --draft --base main`), requires the three CodeQL
  analyses (`refs/pull/<N>/head`) and the `Sonar ratchet` step with conclusion `success` on the exact head commit, reads
  the alerts, and marks the pull request ready for review (`gh pr ready <N>`). This satisfies the issue's "before the
  release pull request opens" as "before it is ready for review", a deviation the maintainer approves.

## Seams

| Seam | What it catches | What it misses |
|---|---|---|
| Pull request #318 | Whether the rule triggers a PR scan | Push scans (`refs/heads/release/<v>`): unverified |
| Rule check in step 8 | The rule deleted or renamed | A change in what default setup scans |

## Tasks

### Task 1: the release skill, the CI documentation and the decision record

Files: `skills/release/SKILL.md` (steps 8 and 9), `docs/development/ci.md` (the `release/**` paragraph),
`docs/development/workflow.md` (lines 143-145), `docs/decisions/README.md`,
`docs/decisions/codeql-release-branches.md`, `src/sharpit/cli/docs_catalog.py`, `tests/docs/`. Do not edit earlier
plans.

Step 8 currently reads `refs/heads/chore/release-<version>`, which no scan covers, and `sonar_ratchet.py --branch`
passes for any branch but `main` without querying SonarCloud (`scripts/ci/sonar_ratchet.py`, `main`).

- [ ] Step 8 becomes: check that the `release/*` classic branch protection rule exists (expect 1 rule; stop otherwise);
  open step 9's release pull request from `chore/release-<version>` into `main` as a draft; wait for its checks; verify
  on its exact head commit (`HEAD_SHA`) that the `sonar` job ran the step `"Sonar ratchet (no new issues; main never
  above sonar-baseline.txt)"` with `conclusion == "success"` (a green `sonar` job can skip that step when SonarCloud is
  unreachable or the change is not marked as code in `.github/workflows/ci.yml` lines 556-600; stop otherwise); confirm
  three CodeQL analyses (`actions`, `javascript-typescript`, `python`) on `refs/pull/<N>/head` for `HEAD_SHA` (expect 3
  analyses on the head SHA; stop otherwise); read open alerts on `refs/pull/<N>/head` (expect 0; stop otherwise); then
  mark the pull request ready for review (`gh pr ready <N>`). Step 9 then runs the council review and merges the
  already-open pull request.

```bash
HEAD_SHA=$(git rev-parse HEAD)
# expect 1 rule for release/*; stop otherwise
gh api graphql \
  -f query='{repository(owner:"ffroliva",name:"sharpit"){branchProtectionRules(first:20){nodes{pattern}}}}' \
  --jq '[.data.repository.branchProtectionRules.nodes[] | select(.pattern == "release/*")] | length'
gh pr create --draft --base main --head "chore/release-<version>" \
  --title "chore: release <version>" --body "Release <version>. See CHANGELOG.md."
gh pr checks <N> --watch # background it
RUN_ID=$(gh api "repos/ffroliva/sharpit/commits/$HEAD_SHA/check-runs" \
  --jq '.check_runs[] | select(.name == "sonar") | .details_url' | sed -E 's|.*/runs/([0-9]+)/job/.*|\1|')
# expect 1 (Sonar ratchet step ran and succeeded); stop otherwise
gh api "repos/ffroliva/sharpit/actions/runs/$RUN_ID/jobs" \
  --jq '[.jobs[] | select(.name == "sonar") | .steps[]
    | select((.name | startswith("Sonar ratchet")) and .conclusion == "success")] | length'
# expect 3 CodeQL categories on HEAD_SHA; stop otherwise
gh api "repos/ffroliva/sharpit/code-scanning/analyses?ref=refs/pull/<N>/head" \
  --jq --arg sha "$HEAD_SHA" '[.[] | select(.commit_sha == $sha) | .category] | unique | length'
# expect 0 open alerts; stop otherwise
gh api "repos/ffroliva/sharpit/code-scanning/alerts?ref=refs/pull/<N>/head&state=open" --jq 'length'
gh pr ready <N>
```

- [ ] `docs/development/ci.md`: default setup scans pull requests into `main` and, through the classic rule, into
  `release/*`; a ruleset alone did not trigger it; analyses of a pull request are under `refs/pull/<N>/head`.
- [ ] `docs/development/workflow.md` (lines 143-145): state that `chore/release-<version>` opens as a draft pull request
  into `main` and is marked ready for review after the `Sonar ratchet` step and the three CodeQL analyses succeed on its
  head commit.
- [ ] `docs/decisions/codeql-release-branches.md`, `docs/decisions/README.md` and `src/sharpit/cli/docs_catalog.py`:
  record the decision to use a classic `release/*` branch protection rule with GitHub's CodeQL default setup instead of
  a custom CodeQL workflow file, and to scan the release pull request into `main` as a draft before marking it ready for
  review, following the `docs/decisions/` index format (`Status`, `Decision`, `Rationale`, `Consequences`,
  `Enforced by`).
- [ ] `tests/docs`: a test asserting that `skills/release/SKILL.md` step 8 no longer names
  `sonar_ratchet.py --branch chore/release-` and requires all four elements of the replacement procedure:
  1. `refs/pull/<N>/head`,
  2. exact-head comparison (`commit_sha` matched against `HEAD_SHA` / `git rev-parse HEAD`),
  3. the `Sonar ratchet` step conclusion check (`startswith("Sonar ratchet")` and `conclusion == "success"`),
  4. opening the pull request into `main` as a draft (`gh pr create --draft --base main`) before `gh pr ready`.
  Each assertion is proven red by deleting that required element from `skills/release/SKILL.md` and running the test.

### Task 2 (maintainer): enable the rule and measure a push scan

- [ ] Create the rule, then verify the count and compare the settings with the design:

```bash
RID=$(gh api graphql -f query='{repository(owner:"ffroliva",name:"sharpit"){id}}' --jq .data.repository.id)
gh api graphql -f r="$RID" -f query='mutation($r:ID!){
  createBranchProtectionRule(input:{repositoryId:$r,pattern:"release/*"}){branchProtectionRule{id}}
}'
# expect 1 rule for release/*; stop otherwise
gh api graphql \
  -f query='{repository(owner:"ffroliva",name:"sharpit"){branchProtectionRules(first:20){nodes{id pattern}}}}' \
  --jq '[.data.repository.branchProtectionRules.nodes[] | select(.pattern == "release/*")] | length'
gh api repos/ffroliva/sharpit/branches/release%2F0.9.0/protection \
  --jq '{checks: .required_status_checks, reviews: .required_pull_request_reviews,
    admins: .enforce_admins.enabled, force_pushes: .allow_force_pushes.enabled,
    deletions: .allow_deletions.enabled}'
```

  Expected: `1` rule for `release/*`, `checks` and `reviews` equal to `null`, and `admins`, `force_pushes` and
  `deletions` equal to `false`; stop otherwise. Undo: `deleteBranchProtectionRule` with `branchProtectionRuleId` set to
  the id.

- [ ] Measure one push scan on a `release/<version>` branch after the rule is enabled, and record the `gh api` evidence:

```bash
REL_SHA=$(gh api "repos/ffroliva/sharpit/commits/refs/heads/release/<version>" --jq .sha)
gh api "repos/ffroliva/sharpit/code-scanning/analyses?ref=refs/heads/release/<version>" \
  --jq --arg sha "$REL_SHA" '[.[] | select(.commit_sha == $sha) | {commit_sha, category, created_at}]'
```

  Expected: three analyses (`actions`, `javascript-typescript`, `python`) on `refs/heads/release/<version>` for
  `REL_SHA`; stop otherwise.

## Verification

- [ ] `uv run --extra test pytest -q -n 4 tests/docs` passes on the implementation branch, and deleting each of the four
  required step 8 elements in `skills/release/SKILL.md` makes the new docs test fail.
- [ ] Issue #303 closes only after the classic `release/*` branch protection rule is enabled in Task 2 and release step
  8 has been run once end-to-end on a real ship branch.
