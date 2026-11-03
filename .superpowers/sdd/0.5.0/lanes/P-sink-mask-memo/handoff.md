# P-sink-mask-memo handoff

Implementer: Claude subagent (claude-opus-5-5)

## Status

Tasks 1-3 done. Council tasks skipped (the coordinator runs the council on the finished diff).

## What changed

`src/sharpit/engine/testsession/sink.py`: `self._mask_sql = functools.lru_cache(maxsize=1024)(self._mask)` built in
`TestSessionSink.__init__`, used by `on_sql` for the fingerprint key and the first-sight statement text. Per sink (the
sink owns one masker for its whole life), so no result crosses sinks or masker settings; the cache stores the masked
output only. Exception messages, app titles and the unattributed top list keep calling `_mask` directly.

## Commits

| Commit | What |
|---|---|
| 18eb9f014f5fb7f9ddd2a4b6ac65edbb129ac04a | test: two safety pins (mutation-proven, see findings.md) |
| e1559d3b441fd07381a054c49a77a1c170f12121 | test: budget red |
| 278e88cb6c1d7dca6b544b0c51b65636b54ef027 | fix: the memo |

## Red SHAs

| Test | Red SHA | Assertion message |
|---|---|---|
| tests/engine/testsession/test_sink_overhead.py::test_sink_on_sql_repeated_statement_overhead_budget | e1559d3b441fd07381a054c49a77a1c170f12121 | `overhead 47.770 µs ... budget 30.000 µs` |

## Must-cover

| Test | Exists | Passes at head |
|---|---|---|
| tests/engine/testsession/test_sink.py::test_masked_fingerprint_memo_never_returns_an_unmasked_value | yes | yes |
| tests/engine/testsession/test_sink.py::test_masked_fingerprint_memo_keys_on_masker_settings | yes | yes |
| tests/engine/testsession/test_sink_overhead.py::test_sink_on_sql_repeated_statement_overhead_budget | yes | yes |

## Questions for the coordinator

1. Add `"test_sink_overhead.py",  # lane P-sink-mask-memo` to `TIMING_MODULES` in `tests/conftest.py` (outside this
   lane's May-touch). Until then `tests/test_overhead_harness.py::test_every_budget_module_runs_last` fails at this head
   with `['test_sink_overhead.py']` missing.

## Decisions

- The two safety tests are pins, not reds: the base masks on every call. Mutation proofs in findings.md.
- `Masker.capture_parameters` is a public mutable attribute; nothing mutates a sink's masker after construction, so the
  memo keys on the sink alone. A caller that mutated it mid-session would see stale masked text for already-seen SQL
  masked under the setting at first sight. sharpit never does that (the report masker is built per sink).
- No session-end clear: the cache lives and dies with the sink (one per session/worker).

## Gates

- `ruff check`: all checks passed; `ruff format --check`: 676 files formatted; `pyright`: 0 errors.
- Full suite (`-n 4`, log `0.5.0-integration/.superpowers/sdd/0.5.0/logs/P-sink-mask-memo-pytest.log`): 5306 passed,
  28 skipped, 3 failed:
  - `tests/test_overhead_harness.py::test_every_budget_module_runs_last` and
    `::test_budget_order_check_survives_a_fixture_conftest`: `['test_sink_overhead.py']` missing from `TIMING_MODULES`
    (question 1 above; the coordinator's conftest edit fixes both).
  - `tests/fastapi/test_security_logs_overhead.py::test_security_logs_hook_overhead_budget`: overhead 7.7 µs, noise
    16.6 µs ("suspect a busy machine"); passes alone (2 passed). This lane does not touch the security-logs hook.

## How to resume

Branch `lane/0.5.0-P-sink-mask-memo`; all work committed. Remaining: nothing in the lane plan.
