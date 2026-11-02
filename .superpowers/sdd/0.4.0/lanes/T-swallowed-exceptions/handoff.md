# T-swallowed-exceptions handoff

Implementer: claude-flavio opus

## Status

DONE_WITH_CONCERNS (see "Left for others"). Tasks 0–5 complete on `lane/0.4.0-T-swallowed-exceptions`, based on
`494521f`. Full-suite result: see "Gates" below.

## Commits

| Task | Red SHA | Fix SHA |
|---|---|---|
| 0 predict | — (`predict.md`, CAUTION 7/10, committed with the Task 1 red) | — |
| 1 spike F1 | `29058b1b7e1a52f78172b3e4476512107fcdcb5d` | `c6c549347dfb1348c9aeed74530ff9f901b52639` |
| 2 predicate, first cut | `eb89f13f6acb1c2b273d988e886fab67ebeb0e67` | `c9a4307dcf8f847dea9b991a274ec8b1559ef358` |
| 2 predicate semantics | `d759f74222225b919b441de595d56f999c3932cd` | `679eef0f295e97a5c4be931b1f44e074fd02b3c6` |
| 3 monitoring capture | `8660ea5a238dec3173f153d384a417cedf7b651c` | `19353b5ee15d2d405fb248026847b7f88d142b1b` |
| 3 freed-id test superseded (xdist name collision) | Historical, mutation-proven | the `test:` commit after `2e40aef` |
| 4 gate, marker, report-only, baseline | `29716480fc7c3e62345bc2a0d47bd592f0797fe0` | `c6c549347dfb1348c9aeed74530ff9f901b52639` |
| 5 overhead budget | `025956260890a0c96e0ef8b6273e79dfae8b1f71` | `2e40aef0ed2910fcdf3a6f792bb8654eda6d568b` |

Per-test red ids and assertion messages: `findings.md` (each replayed at its red SHA with `--junitxml`).

## Decisions

- **Attach/detach through `session.py`.** `pytest_plugin/__init__.py` is outside the May-touch list, so the capture is
  attached in `session.py::pytest_collection_finish` (runs on every worker) and detached at the top of
  `session.py::pytest_sessionfinish`; `config.add_cleanup(capture.detach)` frees the id even when a later hook fails
  (`test_monitoring_tool_freed_at_session_end[True]`). Glue: `pytest_plugin/swallowed.py::attach_session/detach_session`.
- **Handler location.** `EXCEPTION_HANDLED`'s offset is the try's handler entry (`PUSH_EXC_INFO`, no line) on 3.12–3.14;
  the first following line is the first `except` header. Other offsets (cleanup `COPY/POP_EXCEPT/RERAISE`, `with`
  exits) are ignored. The clause that handled the exception is the first one that matches by builtin type; a clause
  naming a non-builtin exception counts as "may match" and stops the search (never a false positive).
- **Swallows** = bare / `Exception` / `BaseException` (also inside a tuple) and the clause body has no `raise` and no call
  named `debug|info|warning|warn|error|exception|critical|fatal|log`.
- **Facts** (`facts.py::SwallowedFact`): cwd-relative `path:line`, type name, `programmingError`; never message or locals.
  Deduped per phase; serialised in `PhaseFacts.to_json` (`swallowed`, read with `.get`, so older worker JSON loads).
- **Finding**: rule `sharpit.swallowed-exception`, target = location, identity = `location:Type` (fingerprint stable
  across tests and machines), `HIGH` for programming errors unless `allow_swallowed`, else `INFO`. `_finding` gained the
  keyword `severity` (default `HIGH`, existing fingerprints unchanged). `Budget.allow_swallowed: bool = False`
  (`TestFacts` JSON key `allowSwallowed`, read with `.get`).
- **Ids taken** → source `swallowed-exceptions` with `attached: false` and reason `sys.monitoring tool ids 3 and 4 are in
  use`; the existing outcome rule then makes the run `unknown` (fail closed; not a crash).
- **Static FASTAPI-ERR-001** lives in `restapi/rules.py` as `FASTAPI_ERR_001` + `swallowed_handler_violations(routes)`:
  reads and parses each route handler module's file (via `sys.modules[...].__file__`), never imports or calls.
  It is not in `RULES` (pinned to BootUI's 20 by `test_registry_covers_every_documented_id`).
- **Performance**: the per-event fact is cached per (code, offset, exception type) (`_fact`), after the budget test went
  red at ~6 µs/exception from `relpath` per event.

## Overhead (Task 5)

`tests/engine/test_swallowed_overhead.py`, 15 paired rounds of 1,000 loops × 3 handled exceptions (app narrow, app
swallow, library narrow). 10 runs on this machine after the fix: overhead 0.402–0.863 µs/exception, noise
0.095–0.403 µs. Budget `SWALLOWED_HANDLER_BUDGET = 1.5e-6` (new constant in the new file). Mutation proof: a 5 µs
busy-wait in the callback → `overhead 5.998 us/exception ... budget 1.500` (AssertionError). Not marked slow.

## Left for others (outside this lane's May-touch list)

1. Wire `FASTAPI-ERR-001` into the `rest-api` advisor run (`restapi/service.py`, `advisors/registry.py` fingerprint
   pattern): D4 or the coordinator. `swallowed_handler_violations` is ready to call.
2. The marker help line in `pytest_plugin/__init__.py:151` does not list `allow_swallowed`.
3. `report.py` renders the per-test budget without `allowSwallowed` (no report schema change in this lane).
4. User-facing text for README/skills is in `docs.md` in this folder (O3).

## Gates

- `uv run ruff check`: All checks passed. `uv run ruff format --check`: 485 files already formatted.
  `uv run pyright`: 0 errors.
- Full suite (`uv run pytest -q -n 4`, log
  `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\T-swallowed-exceptions-pytest.log`):
  `4 failed, 4317 passed, 9 skipped`. Failures: (a) `test_monitoring_tool_freed_at_session_end[False|True]`, a
  probe module name collision with `tests/engine/test_tools.py` under xdist (test defect), superseded by
  `test_monitoring_tool_freed_after_the_session` (see findings.md, Historical SHA); the collision is gone when both files
  run in one process. (b) Load-sensitive overhead budgets, both "within the noise" under `-n 4`:
  `test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget` (89.969 µs, noise 179.102,
  budget 35) and `fastapi/test_capture_overhead.py::test_request_overhead_budget` (0.207 ms, noise 0.040, budget 0.2).
  Both pass when run on their own (`3 passed` together with this lane's budget). Not raised; reported.
  This lane's own budget passed inside the loaded full run.

## How to resume

Branch head is the evidence commit after `2e40aef`. Targeted loop:
`uv run pytest -q tests/engine/testsession/test_swallowed.py tests/engine/restapi/test_swallowed_rule.py
tests/pytest_plugin/test_plugin_swallowed.py tests/engine/testsession/test_gates.py tests/engine/test_swallowed_overhead.py
tests/engine/test_import_boundary.py tests/test_code_shape.py` (needs `UV_LINK_MODE=copy`).
