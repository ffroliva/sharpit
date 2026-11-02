# G3 lane report

- Wheel built locally (no network publish): `...\0.4.0-integration\.superpowers\sdd\0.4.0\logs\G3-wheel\sharpit-0.3.0-py3-none-any.whl`
  (version is still 0.3.0: the bump is `/sharpit:release`'s job; `action.yml` pins the literal `sharpit==0.4.0`).
- The action was NOT executed (lane brief: never run the action for real). Its definition is covered by
  `tests/action/test_action_definition.py`, which runs the Run step's Python against an argv-echo runner and the
  Install step's shell with `none` / invalid values.
- Summary step run from the wheel in an isolated env:
  `uv run --no-project --isolated --with <wheel> python -m sharpit.report summary G3-sample-report.json` -> rendered
  Markdown (status fail, mode report-only, 1 finding, `a|b` escaped as `a\|b`), exit 0.
- Known limit: with `install: none` and a non-`python` runner (e.g. `uv run pytest`), the summary step's bare
  `python -m sharpit.report` needs sharpit importable by that `python`; on failure it only warns.
