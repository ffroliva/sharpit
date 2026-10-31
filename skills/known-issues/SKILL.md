---
name: known-issues
version: "1.0"
description: >
  Use before touching sharpit's activation, guard chain, masking, introspection or the OSV scan, or when something
  feels unexpectedly broken: surfaces open known issues and the logged deviations from BootUI.
---

# `known-issues`: open issues and logged deviations

1. `KNOWN_ISSUES.md`, if it exists: return entries whose status is **open** or **mitigated**.
2. Open GitHub issues: `gh issue list --state open --limit 50` (skip if `gh` is unauthenticated, and say so).
3. The design spec `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md`: §14 (deviation log) and §15
   (coordinator's calls waiting on the owner). These are the known, deliberate differences from BootUI, e.g. the
   cross-site check applied to every method, programmatic `uvicorn.run(reload=True)` not detected.
4. Flag every item relevant to the current task.

If `KNOWN_ISSUES.md` does not exist, say so and offer to bootstrap it (one entry per issue:
`status: open | mitigated | fixed`, since date, affected surface, workaround). Do not create it unasked.

Ported from gflow-cli's `known-issues` skill; sources extended to the spec's deviation log.
