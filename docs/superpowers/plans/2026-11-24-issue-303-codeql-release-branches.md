# Issue #303: CodeQL on pull requests into release branches

The proposed change enables CodeQL default setup for pull requests into `release/*` and verifies CodeQL and the
Sonar ratchet on the ship branch before the release pull request into `main` is ready for review.

## Measurement

A draft pull request into `release/0.9.0` ([#318](https://github.com/ffroliva/sharpit/pull/318), 2026-11-24)
records four commits with CodeQL default setup enabled.

| Commit | Protection on `release/0.9.0` and change | CodeQL evidence |
|---|---|---|
| `02859c22` | Ruleset only, Markdown change | No analyses |
| `7639d982` | Ruleset only, Python change | No analyses |
| `a099d12a` | Ruleset and classic rule, empty commit | No check run observed. Cause undetermined. |
| `7b376461` | Ruleset and classic rule, Python change | `actions`, `javascript-typescript`, `python` |

A draft into `main` ([#319](https://github.com/ffroliva/sharpit/pull/319)) also has all three analyses.
The measurements support adding the classic rule alongside ruleset `27883117`. The temporary rule is removed
after the measurement.

## Proposed release procedure

Issue #303 calls for a scan before opening the release pull request. The proposed deviation is to scan while
the pull request is draft. This uses the actual diff into `main` even when a version branch does not yet exist.
The old branch scan checks a ref that CodeQL does not scan, and the Sonar ratchet's branch mode is a no-op
outside `main`.

- [ ] Step 8 in `skills/release/SKILL.md` verifies that exactly one classic rule matches the pattern `release/*`.
  It opens or reuses the release pull request as a draft into `main`, waits for checks, and runs
  `uv run python scripts/ci/ship_scan.py <PR_NUMBER>`. After exit 0, the skill compares the verified SHA with
  the current head before `gh pr ready <N>`. If the head changes, it waits for the new checks and runs the
  script again. Step 9 reviews and merges the existing pull request.
- [ ] Update `docs/development/ci.md` with the rule, default setup, and the PR scan ref. Update
  `docs/development/workflow.md` with the draft procedure. Add the decision record
  `docs/decisions/codeql-release-branches.md`, index it in `docs/decisions/README.md`, and add it to
  `src/sharpit/cli/docs_catalog.py`. Record the rule and draft procedure as proposed until approved.
- [ ] Add a `tests/docs/` check that step 8 opens a draft into `main` and invokes `ship_scan.py` before
  marking it ready. Prove the check by removing each required element in turn.

## Ship scan contract

- [ ] Add `scripts/ci/ship_scan.py` with `main(argv: list[str] | None = None) -> int`, following
  `scripts/ci/sonar_ratchet.py`. Use the standard library and isolate all `gh` subprocess calls behind
  one function that tests replace with fixtures. The only CLI argument is a positive pull request number
  in `ffroliva/sharpit`. Either release head naming convention works, as in #281/#282
  (`chore/release-<version>`) and #298 (`release/<version>`).
- [ ] Exit `0` and print the verified head SHA on success. Exit `1` when a release check fails or its
  evidence is absent. Exit `2` on invalid input, API failure, or malformed or incomplete response data.
  Report the reason to stderr on nonzero exit. The script makes only read requests.
- [ ] Read the PR and capture its head SHA. Require draft status and base `main`. On `refs/pull/<N>/head`,
  require the exact CodeQL category set `/language:actions`, `/language:javascript-typescript`, and
  `/language:python` for that SHA, and zero open code scanning alerts on the ref.
- [ ] Require the PR's own `pull_request` run of `.github/workflows/ci.yml` for that SHA. Match the run to the
  PR number using explicit PR evidence. In the latest attempt of the latest matching run, the `sonar` job must
  contain `Sonar ratchet (no new issues; main never above sonar-baseline.txt)` with conclusion `success`.
  A missing or skipped step fails the gate, even when the job is green. A `push` run for the same SHA
  can report success after a no-op ratchet. Paginate the run, job, analysis, and alert lists. CI runs can have
  45 jobs.
- [ ] Re-read the PR after the checks and reject a changed head SHA.
- [ ] Add fixtures under `tests/scripts/` for a pass and each failure. Cover API error, parse error,
  non-draft PR, wrong base, missing or extra category, stale CodeQL SHA, missing PR CI run with same-SHA push CI,
  wrong or unproven PR association, missing ratchet step, skipped step, other unsuccessful conclusion,
  open alert, and changed head. Include pagination in the pass case and place an open alert on a later page
  in its failure case. See each failure assertion red before implementing its guard, then delete each guard
  in turn to show the test fails.

## Proposed classic protection rule

The rule covers `release/<version>` and leaves fast-forward pushes open. It adds no required check or review.
Ruleset `27883117` stays in place. Fork PR scanning is outside this change. Administrator bypass, branch deletion
under the classic rule, and CodeQL push scans on `release/<version>` remain unverified.

After approval, the maintainer creates and lists the rule, then inspects its effective settings.

```bash
RID=$(gh api graphql -f query='{repository(owner:"ffroliva",name:"sharpit"){id}}' --jq .data.repository.id)
gh api graphql -f r="$RID" -f query='mutation($r:ID!){
  createBranchProtectionRule(input:{repositoryId:$r,pattern:"release/*"}){branchProtectionRule{id}}
}'
gh api graphql --paginate -f query='query($endCursor:String){
  repository(owner:"ffroliva",name:"sharpit"){branchProtectionRules(first:100,after:$endCursor){
    nodes{id pattern} pageInfo{hasNextPage endCursor}
  }}
}' --jq '.data.repository.branchProtectionRules.nodes[] | select(.pattern == "release/*")'
gh api repos/ffroliva/sharpit/branches/release%2F0.9.0/protection \
  --jq '{checks: .required_status_checks, reviews: .required_pull_request_reviews,
    admins: .enforce_admins.enabled, force_pushes: .allow_force_pushes.enabled,
    deletions: .allow_deletions.enabled}'
```

Expect one matching rule, null checks and reviews, and false values for admin enforcement, force-pushes, and
deletions. To undo, use the matching rule ID as `RULE_ID`.

```bash
gh api graphql -f r="$RULE_ID" -f query='mutation($r:ID!){
  deleteBranchProtectionRule(input:{branchProtectionRuleId:$r}){clientMutationId}
}'
```

## Verification

- [ ] Run `uv run --extra test pytest -q -n 4 tests/docs tests/scripts`.
- [ ] On [#298](https://github.com/ffroliva/sharpit/pull/298), use read-only API calls to confirm the PR
  metadata and stable head SHA, compare PR run `45199386677` with same-SHA push run `45199371013`, inspect
  the PR run's paginated jobs for the ratchet step conclusion, and check exact-head CodeQL categories and
  open alerts on `refs/pull/298/head`. The historical PR run has an empty `pull_requests` list. Its `sonar`
  job log identifies `PR: 298` for the ratchet step. The merged PR's non-draft status fails the live gate.
- [ ] If the rule is approved and enabled, record the CodeQL analysis categories and SHA for the first
  measured push to `refs/heads/release/<version>`. Expect all three categories on the pushed head.
- [ ] Close #303 only after the maintainer resolves the rule decision and step 8 runs successfully once
  on a real ship branch under the accepted procedure.
