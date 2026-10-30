---
name: release
version: "1.0"
description: >
  Use when the owner asks to prepare a sharpit release: version bump, changelog, build sanity check, release branch.
  Gated: it never publishes to PyPI, never tags or pushes master, and stops for the owner before anything public.
---

# `release`: gated release preparation

> **Hard gate.** Never run `uv publish`, `twine upload`, `git push` to `master`, `git tag` pushes or `gh release create`
> unless the owner has given an explicit instruction **in this session** naming the version. "Prepare a release" is
> not that instruction. When in doubt, stop and print the commands for the owner.

## 1. Preconditions

- On an up-to-date `master` checkout with a clean tree (`git status --porcelain` empty), or stop.
- `/sharpit:status`: the plan the release covers has no open steps, or the owner accepts what is open.
- `/sharpit:check` green on that commit; CI green on `master` (`gh run list --branch master --limit 3`).
- `/sharpit:known-issues`: no open Critical/High safety issue.

## 2. Version

The single version site is `__version__` in `src/sharpit/__init__.py` (hatch reads it). Follow PEP 440: the MVP is
`0.1.0.dev0`; the first public build is `0.1.0` (or `0.1.0rc1` for a candidate). Ask the owner for the number if not
given.

## 3. Release branch

```bash
git switch -c chore/release-<version>
# edit src/sharpit/__init__.py
```

## 4. Changelog

Run `/sharpit:changelog`. If `CHANGELOG.md` exists, move `[Unreleased]` under `## [<version>] - <YYYY-MM-DD>` and open
a fresh `[Unreleased]`. If it does not, create it now from the grouped git log (a release is the moment to bootstrap
it).

## 5. Build sanity check (local only)

```bash
uv build                                           # background it
uv run --isolated --with dist/sharpit-<version>-py3-none-any.whl python -c "import sharpit; print(sharpit.__version__)"
```

Check the wheel contains `sharpit/ui/static/` and no `tests/`, `scripts/`, `replica/` or `.sharpit/`
(`python -m zipfile -l dist/*.whl`). Do not commit `dist/`.

## 6. Commit and review

```bash
git add src/sharpit/__init__.py CHANGELOG.md
git commit -m "chore: release <version>"
```

Run `/sharpit:llm-council --tier high` on the release branch. No AI attribution anywhere.

## 7. STOP: hand over to the owner

Print, do not run:

```bash
git push -u origin chore/release-<version>
gh pr create --base master --title "chore: release <version>"
# after merge, on master:
git tag v<version> && git push origin v<version>
uv publish                                         # needs the owner's PyPI token
```

Report: version, branch, commit, build check result, council verdict, and the commands above.

Ported from gflow-cli's `release`; reduced to one version site and gated before any publish.
