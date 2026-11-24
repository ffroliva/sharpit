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

## Release procedure

Issue #303 calls for a scan before opening the release pull request. The accepted deviation is to scan while
the pull request is draft. This uses the actual diff into `main` even when a version branch does not yet exist.
The old branch scan checks a ref that CodeQL does not scan, and the Sonar ratchet's branch mode is a no-op
outside `main`.

PR #281 merged `chore/release-0.8.0` into `release/0.8.0`; #282 and #298 merged `release/<version>` into
`main`. The gate runs on the draft PR into `main`.

- [ ] Step 8 in `skills/release/SKILL.md` first brings the ship head up to date with `main`: merge `origin/main`
  (after a fetch) into `chore/release-<version>` and push it or, on the version-branch path, into a branch that
  reaches `release/<version>` through a staging PR. Staging PRs use a merge commit: a squash loses
  the ancestry of `main` and fails the gate. It then opens or reuses a draft PR into `main`, waits for its checks and runs
  `uv run python scripts/ci/ship_scan.py <PR_NUMBER>`. The classic rule is not a gate input: it does not affect
  the scan of a PR into `main`.
- [ ] Write out both release paths in the skill:
  - Without a `release/<version>` branch, step 3 cuts `chore/release-<version>` from `origin/main`, step 7 pushes
    it, and it is the head of the draft PR into `main`.
  - With one, step 3 cuts it from `origin/release/<version>`, step 7 also merges it into `release/<version>`
    through a staging PR, and step 8 opens the draft with `--head release/<version>`. A later fix goes through a
    new staging PR, never only to the merged chore branch.
- [ ] Step 9 runs the council on the draft head, then the gate, and requires both for the same head SHA. The
  gate prints the head and base SHA. With all checks green, `gh pr ready <N>` follows. Immediately before the
  merge, the skill confirms that the checks are still green, the base is still `main` and
  `gh api repos/ffroliva/sharpit/git/ref/heads/main --jq .object.sha` still prints the recorded base SHA. A changed head or base runs `gh pr ready <N> --undo` and returns to
  step 8 and repeats council, gate and checks.
- [ ] Merge with `gh pr merge <N> --merge --match-head-commit "$VERIFIED_SHA"`, which refuses a different head.
  GitHub has no matching flag for the base, so a push to `main` between the check and the merge remains
  possible; step 3's hold on merges to `main` covers it. After the merge only `chore/release-<version>` is
  deleted, by name, without `--delete-branch`. Ruleset `27883117` also refuses the deletion of `release/**`.
- [ ] Document the rule in `docs/development/ci.md` with default setup and the PR scan ref, and in
  `docs/development/workflow.md` and `skills/release/SKILL.md` with the draft procedure.
- [ ] Add a `tests/docs/` check that step 8 opens a draft into `main` and invokes `ship_scan.py` before
  marking it ready, that the merge command has `--match-head-commit` and no `--delete-branch`, and that the
  `release/<version>` path is present. Prove the check by removing each required element in turn.

## Ship scan contract

- [ ] Add `scripts/ci/ship_scan.py` with `main(argv: list[str] | None = None) -> int`, following
  `scripts/ci/sonar_ratchet.py`. Use the standard library and isolate all `gh` subprocess calls behind
  one function that tests replace with fixtures. The only CLI argument is a positive pull request number
  in `ffroliva/sharpit`.
- [ ] Exit `0` and print the verified head and base SHA on success. Exit `1` when a release check fails or its
  evidence is absent. Exit `2` on invalid input, API failure, malformed JSON or a missing field.
  A well-formed answer that lacks the required run, job, step, check run or category is absent evidence, exit `1`.
  Report the reason to stderr on nonzero exit. The script makes only read requests.
- [ ] Require PR state `open`, draft `true`, and base `main`, then capture its head SHA
  and the SHA of `refs/heads/main`. Require the head to contain that `main` SHA (compare API, `behind_by` is `0`).
  On `refs/pull/<N>/head`, select analyses with `tool.name == "CodeQL"` and `commit_sha` equal to the head SHA.
  Their category set must equal `{/language:actions, /language:javascript-typescript, /language:python}`,
  and every selected analysis must have an empty `error`. Use the newest analysis per category. The ref must have
  zero open code scanning alerts; dismissed alerts pass, so a dismissal stays a review matter.
- [ ] Require the newest `CodeQL` check run of app `github-advanced-security` on the head SHA to be `completed`
  (read with `filter=all`) with conclusion `success`. `neutral` and `skipped` fail.
- [ ] Match runs by path `.github/workflows/ci.yml`, event `pull_request`, exact `head_sha`, and PR number
  in `run.pull_requests`. The list is empty on the closed #298 and names the PR on the open #321. An empty list cannot establish a match
  on an open PR, so the gate fails closed if no run matches.
  Select the match with the greatest `run_number` and inspect jobs from its latest attempt only.
  Require the `sonar` job to have status `completed` and conclusion `success`, and its step
  `Sonar ratchet (no new issues; main never above sonar-baseline.txt)` to have conclusion `success`.
- [ ] Read paginated calls with `gh api --paginate --slurp` and parse the one array of pages, combining the
  `check_runs`, `workflow_runs` or `jobs` lists from object pages and the entries from array pages for analyses
  and alerts.
- [ ] Re-read the PR and `refs/heads/main` after the checks and reject a changed head SHA, base branch, base SHA,
  state or draft flag.
- [ ] Add fixtures under `tests/scripts/` for a pass and each failure. Cover API error, parse error,
  non-draft PR, closed draft (#319), wrong base, missing or extra category, stale SHA, wrong analysis tool,
  analysis with an error, missing, unfinished, neutral or failed `CodeQL` check run, check run of another app,
  same-SHA push run, wrong workflow path, wrong or empty PR association, success only on an older run or attempt,
  incomplete or unsuccessful job, missing or skipped ratchet step, other unsuccessful step conclusion,
  open alert, head behind `main`, and a head, base branch or base SHA changed during the checks. Use several pages for all five endpoints in the pass fixture and a later-page alert
  in its failure case. See each failure assertion red before implementing its guard, then delete each guard
  in turn to show the test fails.

## Classic protection rule

The rule covers `release/<version>` and leaves fast-forward pushes open. It adds no required check or review.
Ruleset `27883117` stays in place. Fork PR scanning is outside this change. Administrator bypass, branch deletion
under the classic rule, and CodeQL push scans on `release/<version>` remain unverified.

The rule is created once this plan is accepted: create it, list it, then its effective settings.

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

- [ ] Run `uv run --extra test pytest -q -n 4 tests/docs tests/scripts tests/test_code_shape.py tests/test_ci_layout.py`,
  `uv run ruff check`,
  `uv run ruff format --check` and `uv run pyright`.
- [ ] On [#298](https://github.com/ffroliva/sharpit/pull/298), use read-only API calls to confirm the PR
  metadata and stable head SHA, compare PR run `45199386677` with same-SHA push run `45199371013`, inspect
  the PR run's paginated jobs for the ratchet step conclusion, and check exact-head CodeQL categories and
  open alerts on `refs/pull/298/head`. The historical run's empty `pull_requests` list cannot verify association.
- [ ] On the first open draft release PR into `main`, verify that the matching CI run lists its PR number
  in `run.pull_requests` and that the gate returns the current head SHA.
- [ ] Once the rule is enabled, record the CodeQL analysis categories and SHA for the first
  measured push to `refs/heads/release/<version>`. Expect all three categories on the pushed head.
- [ ] Close #303 only after the rule exists and step 8 runs successfully once
  on a real ship branch under the accepted procedure.
