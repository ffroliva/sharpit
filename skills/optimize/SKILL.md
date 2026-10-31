---
name: optimize
version: "1.0"
description: >
  Use when sharpit's test suite or one test file is too slow, when the pytest-speed check flags a file, or when asked
  to make tests faster. A thin pointer: the protocol is the standalone pytest-speed skill, run against sharpit's config.
---

# `optimize`: make sharpit's tests faster without weakening them

This skill does not restate the protocol. **Read the pytest-speed skill and follow it end to end:**
`~/.agents/skills/pytest-speed/SKILL.md` (developed in `ffroliva/pytest-speed`; read-only here). Its cause catalogue
is `causes.md` next to it.

## sharpit's wiring

| Key | Value |
|---|---|
| Config (`<cfg>`) | `pytest-speed.toml` at the repo root |
| Module (`<module>`) | `scripts.pytest_speed` (vendored verbatim; `scripts/pytest_speed/VERSION` holds the source commit and tree hash) |
| Run (`<run>`) | `uv run pytest` |
| Baseline | `tests/test_durations.json` (+ `tests/test_durations.meta.json`) |
| Exceptions | `tests/pytest_speed_exceptions.json`; only `approved_by: "ffroliva"` counts |
| Mode | `block = false`: the check reports, it never fails the build |

So `python -m <module> ...` is `uv run python -m scripts.pytest_speed ...` from the repo root, e.g.

```bash
uv run pytest -q --junitxml=speed/report.xml                       # background: it is the full suite
uv run python -m scripts.pytest_speed rank speed --root .
uv run python -m scripts.pytest_speed check speed --config pytest-speed.toml --out speed.md
```

The gating run is CI's Linux job (`.github/workflows/ci.yml`); a local Windows run is for finding causes, not for
ranking. CI does not yet upload JUnit artifacts, so until it does, rank a local full run and say which OS it came from.

## The never-weaken rule (summary; the pytest-speed skill is authoritative)

A speed change never skips, deselects, `xfail`s or marks a test slow; never loosens an assertion or shrinks its data;
never raises a timeout to hide a wait; never adds an exception or refreshes the baseline to silence a flag; never
shards, splits or rebalances as "the fix". Every fix has a red test that pins the cost (a call or rebuild count, never
a wall-clock threshold). sharpit-specific: the `no_side_effects` fixture and the golden-fixture checks are assertions;
making them cheaper is fine, removing or narrowing them is weakening.

Refreshing the baseline (`refresh --source ci|fleet --commit <sha>`) and editing the exceptions file are owner
decisions, never part of a speed fix. Re-vendoring is `python -m pytest_speed vendor <sharpit>/scripts/pytest_speed`
run from a clean pytest-speed checkout; never hand-edit the vendored files.

pytest-speed checkout: `~/.agents/skills/pytest-speed` (repo `ffroliva/pytest-speed`).
