---
name: release
version: "2.0"
description: >
  Use when the owner asks to cut a sharpit release: version bump, changelog, release PR, signed tag. Publishing is
  CI's job: pushing the signed tag runs .github/workflows/release.yml (PyPI Trusted Publishing + GitHub Release).
  Never `uv publish` by hand.
---

# `/sharpit:release` — cut a release

Follow this sequence in order. Ask the owner for anything under **Inputs** that was not given.

> **How publishing works.** Nobody uploads to PyPI by hand. A signed tag `v<version>` pushed to GitHub starts
> `.github/workflows/release.yml`, which checks the signature, builds, checks the wheel version matches the tag,
> smoke-tests the wheel, publishes to PyPI through Trusted Publishing (OIDC, no token anywhere) and creates the GitHub
> Release with the wheel and sdist. The tag push is therefore the **point of no return**.

## Inputs

1. **Version**, PEP 440: `0.2.0`, `0.2.0rc1`, `0.2.0a1`. Patch for fixes only, minor for features, major for breaks.
   Run `/sharpit:changelog` first if the owner wants a proposal.
2. **Pre-release?** `a`, `b`, `rc` and `dev` versions become GitHub pre-releases automatically. Only the owner says
   when a line is ready for a stable tag.

## One-time setup (already done unless the first run fails)

- PyPI: <https://pypi.org/manage/project/sharpit/settings/publishing/>, add a GitHub publisher with owner `ffroliva`,
  repository `sharpit`, workflow `release.yml`, environment `pypi`. Only the owner can do this (PyPI login).
- GitHub: the `pypi` environment exists (`gh api repos/ffroliva/sharpit/environments --jq '.environments[].name'`).
- Signing: `git config --global gpg.format` is `ssh` and `user.signingkey` points at the key registered on GitHub.

## Sequence

**1. Clean, current `main`.** In the main checkout: `git status --porcelain` is empty, `git fetch origin` and
`git rev-list --count HEAD..origin/main` is `0`. Stray build output (`dist/`) is deleted; real uncommitted work
stops the release until the owner decides where it goes.

**2. Gates.** All must pass; stop and report if one fails.

- `/sharpit:check` green.
- CI green on `main`: `gh run list --branch main --limit 3`, the `sonar` job included. The code-scan ratchet
  (`scripts/ci/sonar_ratchet.py`) fails every pull request while `main` has fewer open issues than
  `sonar-baseline.txt`; lower it in the release PR or a one-line PR before tagging, and tag the release merge commit
  explicitly if `main` moved (step 10).
- `/sharpit:known-issues`: no open Critical or High safety issue.
- `/sharpit:doc-review` clean: version references, links (github.com only) and the changelog footer.
- `/sharpit:live-verify` for each user-facing change in this release, or a line in the PR saying why not.
- `[Unreleased]` in `CHANGELOG.md` is non-empty and true.
- A coordinated (multi-lane) release reached `main` with its decisions harvested into
  `docs/reports/<date>-<version>-decisions.md` and no tracked `.superpowers/` files
  (`python scripts/ci/no_superpowers.py` exits 0; `docs/development/workflow.md` step 7).

**3. Hold merges to main and cut the release worktree.** Set `version` to the release version. Announce the
release and hold merges to `main` until the tag is pushed. After fetching, choose the existing version branch
as the starting point when present.

```bash
python ~/.agents/skills/multi-agent-dev/scripts/agentctl.py status
git fetch --prune origin
start=origin/main
if git show-ref --verify --quiet "refs/remotes/origin/release/$version"; then
  start="origin/release/$version"
fi
git worktree add -b "chore/release-$version" "../sharpit-release-$version" "$start"
cd "../sharpit-release-$version"
```

**4. Bump the version.** `tests/test_packaging.py::test_version_is_<x>` pins it by name and value: update both, or the suite
fails. There is one source: `__version__` in `src/sharpit/__init__.py` (hatch reads it; the two manifests under `plugins/sharpit/` carry a copy the Agent Plugins schema requires, and `tests/test_agent_plugin.py::test_manifest_version_matches_the_package` fails until you update it;
`uv.lock` carries no version for the editable package). Then
`git grep -n "<old version>" -- ':!CHANGELOG.md'` and update only *declarations* that name the current release
(for example "the current release is …" in `AGENTS.md` or `skills/sharpit/SKILL.md`). Leave records of what was
measured or shipped alone.

