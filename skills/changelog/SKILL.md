---
name: changelog
version: "1.0"
description: >
  Use to see what sharpit has queued since its last release and what the last tag shipped: before a release, or when
  deciding whether a change is user-visible enough to record.
---

# `changelog`: recent changes

1. If `CHANGELOG.md` exists (Keep a Changelog format), return everything under `## [Unreleased]` and the most recent
   versioned section.
2. If it does not exist (true for the pre-release MVP), fall back to git:
   ```bash
   git describe --tags --abbrev=0 2>/dev/null || echo "no tag yet"
   git log --oneline <last-tag-or-root>..HEAD
   ```
   Group the conventional-commit subjects: `feat:` → Added, `fix:` → Fixed, everything else → Changed/Internal. Offer
   to bootstrap `CHANGELOG.md` with an `[Unreleased]` section from that grouping; do not create it unasked.
3. One line: "N features, M fixes queued since <tag or 'the start'>."

Called first by `/sharpit:release`.

Ported from gflow-cli's `changelog` skill, with a git fallback because sharpit has no CHANGELOG.md yet.
