---
name: check
version: "1.0"
description: >
  Use before every sharpit commit: auto-fixes lint and format, then runs the exact CI gate (ruff check, ruff format
  --check, pyright strict, pytest) and walks the contract/safety checklist for what the change touched.
---

# `check`: quality gates

Mirrors `.github/workflows/ci.yml` in the same order. Stop and report when a step still fails after the fix pass.

## 1. Auto-fix (rewrites files)

```bash
uv run ruff check --fix
uv run ruff format
```

List the files it changed. Those rewrites are part of your change: stage them.

## 2. The CI gate (non-mutating, repo-wide, never narrowed to "my files")

```bash
uv run ruff check
uv run ruff format --check
uv run pyright                 # strict on src/sharpit
uv run pytest -q -n auto       # parallel; background it: run_in_background, then read the log when notified
```

If `.venv` is missing, `uv sync --extra test` first (in the background). CI also runs Python 3.12–3.14, a Windows job
and a `--resolution lowest-direct` job; a change that touches dependency floors or version-specific APIs should be
checked with `uv sync --extra test --resolution lowest-direct` too.

When `ui/` changed: `cd ui && npm ci && npm run build`, then `git diff --exit-code src/sharpit/ui/static`
(the built UI is committed; CI fails on drift).

## 3. Contract and safety checklist

Tick each row or write "N/A: <why>". Silence is not an answer.

| If the change touches… | Confirm |
|---|---|
| A JSON response | Every DTO key emitted (nulls included), camelCase, epoch ms, no envelope; a golden fixture or contract § asserts it |
| An error or reason string | Verbatim from contract §1/§10 with `BootUI`→`sharpit`, `bootui.<prop>`→`SHARPIT_<PROP>` |
| A setting | Env name follows `SHARPIT_` + property (`.`/`-`→`_`); env overrides kwarg; empty = unset; invalid → fail-safe + warning |
| A GET route or MCP tool | A test using the `no_side_effects` fixture (no socket, no file, no logger level, no environ change) |
| Any new output surface | Masking applied before filtering; the secret corpus test covers it |
| Activation or the guard | Fails closed; guard order unchanged; forwarded headers never grant trust |
| A ported BootUI test | `# ported: <Class>.<case>` comment |
| Dependencies | Runtime deps still exactly `starlette` and `packaging`; optional imports inside `try/except ImportError` |
| A deviation from BootUI | Logged in the design spec §14 |
| User-facing behaviour | README and `skills/sharpit/SKILL.md` still true |
| Agent workflow files | `tests/test_agent_workflow.py` passes |

## Output

Files changed by the fix pass; the checklist; ruff and format results; every pyright error as `file:line`; the pytest
summary line; a final verdict naming any failed gate.

## Next step

On a local feature branch: "Gates passed. Next: `/sharpit:branch-review`." With an open PR:
"`/sharpit:pr-council-review <N>`". If an endpoint or the UI changed, `/sharpit:live-verify` before claiming done.

Pyright errors and test failures need a real fix: never a `# type: ignore`, `skip` or loosened assertion to get green.

Ported from gflow-cli's `check` skill; gates replaced with sharpit's CI and contract checklist.
