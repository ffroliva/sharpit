# handoff: g1g2-red-audit

Implementer: claude-opus subagent
Branch: `fix/0.4.0-g1g2-red-audit` (from release/0.4.0 at `34f1689`)

## What changed

- **Audit of the 11 G1G2 tests merged with a ruling** (`docs/reports/2026-11-02-g1g2-red-audit.md`): one wrong-value
  mutation per test on the current code. 10 catch their defect with an AssertionError in their own file. One
  (`test_vulnerability_findings_excluded_from_baseline`) caught only the removal of both exclusions; two new tests
  cover one half each (`3e57653`). Review round: five more `baseline.py` mutations (the exclusions repeated in
  `compare()`, the fixed-entry filter, both `.lower()` folds) survived the whole suite; five new tests catch them
  (`4d99d5b`).
- **One red rule** in `scripts/dev/lane_gate.py` (`is_red`, `red_verdicts`): an AssertionError or a pytest.raises DID
  NOT RAISE counts only when its last frame is under `tests/` (a test file or a helper), judged relative to the tree
  pytest ran in. No frame means it is not a red (fails closed). A setup/teardown error outranks a failure in the same case.
- **`scripts/dev/red_check.py`**: the worker-side check before a `test:` commit. It shares lane_gate's rule, loading
  it by file path. It expands files, normalises ids, runs each id in its own pytest call with a 900 s timeout and the
  tree's `src` first, and prints pytest's tail under a verdict that is not RED. Collection and fixture errors and a
  collection timeout get separate labels. Output is ASCII, and it warns about uncommitted `src/`/`tests/` files.
- **Docs**: `docs/development/workflow.md` section "Before every `test:` commit: `red_check`" (a working stub
  example, what it checks and what only the gate checks); one pointer line in `AGENTS.md`.

## Gates run (at `e95b53f`)

- `uv run ruff check`: all checks passed; `uv run ruff format --check`: 471 files already formatted
- `uv run pyright`: 0 errors, 0 warnings
- `pytest tests/scripts` (`-n 4`): 145 passed
- `pytest tests/engine/testsession tests/test_code_shape.py tests/engine/test_import_boundary.py` with `tests/scripts`
  at `7bf749d`: 341 passed
- Red replay of every `findings.md` row at its Red SHA (the integration gate's own `red_integrity` and
  `replay_refusals`, a detached tree, `PYTHONPATH` = that tree's `src`): every row is an AssertionError red, and
  each passes at the head.

Not run: the full suite on the head. The mutation runs of the whole suite (M18–M22) ran it five times at `4d99d5b`'s
parent; only the two overhead-budget tests failed, mutated and unmutated alike, on a loaded machine.
