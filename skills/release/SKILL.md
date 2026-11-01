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
- CI green on `main`: `gh run list --branch main --limit 3`, the `sonar` job included. The Sonar ratchet
  (`scripts/ci/sonar_ratchet.py`) fails on `main` when a merged PR fixed issues and `sonar-baseline.txt` was not
  lowered (0.3.0: 122 open against 123); lower it in a one-line PR before tagging, and tag the release merge commit
  explicitly if `main` moved (step 8).
- `/sharpit:known-issues`: no open Critical or High safety issue.
- `/sharpit:doc-review` clean: version references, links (github.com only) and the changelog footer.
- `/sharpit:live-verify` for each user-facing change in this release, or a line in the PR saying why not.
- `[Unreleased]` in `CHANGELOG.md` is non-empty and true.

**3. Announce, then cut the branch in its own worktree.**

```bash
python ~/.agents/skills/multi-agent-dev/scripts/agentctl.py status      # who else works on sharpit
git worktree add -b chore/release-<version> ../sharpit-release-<version> origin/main
cd ../sharpit-release-<version>
```

Tell every live sharpit agent: "Cutting v<version> from main@<sha>; hold merges to main until the tag is pushed."
A worktree keeps another session's `git switch` from moving the branch under you.

**4. Bump the version.** There is one declaration site: `__version__` in `src/sharpit/__init__.py` (hatch reads it;
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

**7. Commit, PR, merge.**

```bash
git add src/sharpit/__init__.py CHANGELOG.md     # plus any declaration from step 4
git commit -m "chore: release <version>"
git push -u origin chore/release-<version>
gh pr create --base main --title "chore: release <version>" --body "Release <version>. See CHANGELOG.md."
gh pr checks <N> --watch                          # background it
```

Run `/sharpit:llm-council --tier high` on the branch. All checks green and no council blocker, then merge with a **merge commit** (never squash) and remove the worktree:

```bash
gh pr merge <N> --merge --delete-branch
cd <main checkout> && git worktree remove ../sharpit-release-<version>
```

On Windows a held `.venv` can block the removal: merge without `--delete-branch`, run
`git push origin --delete chore/release-<version>`, and list the directory for manual deletion.

**8. Sign the tag on the merged `main`.**

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

**9. Point of no return: confirm with the owner, then push the tag.** Show the version, the commit and the signature
check, and wait for an explicit go-ahead in this session.

```bash
git push origin v<version>
```

**10. Watch the release run.**

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

**11. Report.** Version, PR, tag commit, the release run link, the GitHub Release link, the PyPI page
(<https://pypi.org/project/sharpit/>), and that the agents from step 3 may merge again.

## Never

- Never `uv publish` or `twine upload` from a laptop: the CI run is the record of what shipped.
- Never push or move a tag without the owner's go-ahead in this session.
- Never squash the release PR, never `--no-verify`, never add AI attribution to commits, PRs or tags.
- Never change `release.yml` in the same PR as a release.

Ported from gflow-cli's `release` skill and `release.yml`: same signed-tag gate, OIDC publish and Release step;
sharpit has one branch (`main`) and one version site, so the develop back-merge and the seven-site table are gone.
