# sharpit docs

| Path | What it is |
|---|---|
| [../website/docs/how-it-works.md](../website/docs/how-it-works.md) | How sharpit works; published with the rest of the user docs at https://ffroliva.github.io/sharpit/ |
| [development/workflow.md](development/workflow.md) | How a change goes from idea to release with the `/sharpit:*` skills |
| [development/ci.md](development/ci.md) | Every CI job, what it guards, and the exact command to run it locally |
| [development/overhead-budgets.md](development/overhead-budgets.md) | How the overhead budget tests measure and how to read a failure |
| [reference/BOOTUI-CONTRACT-MVP.md](reference/BOOTUI-CONTRACT-MVP.md) | The BootUI HTTP contract the MVP must match: DTOs, error strings, activation reasons |
| [reference/BOOTUI-PYTHON-MAPPING.md](reference/BOOTUI-PYTHON-MAPPING.md) | How BootUI's Spring concepts map to Python/FastAPI |
| [superpowers/specs/2026-10-30-sharpit-mvp-design.md](superpowers/specs/2026-10-30-sharpit-mvp-design.md) | MVP design spec; §14 deviation log, §15 coordinator's calls for the owner |
| [superpowers/specs/council/](superpowers/specs/council/) | Spec reviews by Claude, Codex and Gemini, and the round-1 synthesis |
| [superpowers/plans/2026-10-30-sharpit-mvp.md](superpowers/plans/2026-10-30-sharpit-mvp.md) | MVP implementation plan: Global Constraints, Review Focus, tasks |
| [superpowers/plans/council/](superpowers/plans/council/) | Plan reviews by Claude, Codex and Gemini, and the round-2 synthesis |

Elsewhere: [AGENTS.md](../AGENTS.md) (rules for every agent), [skills/README.md](../skills/README.md) (the workflow
skills), [skills/sharpit/SKILL.md](../skills/sharpit/SKILL.md) (how to use sharpit), [.claude/README.md](../.claude/README.md)
(the `/sharpit:*` command wrappers).

New plans go in `superpowers/plans/<YYYY-MM-DD>-<slug>.md`, their scenario notes beside them as `<...>-scenario.md`,
and spike verdicts in `superpowers/spikes/<YYYY-MM-DD>-<slug>.md`.