**5. Changelog.** Move everything under `## [Unreleased]` into `## [<version>] - <YYYY-MM-DD>`, leave `[Unreleased]`
empty, and add the footer link in the existing form:

```
[<version>]: https://github.com/ffroliva/sharpit/releases/tag/v<version>
```

**6. Local build check.**

```bash
uv build --out-dir "$TEMP/sharpit-dist"                                      # background it
python -m zipfile -l "$TEMP"/sharpit-dist/sharpit-<version>-py3-none-any.whl  # has sharpit/ui/static/, no tests/ scripts/ replica/
```

The file name must carry `<version>`; CI refuses the tag otherwise. Do not commit `dist/`.

**7. Commit and push the release changes.** Include each updated declaration from step 4. Set `body_file` to
the path of a file containing the release PR description.

```bash
git add src/sharpit/__init__.py plugins/sharpit/plugin.json plugins/sharpit/.claude-plugin/plugin.json tests/test_packaging.py CHANGELOG.md
git commit -s -m "chore: release $version"
git push -u origin "chore/release-$version"
```

For a release cut from `origin/main`, continue to step 8. For one cut from `origin/release/$version`, stage the
changes on the version branch first. Record the pushed SHA and new PR URL.

```bash
STAGING_SHA=$(git rev-parse "chore/release-$version") &&
STAGING_PR=$(gh pr create --base "release/$version" --head "chore/release-$version" --title "Stage release $version" --body-file "$body_file")
```

**Shared staging merge.** For initial staging, fixes and retries, use the recorded URL, pushed SHA and release
version. If checks are pending or absent, wait and rerun this block for the same PR.

```bash
: "${STAGING_PR:?}" "${STAGING_SHA:?}" "${version:?}" &&
gh pr checks "$STAGING_PR" --watch &&
test "$(gh pr view "$STAGING_PR" --json baseRefName --jq .baseRefName)" = "release/$version" &&
gh pr merge "$STAGING_PR" --merge --match-head-commit "$STAGING_SHA"
```

**8. Scan the draft release PR into main.** Fetch before synchronizing the ship head.

```bash
git fetch origin
```

For the direct path, update and push the chore branch.

```bash
git switch "chore/release-$version" &&
git merge --no-edit origin/main &&
git push origin "chore/release-$version"
```

For the version-branch path, check `git merge-base --is-ancestor origin/main "origin/release/$version"`.
If the version branch lacks the current main commit or needs a fix, start a fresh staging branch from the
current version branch. Set `stage` to an unused branch name. Create the branch before applying and committing
any fix, then merge main and push it.

```bash
git switch -c "$stage" "origin/release/$version"
```

After committing any fix, stage the updated head.

```bash
git merge --no-edit origin/main &&
git push -u origin "$stage" &&
STAGING_SHA=$(git rev-parse "$stage") &&
STAGING_PR=$(gh pr create --base "release/$version" --head "$stage" --title "Update release $version" --body-file "$body_file")
```

Run the shared staging merge in step 7 with this PR URL and pushed SHA.
After its successful merge, clean up the temporary staging branch from the merged version-branch commit.

```bash
git fetch origin &&
git switch --detach "origin/release/$version" &&
git merge-base --is-ancestor "$stage" HEAD &&
git push origin --delete "$stage" &&
git branch -d "$stage"
```

For either path, look up the PR after updating the ship head. Set `ship` to `chore/release-$version` or
`release/$version` for the chosen path. Reuse only a PR opened against main with that head. If its base ever changed, close the PR and open a new draft against main.

```bash
gh pr list --state open --base main --head "$ship" --json number,isDraft
```

Reuse the matching draft. If the matching PR is ready, set `N` to its number and run `gh pr ready "$N" --undo`.
If the lookup finds no PR, use the create command for the chosen path.

Direct path:

```bash
gh pr create --draft --base main --head "chore/release-$version" --title "Release $version" --body-file "$body_file"
```

Version-branch path:

```bash
gh pr create --draft --base main --head "release/$version" --title "Release $version" --body-file "$body_file"
```

For either path, set `N` to the draft PR number. Wait for all checks to pass and verify CodeQL and the code-scan ratchet on the draft.

```bash
gh pr checks "${N:?}" --watch &&
uv run python scripts/ci/ship_scan.py "$N"
```

**9. Review the scanned draft and merge.** Review the exact draft head with `/sharpit:llm-council --tier high`.
Record the reviewed SHA as `COUNCIL_SHA`. Resolve any council blocker through the applicable path in step 8.
After council approval, run this block in one Bash shell. Keep the verified SHAs for the merge.

