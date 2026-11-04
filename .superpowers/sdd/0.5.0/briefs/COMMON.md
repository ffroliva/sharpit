# Common rules for every sharpit 0.4.0 lane worker (read in full)

You are one of several AI agents implementing sharpit 0.4.0 tonight, each in its own git worktree, coordinated by a
Claude Code session (agentctl id `claude-sharpit`). The owner is asleep. Nobody answers questions: decide from the
spec and your lane plan, write the decision in your `handoff.md`, and keep going.

## Where you work

- ONLY in your lane worktree `C:\development\github\sharpit-wt\0.4.0-<LANE>`, branch `lane/0.4.0-<LANE>`. Never cd
  to `C:\development\github\sharpit` (main checkout), `...\0.4.0-integration` or another lane's worktree. Never
  switch branches. No `git stash` (stash is shared across worktrees): use WIP commits.
- Never push, open PRs, merge, rebase onto anything, tag or publish. Commit locally; the coordinator reviews and
  merges through `scripts/dev/lane_gate.py`.
- Touch ONLY the files your lane plan's **May touch** list allows. Other lanes run in parallel on other files.
- Never edit `.superpowers/sdd/0.4.0/lanes/*/review.md` or anything under `.superpowers/sdd/0.4.0/lanes/*/gate/`
  (the gate refuses the merge).
- Do not start dev servers or bind ports 5432 6379 9092 8080 80 443 8000 (the coordinator and the reference stack
  hold them). Tests use in-process clients and SQLite unless your plan says otherwise.
- Register: `python C:/Users/ffrol/.agents/skills/multi-agent-dev/scripts/agentctl.py join --title "<harness> 0.4.0-<LANE>" --role "lane <LANE>"`;
  run `... leave` when done.

## Read first (mandatory, in order)

1. `AGENTS.md` in your worktree (repo rules: TDD, architecture rules, safety model, no AI attribution).
2. `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` (r5) — the sections your lane plan cites, plus §4
   anti-goals, §6.1 definition of done, §10.3.
3. `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/PLAN.md` — Global Constraints and Review Focus.
4. Your lane plan `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/<LANE PLAN>.md`, then
   `council-r1-fixes.md`, `council-r2-fixes.md`, `council-r3-fixes.md` in that folder (they amend lane plans; where a
   lane plan disagrees with them or with PLAN.md, the council files and PLAN.md win).
5. After F merges: F's interface table (in F's handoff / `docs/superpowers/plans/.../F-foundation.md`) for every
   symbol you consume. Verify every symbol against the real code before using it; adapt the call, never the assertion.

## How you work

- TDD, one task at a time. Each task's red is a **red commit**: the failing tests plus minimal importable stubs that
  return a WRONG value (never `NotImplementedError`, never an ImportError), commit subject starting `test:`. The red
  must be an `AssertionError` that names the defect. Record each red test name + red SHA in
  `.superpowers/sdd/0.4.0/lanes/<LANE>/findings.md` and `handoff.md` (table: `test id | red SHA | assertion message`).
  `lane_gate.py` replays every named red test at its red SHA and refuses fakes, errors and passes. Never edit a red
  test's body after its red commit (the gate checks it).
- Then the fix commit (`feat:`/`fix:`/`refactor:`), test green.
- One condition per assert. Ported tests cite `# ported: <BootUI class>.<method>`. Never weaken, skip or delete an
  existing test; never raise a budget or a ratchet number.
- Commits: conventional prefix, explicit `git add <paths>` (never `git add -A`/`.`), **NO AI attribution of any
  kind** (no Co-Authored-By, no "Generated with"); a hook rejects them.
- Evidence (in your worktree, committed): `.superpowers/sdd/0.4.0/lanes/<LANE>/handoff.md`, `findings.md`,
  `field-map.md` (`N/A — not a panel lane` if not a panel), `checklist.md` (spec §6.1's ten items in order, each with
  an evidence path or `N/A` + reason). Note: `.superpowers/` is gitignored — add these files with `git add -f`.
- `handoff.md` is kept current after EVERY task: done / next step / decisions / red SHAs / how to resume. If you
  stop for any reason, another agent resumes from it.
- **Commit WIP on any exit, error or usage limit** (`chore: WIP <lane> <task>`), and update handoff.md first.
- Do not stop until your final report. Keep working while a background run goes.

## Commands (run from your worktree)

**On this machine every `uv` command needs `UV_LINK_MODE=copy`** (export it first; otherwise hardlink error 1142).
Put pytest logs OUTSIDE your worktree (e.g. `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\<LANE>-pytest.log`):
the `no_side_effects` fixture scans the cwd and fails on files written inside it.

```bash
uv sync --extra test                         # first time; slow → background
uv run ruff check && uv run ruff format --check
uv run pyright
LOG=C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/<LANE>-pytest.log
timeout 900 uv run pytest -q -n 4 > $LOG 2>&1 &   # full suite, detached
tail -5 $LOG                                       # poll until summary
uv run pytest -q tests/path/test_x.py        # one file is fine in the foreground
```

