# T-swallowed-2 handoff

Implementer: claude-flavio opus
Status: DONE_WITH_CONCERNS (load-sensitive budgets only, see Gates)

## Done
- Task 1 pins `5ba446c00c95aa7ef379f6db48f00ce4e36acb2f` (`test: pin swallowed-error bench cases`): twins in
  `tests/fixtures/apps/swallow_twins/` (planted library under `site-packages/` logs WARN then re-raises),
  `tests/pytest_plugin/test_plugin_swallowed_bench.py` — all four Must-cover tests passed first time; mutation proofs
  in `findings.md` (Historical SHA). Loop: 200 iterations -> 1 finding (200 with both dedup layers removed).
- Task 2 probes, both RED at `0dc5568ac00edbee3794dc1ffe68d157101a909b` (red_check: RED; replayed in a detached tree):
  - `test_helper_that_logs_is_not_a_swallow` -> fixed in `93c22a3b4a72703f1758b20a7c8e3032a4666aa5`: a call passing
    the bound exception name (`self._report(e)`, positional or keyword) counts as handled.
  - `test_non_logger_error_call_is_not_logging` -> fixed in `9503c401b309ea5ba1fe7f5a2f074aa71518ebd1`: an attribute
    log call counts only when its receiver chain names `log`, `logger`, `_log`, `_logger`, `LOG`, `LOGGER`, `logging`,
    `warnings`, `getLogger`, `get_logger`, or a module-level name assigned from `getLogger(...)`/`get_logger(...)`/
    `loguru.logger`. Guard test `test_logger_receivers_still_count_as_logging` (self.logger, module logger,
    `logging.getLogger(__name__)`, annotated structlog logger, `log.bind(...)`).

## Fix round 1 (review.md finding 1, major)
- Reds at `84f4d789c6438294c524a713d063870c82b8fdea`, fixed in `bef2d10f8d6cbf84f97af9fb72c2ab6467a0cc85`.
- Sink rule (`swallowed.py` `_handles`): a clause handles the exception when its body (1) raises; (2) returns a call
  with `status_code=` a constant >= 400 or `HTTP_4xx/5xx_*` name; (3) calls a logger (receiver rule of 9503c40) or
  `warnings`; (4) calls an error tracker: any `*.capture_exception` / `capture_exception`, `rollbar.report_exc_info`,
  `bugsnag.notify`; (5) hands the caught name to a function/method defined in the same module whose own body (one
  level, `ast.walk` of the def, no call chase) does (1), (3) or (4). Builtins (`str`, `repr`, `print`, `isinstance`,
  `setattr`) and methods on local values (`errors.append`, `metrics.increment` on a non-import) are not handling.
- Fail-safe kept (`_hands_on`, comment on the line): a target that cannot be read here — an imported or unknown bare
  name, `self.`/`cls.` method not defined in the module (inherited), a method on an imported module, a dynamic call
  (`getattr(self, name)(e)`) — counts as handling, so it is never reported on a guess. The 0.5.0 red
  `test_helper_that_logs_is_not_a_swallow` (undefined `self._report`) stays green under that rule.
- Spec §14 note for the coordinator: replace entry (1) above with this sink rule.

## Decisions
- Bare-name calls (`warn("x")`, `log(...)`) keep 0.4.0 behaviour (count as logging): no proven edge, and restricting
  them would add false positives for `from warnings import warn`.
- The receiver walk goes through attributes and calls (`log.bind(x=1).warning`), so chained structlog loggers still count.
- Spec §14 entries: the spec is outside this lane's May-touch list, so they are not written there. Coordinator, add to
  0.5.0 §14: (1) `_passes`: handing the bound exception to any call counts as handled (accepts `print(e)`, no false
  positives); (2) `_LOG_CALLS` restricted to logger receivers as above.
- U17's 16-catch limit does not apply: facts are de-duplicated per handler and type (`record`) and again by
  fingerprint (`outcome.py`).

## Gates (fix round 1, head bef2d10)
- ruff check: all passed; ruff format --check: formatted; pyright: 0 errors. Targeted (testsession, swallowed bench,
  import boundary, code shape): 249 passed.
- Full suite `-n auto`: 4424 passed, 9 skipped, 3 failed, 1 error — budgets `test_sqlalchemy_lazy_relationship_hook_overhead_budget`,
  `test_statement_overhead_budget`, `test_request_overhead_budget` and `test_osv.py::test_follows_pagination_until_token_absent`
  (error). Run alone: statement + OSV passed; the other two failed once, then passed at head (2 passed) and on the untouched
  base `3ea8201` (2 passed): load noise. Files and budgets untouched by this lane.
  Log: `0.5.0-integration/.superpowers/sdd/0.5.0/logs/T-swallowed-2-fix1-pytest.log`.

## Gates (head 9503c40)
- ruff check: all passed; ruff format --check: 497 files formatted; pyright: 0 errors.
- Full suite `-n auto`: 4406 passed, 9 skipped, 2 failed — `test_statement_overhead_budget`,
  `test_capture_overhead.py::test_request_overhead_budget` ("within the noise: suspect a busy machine"); both pass run
  alone (2 passed, 7.4 s). Files untouched by this lane; budgets untouched.
  Log: `0.5.0-integration/.superpowers/sdd/0.5.0/logs/T-swallowed-2-pytest.log`.

## Note to the bench tracker owner
U1/U19: fixed-by-design in 0.4.0, pinned by `test_library_warn_does_not_hide_app_swallow`,
`test_logged_handler_is_not_a_finding`. U2: `test_db_error_swallow_found`. U17 loop: `test_swallow_in_loop_is_one_finding`.
New in 0.5.0: `test_helper_that_logs_is_not_a_swallow`, `test_non_logger_error_call_is_not_logging`.

## Resume
Nothing left. Next: coordinator review + `lane_gate.py T-swallowed-2 --release 0.5.0`.
