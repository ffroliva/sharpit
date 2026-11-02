# G3 handoff

Implementer: Claude Code / claude-sonnet-5-5

## Status

- DONE (pending gate line below). Tasks 1-3 complete; branch `lane/0.4.0-G3` on top of G1G2's head `ab1c5de`.
- Task 1: red `8bd33f7184e715062f1b387bef908ec5af65c9dd`, fix `cb1f8f9093fccf5b4aa0c915b5740ed0d3e85fd6` (`sharpit.report` summary renderer + CLI).
- Task 2: red `c3ba9201e065905f613b80608dae5965af0c756f`, fix `912b1fc` (root `action.yml`).
- Task 3: `lane-report.md` (local wheel built; the action itself was not run, per the lane brief).
- Red tables: see `findings.md` (19 tests, all `AssertionError` on stubs).

## Decisions

- No YAML parser dependency: the static tests use a small reader for the fixed shape of `action.yml`, and *execute*
  the Run step's Python (argv-echo runner) and the Install step's shell, so quoting/shlex is tested behaviourally.
- Escaping: backslash-escape `` \ ` * _ [ ] < > | & ~ ``, collapse CR/LF to a space; same escape for every value.
- Findings sorted by severity then fingerprint; top 20 shown, `**Findings:**` is the full count.
- Install step rejects values other than `pip`/`none` (exit 1). Summary step is `if: always()` and only warns on
  failure, so the pytest exit code is never hidden.
- Literal pin is `sharpit==0.4.0` (the package is still 0.3.0 until `/sharpit:release`).
- Reds were re-amended locally (before any later commit) twice to fix test bugs found while writing the fix.

## Needs from coordinator

- None outside the May-touch list. G1G2's two foundation-test updates (see its handoff) still apply to the full suite.
- `/sharpit:release` must bump the `sharpit==` literal in `action.yml` together with `__version__`.

## Gates
(gate results appended after the final frozen run)