Anything that can take more than ~8 seconds runs detached with a `timeout` and a log, then you poll the log. Never
more than `-n 4`. Never run `npm run build` (only `npm --prefix ui run check` and vitest, if your lane has UI).
Stop only processes you started, by PID.

## Final report (last message, under 300 words)

Status (DONE / DONE_WITH_CONCERNS / BLOCKED), commit SHAs (red and fix per task), the four gates' results with
counts, deviations and why, anything left for another lane. The same content goes in `handoff.md`.

## Benchmark integrity (sharpit-bench, owner-approved)

Never read, list or ask for anything under `C:\development\github\sharpit-bench-spike\cases-heldout\` (held-out
benchmark cases; a sharpit result only counts if sharpit never saw them).

## Evidence format the merge gate enforces (learned on lanes F–D1, 02:00)

- `handoff.md` has a line `Implementer: <harness/model>`.
- `checklist.md`: spec §6.1 items 1–10, each row's Evidence cell names a file that exists at your head (a backticked
  repo path) or `N/A — <non-empty reason>`. Item 8 may say `N/A — coordinator gate logs`.
- Only REAL red tables have a column headed `Red SHA`: rows are `| tests/<path>.py::<test> | <40-char SHA> | <assertion> |`.
  Superseded reds go in a separate table headed `Historical SHA`; UI/vitest reds in a table headed `Commit`.
- A red test must be one your lane adds or changes; after its red commit never change the test function, its
  decorators, or any top-level name/fixture it references (add NEW tests instead, and supersede the old row).
- A red assertion may fail in the test file or a shared test helper, never inside `src/`; `pytest.raises` reds are fine.
- Do not edit pyproject tool config, tests/conftest.py, tests/test_code_shape.py, tests/overhead.py or existing
  overhead-budget lines.

## Safety-matrix rows (after F-rest, 03:25)

Add `tests/safety/test_<lane_id>_safety.py` (lower case, `_`): export `PANEL = "<sharpit panel id>"`,
`GET_ROWS = ["/sharpit/api/<id>", ...]` (every GET route path format, `{param}` placeholders) and
`WRITE_ROWS = [("POST", "/sharpit/api/<id>/..."), ...]`. The shared route-table tests include them only while your
panels04 flag is true — never edit tests/test_safety_matrix.py. New path params need a sample value in
`tests/conftest.py::_PATH_PARAMS` (the one conftest edit allowed; say so in handoff.md). Rebuild the tool catalogue in
tests only via `surface.catalogue_with_lanes(*panels04.tool_definitions())`.
- `findings.md`: the red table has a `Disposition` column, each row `Fixed in <sha>` or `Parked: <reason>`
  (the gate refuses a findings.md without it).

## Crash reds are not reds (owner, 2026-11-02)

A red that fails with TypeError/AttributeError/ImportError, or passes, proves nothing. Before every `test:` commit,
check each new red fails by an AssertionError raised in the test file (once `scripts/dev/red_check.py` exists, run
it on the red tests and commit only on all-RED). A stub returns a WRONG VALUE of the right type — never raises, never
has a wrong signature. The coordinator never accepts crash reds by ruling: the lane re-reds them.

## Evidence tables the lane gate parses (added 2026-11-03 after three lanes tripped it)

- A table with a `Disposition` column is a findings table: it MUST also have `Test` (full `path.py::name`) and
  `Red SHA` (full 40-char SHA of the commit where that test went red) columns, one test per row. Disposition starts with
  `Fixed in <sha>` or `Parked: <reason>`; a `fixed` row with an empty Test cell counts as unresolved.
- A table that is not a red/findings table (a list of review fixes, a module map, gates) must not use the header
  `Disposition`: use `Resolution` or `Status`.
- UI (vitest) reds go in a table under a heading containing "UI"; the column is still `Red SHA`.
- A test that passed before its fix is a pin, never a red: put it in the `Historical SHA` table with its mutation proof.
- A merge of an older branch must not carry its `.superpowers/sdd/<other release>/lanes/<other lane>/` files into your
  diff: `git rm` them in a `docs:` commit.
- Never write files in the worktree while a test suite runs there (SideEffectGuard flags cwd changes).
- Before reporting done, run the gate's evidence checks yourself from your worktree:
  `uv run python C:/development/github/sharpit-wt/0.5.0-integration/scripts/dev/lane_gate.py <lane> --release 0.5.0 --worktree . --integration C:/development/github/sharpit-wt/0.5.0-integration --accept-unverified`
  (background) and fix every REFUSED line about findings.md / handoff.md / reds (refusals about review.md or gate/*.log
  are the coordinator's).
- Every full 40-char SHA you write in evidence comes from `git rev-parse <short>` (or `git log --format=%H`), never typed
  or completed from memory: the gate refuses an unknown SHA (lane A-mysql recorded three invented full SHAs).

## Gate format reminders (2026-11-04)

- `review.md` ends with the exact line `VERDICT: APPROVE`.
- A lane plan's `## Must-cover` names test ids, even for a speed lane.