```bash
gh pr checks "${N:?}" --watch &&
gate=$(uv run python scripts/ci/ship_scan.py "$N") &&
[[ $gate =~ ^Verified\ head\ ([0-9a-f]{40})\ and\ base\ ([0-9a-f]{40})$ ]] &&
VERIFIED_SHA=${BASH_REMATCH[1]} && VERIFIED_BASE=${BASH_REMATCH[2]} &&
test "${COUNCIL_SHA:?}" = "${VERIFIED_SHA:?}" &&
printf '%s\n' "$gate" &&
gh pr ready "${N:?}"
```

Shell variables do not persist between separate shell calls. In the shell running the following block,
set `N`, `version`, `main_checkout`, and the recorded `VERIFIED_SHA` and `VERIFIED_BASE`. The merge pins the
head. Keep the step 3 hold on main through the interval following the live base check.

```bash
gh pr checks "$N" &&
test "$(gh pr view "$N" --json headRefOid --jq .headRefOid)" = "${VERIFIED_SHA:?}" &&
test "$(gh pr view "$N" --json baseRefName --jq .baseRefName)" = main &&
test "$(gh api repos/ffroliva/sharpit/git/ref/heads/main --jq .object.sha)" = "${VERIFIED_BASE:?}" &&
gh pr merge "$N" --merge --match-head-commit "${VERIFIED_SHA:?}" && {
  git push origin --delete "chore/release-$version"
  cd "$main_checkout" && git worktree remove "../sharpit-release-$version"
}
```

On Windows a held `.venv` can block worktree removal. Record the directory for manual deletion.
If the head, base branch or base SHA changes before merge, return the PR to draft and repeat step 8, council,
gate and checks.

```bash
gh pr ready "$N" --undo
```

**10. Sign the tag on the merged `main`.**

```bash
git switch main && git pull --ff-only
git log --oneline -1                              # the merge of the release PR, nothing newer
git tag -s v<version> -m "v<version>"
git cat-file -p v<version> | grep -cE "BEGIN (SSH|PGP) SIGNATURE"   # expect 1
```

If `main` moved past the release merge, those commits are not in the changelog section: move their entries under
`[<version>]` in a follow-up PR first, or tag the release merge commit explicitly (`git tag -s v<version> <sha>`).
`git tag -v` failing with `gpg.ssh.allowedSignersFile needs to be configured` is a local verify setting only; the tag is
signed and CI accepts it.

**11. Point of no return: confirm with the owner, then push the tag.** Show the version, the commit and the signature
check, and wait for an explicit go-ahead in this session.

```bash
git push origin v<version>
```

**12. Watch the release run.**

```bash
gh run list --workflow release.yml --limit 1
gh run watch <run id> --exit-status               # background it
gh release view v<version>
python -m pip index versions sharpit              # the new version is listed
```

On failure, read the log (`gh run view <run id> --log-failed`):

| Failed step | Meaning | Fix |
|---|---|---|
| Verify the tag is signed | lightweight or unsigned tag | delete it (`git push origin :refs/tags/v<version>`, `git tag -d`), re-sign, re-push |
| Verify the tag matches the built version | step 4 missed or a typo in the tag | same: delete, fix, re-tag |
| pypi-publish: `invalid-publisher` | Trusted Publishing not set up or a field differs | owner fixes the PyPI publisher (one-time setup), then `gh run rerun <run id>` |
| pypi-publish: file already exists | the version is already on PyPI | ship the next patch version |

Deleting and re-pushing a tag is safe **only if PyPI never received that version**. Once it is on PyPI the tag is
permanent: fix forward with a patch release.

**13. Report.** Version, PR, tag commit, the release run link, the GitHub Release link, the PyPI page
(<https://pypi.org/project/sharpit/>), and that the agents from step 3 may merge again.

## Never

- Never `uv publish` or `twine upload` from a laptop: the CI run is the record of what shipped.
- Never push or move a tag without the owner's go-ahead in this session.
- Never squash the release PR, never `--no-verify`, never add AI attribution to commits, PRs or tags.
- Never change `release.yml` in the same PR as a release.

Ported from gflow-cli's `release` skill and `release.yml`: same signed-tag gate, OIDC publish and Release step;
sharpit tags releases on `main` and has one version site, so the develop back-merge and the seven-site table are gone.
