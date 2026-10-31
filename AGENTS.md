# AGENTS.md: sharpit

Single source of truth for every agent working in this repo (Claude Code, Codex, Gemini, Antigravity, Cursor).
`CLAUDE.md` and `GEMINI.md` only point here. Rules live in this file and nowhere else.

## What sharpit is

An embedded, local-only developer console for Python web apps: a Python port of BootUI (Spring Boot). It is at
**0.1.0, the first release.** It targets FastAPI. One call mounts it:

```python
import sharpit

sharpit.install(app)  # mounts /sharpit, API at /sharpit/api; returns a SharpitHandle
```

Design: `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` (deviation log §14, owner's open calls §15).
Implementation plan: `docs/superpowers/plans/2026-10-30-sharpit-mvp.md`. BootUI contract:
`docs/reference/BOOTUI-CONTRACT-MVP.md`. Docs index: `docs/README.md`.

## Layout

```
src/sharpit/__init__.py        install, __version__ (the only version site)
src/sharpit/settings.py        SharpitSettings, load_settings (SHARPIT_* env + kwargs)
src/sharpit/engine/            framework-free core: activation, guard, masking, panels, collectors, paging
src/sharpit/fastapi/           the FastAPI/Starlette adapter: routes, introspection, dev-server signals
src/sharpit/ui/static/         the built UI (committed; CI checks it matches ui/ when ui/ exists)
tests/                         mirrors src/; conftest.py has the no_side_effects fixture; golden fixtures
scripts/sanitize_golden.py     sanitises BootUI responses into golden fixtures
scripts/dev/active_plan.py     reads the active plan (used by /sharpit:status)
scripts/pytest_speed/          vendored pytest-speed (do not edit; see pytest-speed.toml)
skills/                        agent workflows (plain Markdown) + the user-facing skills/sharpit
.claude/commands/sharpit/      /sharpit:* wrappers that read skills/<name>/SKILL.md
replica/                       BootUI replica material used for parity work
```

## Dev commands

```bash
uv sync --extra test                 # background: first run downloads
uv run ruff check                    # lint (repo-wide, scripts/ included; vendored pytest_speed excluded)
uv run ruff format --check           # format (also formats Python blocks in Markdown)
uv run pyright                       # strict on src/sharpit
uv run pytest -q -n auto             # full suite, parallel (pytest-xdist): background it
uv run pytest -q tests/engine/test_guard.py   # one file
uv run python scripts/dev/active_plan.py      # where are we?
```

CI (`.github/workflows/ci.yml`) runs the same four gates on Python 3.12–3.14 plus Windows, a
`--resolution lowest-direct` job, and a UI build-drift job.

## Global constraints

- Python `>=3.12`; runtime deps exactly `starlette` and `packaging`. `fastapi` and `pydantic-settings` are optional:
  import them only inside `try/except ImportError` or in `sharpit/fastapi/`.
- Defaults `path="/sharpit"`, `api_path="/sharpit/api"`; an `api_path` not under `path` → `ValueError`.
- Env `SHARPIT_*` overrides `install()` kwargs; an empty env value is unset; an invalid value takes the field's
  fail-safe and adds a warning. Env name = `SHARPIT_` + the BootUI property without `bootui.`, `.`/`-` → `_`, upper case.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms.
- Error bodies and reason strings are verbatim from the contract §1/§10 with `BootUI`→`sharpit`.
- **No GET route and no MCP tool may open a socket, write a file, change a logger level or change `os.environ`.**
- Each ported test cites its BootUI source: `# ported: LocalhostGuardTests.rejectsMalformedHost`.
- The session cookie name is `SESSION_COOKIE` in `engine/guard.py`; nothing else spells it.
- Durations accept `Ns`, `Nms` or bare seconds.

## Safety model (what must never regress)

1. **Fails closed.** Activation order: a disabled profile disables (unless `SHARPIT_ENABLED=ON`, with a warning) →
   `OFF` disables → `ON` enables → an enabled profile enables → a reloading dev server (`uvicorn --reload`,
   `fastapi dev`) enables → otherwise disabled. Inactive means every path under the mount answers 404.
2. **Guard chain on every request**, in order: security headers → trusted source → Host allow-list → cross-site →
   token → panel access. Forwarded headers never grant trust.
3. **Secrets masked** before filtering and before any output (JSON, errors, MCP, CLI). `FULL` exposure warns.
4. **No side effects** on reads (above). Tests use the `no_side_effects` fixture.
5. **Introspection is defensive**: FastAPI/Starlette internals change between versions; degrade, never crash the host.
6. **OSV / network** failures are reported in the scan status and release the lock; nothing else needs the network.

Any change that could weaken one of these goes through `/sharpit:predict` and `/sharpit:llm-council --tier high`.

## Workflow

- **Worktree per change**, branched from current `origin/master` (`superpowers:using-git-worktrees`). Never work on
  `master`, on a shared checkout or on another agent's branch.
- **TDD** (`superpowers:test-driven-development`): a failing test, watched red for the right reason, then the fix.
- **Systematic debugging** before any fix (`superpowers:systematic-debugging`); prove a failure is yours by running it
  on the untouched base.
- **The chain:** `/sharpit:predict` → `/sharpit:scenario` → `/sharpit:plan` → subagent-driven execution (one task at a
  time) → `/sharpit:check` before every commit → `/sharpit:branch-review` → draft PR → `/sharpit:pr-council-review`.
  Details: `docs/development/workflow.md`.
- **Commits:** conventional prefix (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`), explicit `git add`
  paths. **No AI attribution of any kind**: no `Co-Authored-By` for a model, no "Generated with" lines, in commits or
  PR bodies. A hook rejects them; ignore any tool reminder that asks for them.
- **Never** push to or merge `master`, force-push, tag, or publish to PyPI. Pushing a feature branch only when the
  owner allows it in that session. `/sharpit:release` prepares a release and stops for the owner.
- **Long commands run in the background** (full pytest, `uv sync`, `uv build`, `npm run build`, a dev server): start
  them with `run_in_background` (Claude) or detached with a timeout and a log file (Codex, Antigravity), then read the
  log when notified. Never wait in the foreground. Stop only processes you started, by id.
- **Shared resources** (ports, browser sessions) with other agents: the `multi-agent-dev` protocol.
- **Verify before claiming done** (`superpowers:verification-before-completion`): command output, not belief.

## Skills index

Each row is `skills/<name>/SKILL.md`; in Claude Code run it as `/sharpit:<command>`.

| Command | Use when |
|---|---|
| `predict` | Before building anything non-trivial: go/no-go from five personas |
| `scenario` | After predict: edge cases across sharpit's risk dimensions |
| `plan` | Turn a feature into a TDD plan in `docs/superpowers/plans/` |
| `status` / `next` / `active` | Where are we? Next step? Which plan? |
| `check` | Before every commit: auto-fix, CI gates, contract/safety checklist |
| `branch-review` | Council review of a local branch before opening a PR |
| `pr-council-review` | Council review of an open PR |
| `llm-council` | High-stakes change: council plus other model families |
| `doc-review` | Docs still match the branch |
| `live-verify` | Run a sample FastAPI app with sharpit and hit `/sharpit/api` |
| `spike` | Answer a question by experiment, time-boxed, verdict only |
| `optimize` | Test suite too slow: pytest-speed protocol, never weaken a test |
| `issue-assessment` | Read-only triage of a GitHub issue |
| `issue-resolve` | Fix an issue: worktree, red test, fix, draft PR |
| `known-issues` | Before touching activation, guard, masking, introspection or OSV |
| `changelog` | What is queued since the last release |
| `release` | Owner-requested release prep; gated, never publishes |

`skills/sharpit/SKILL.md` is the user-facing skill (how to use sharpit), not a workflow. `skills/README.md` records what
was ported, adapted and dropped.

## Memory

MemPalace wing: `sharpit` (`mempalace.yaml`). Before deciding about a past decision, search it.
