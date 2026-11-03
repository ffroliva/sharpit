# Handoff: lane F5a-core (sharpit 0.5.0)

Implementer: claude-flavio / Claude Opus 5.5 (claude-opus-5-5)
Branch `lane/0.5.0-F5a-core`, from `release/0.5.0` @ 836d3fd. Plan: `docs/superpowers/plans/2026-11-03-sharpit-0.5.0/F5a-foundation.md` (F5a-core Tasks 2-4; the Task 1 council is the coordinator's, on this diff). Spec §4.3, §4.4, §5.

## Status

DONE: Tasks 2, 3, 4 done. Q1 resolved by the coordinator (May-touch amended): merged release/0.5.0 (335e104, no duplicated top-level defs), dogfood fix 8c58f6ec388f2ec61d789166946d339c80436b4e. `pytest -n 4 tests/test_dogfood_sqla.py tests/engine/advisors`: 132 passed; ruff, format, pyright clean.

| Task | Red | Fix |
|---|---|---|
| 2 RuleResult contract + enum parity | 4517a91801df63ea7ce87824707c92bf6addbdb1 | 3fdb8917b41fb3d2d59231d31c0514fefca9bc81 |
| 3 advisor scan core, rest-api on it | 0470e2df9afc737f4470a2025240a377b50c45dc | 7027c61224c2035ea055705d0ba02ac6431af7a0 |
| 4 registry prefix ownership + pytest discovery | 3da97c96f8631666e321edd1ac24909cf8ede63f | a3f953100f3981ee794a095d00d36e6ab6f5fc3a |

## Reds

| Test | Red SHA | Assertion message |
|---|---|---|
| tests/engine/advisors/test_scan.py::test_enum_values_checked_against_golden | 4517a91801df63ea7ce87824707c92bf6addbdb1 | `assert 'results[].status' in ''` |
| tests/engine/advisors/test_scan.py::test_advisor_core_matches_rest_api_post_scan_golden | 4517a91801df63ea7ce87824707c92bf6addbdb1 | `assert 'FAILED' == 'VIOLATION'` |
| tests/engine/advisors/test_scan.py::test_advisor_core_pre_scan_shape_all_four_goldens | 0470e2df9afc737f4470a2025240a377b50c45dc | `<id>/captured.json parity: localOnly: missing from payload; ...` |
| tests/engine/advisors/test_scan.py::test_advisor_core_single_flight | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert None == 'sharpit action already in progress'` |
| tests/engine/advisors/test_scan.py::test_advisor_core_violations_paged | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert [] == ['v 1', 'v 2']` |
| tests/engine/advisors/test_scan.py::test_advisor_core_unknown_rule_404 | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert None == 404` |
| tests/engine/advisors/test_scan.py::test_advisor_core_masks_every_string | 0470e2df9afc737f4470a2025240a377b50c45dc | `assert [] == [['message password=******']]` |
| tests/engine/advisors/test_scan.py::test_registry_owns_by_prefix | 3da97c96f8631666e321edd1ac24909cf8ede63f | `assert None == '<advisor>'` |
| tests/engine/advisors/test_scan.py::test_pytest_plugin_discovers_advisors_from_registry | 3da97c96f8631666e321edd1ac24909cf8ede63f | `assert [] == ['rest-api', 'security']` |

Must-cover: all five exist in `tests/engine/advisors/test_scan.py` and pass at the head. Mutation proofs and the existing tests changed: `findings.md`.

## Decision for the council: the [AMBIG] status vocabulary (spec §4.3 reading)

Spec §4.3: "vocabulary from the contract and goldens, not from `advisors/rules.py:13`; result status `VIOLATION` (and the passing value the contract names)". The contract (`docs/reference/BOOTUI-CONTRACT-0.4-WAVE-B.md:67`) names `PASS`, `VIOLATION`, `SKIPPED`, `ERROR` (`*RuleSupport.java:10-13`). Implemented: `Status = Literal["VIOLATION", "PASS", "SKIPPED", "ERROR"]` (`ERROR` for advisor `analysisErrors` rows; nothing emits it yet). This differs from the plan table's `PASSED`; the council settles it. Changing it is one literal in `rules.py`, one in `report.py` and the `enums.json` files.

- `DISABLED`: in the scan-status enum (`NOT_SCANNED | SCANNED | PARTIAL | ERROR | DISABLED`), set by an advisor's `Evaluation.status`; the core does not decide it.
- "no base package -> `SCANNED` with a message": the advisor's `run` returns `Evaluation("SCANNED", <message>, ...)`; the core has no rule of its own.
- A rule whose every occurrence is dismissed reports `PASS` (was `PASSED`) and stays in `results` (sharpit §5.6 deviation), so `results[].status` allows `VIOLATION` and `PASS`.
- Unchanged: `AdvisorRun.status` (`PASSED/FAILED/UNKNOWN/SKIPPED`, `sharpit-report/1`) in `advisors/findings.py` and `testsession/outcome.py`.

## Consumer interface (advisor lanes)

| Symbol | Where | Contract |
|---|---|---|
| `ScanSpec(id, analyzer, disclaimer, not_scanned_message)`; `.operation` = `f"{id}-scan"` | `engine/advisors/scan.py` | the advisor's texts; the single-flight operation name |
| `Evaluation(status, message, evaluated, findings, evidence, detail=None)` | same | what `run` returns: scan status, message, ids of the rules that ran, raw `Finding`s, `evidence(...)`, the advisor's own facts for its hooks |
| `Scope(lists, counts)` | same | `lists` at the top level only (e.g. `filterChains`); `counts` at the top level and in `scan` (e.g. `filterChainsAnalyzed`) |
| `AdvisorScan(spec, rules, run, *, scope, extra_sections=no_extra_sections, dismissals, masker, single_flight, max_retained)` | same | `run(request) -> Evaluation`; `scope(Evaluation or None) -> Scope`; `extra_sections(Evaluation or None) -> Mapping` (e.g. `analysisErrors`, `diagnostics`, `suppression`); both hooks get `None` before the first scan |
| `.report()`, `.scan(request=None)`, `.violations(rule_id, scan_id, offset, limit, max_results=1000)` | same | report never scans; scan raises `ActionBusy` (route -> 409 `"sharpit action already in progress"`); violations raise `AdvisorViolationError` (400/404/409) |
| masking | same | finding target/message masked at intake (before retention); scan message, evidence limitations, scope lists and extra sections masked at render; static texts (spec, rule definitions) are not |
| `build_report(...)`, `violating(results)`, `mask(masker, text)` | same | the shared report builder; violating rules sorted severity, count desc, id |
| `RuleResult.sample_locations` -> DTO `sampleLocations` (default `[]`) | `engine/advisors/rules.py` | D4 fills it |
| `violationDetails` | core | retention details + `locationNotes: []`, `changes: null` |
| registry rows | `engine/advisors/registry.py` | `SEC-` security, `ARCH-` architecture, `FASTAPI-`/`SPRING-` fastapi, `DB-` database-advisor (`<PREFIX>-[A-Z0-9][A-Z0-9-]*`), fingerprint `<advisor>:<rule>:<16 hex>`, gated by each panel flag |
| `AdvisorSpec.assess` | registry | the module whose `assess(model, masker, *, fail_on, app, dismissed, **options) -> AdvisorRun` the pytest plugin runs: `sharpit.engine.collectors.<id with _>.service` (rest-api: `...collectors.restapi.service`). A missing module is skipped (no pytest assessment); any other import error raises |
| `advisor_assessors()` | `pytest_plugin/apps.py` | implemented advisors' assessors, in registry order |
| `assert_enum_values(sharpit_id, name, payload)` | `tests/golden.py` | checks the values at the paths in `fixtures/bootui/2.2.0/<id>/enums.json` (`{"<path>": [allowed]}`, list items as `items[].key`) |

`enums.json` written for rest-api, security, architecture, fastapi, database-advisor: `scan.status`, `severityCounts[].severity`, `results[].severity`, `results[].status`, and (not rest-api) `analysisErrors[].status`/`.severity`. Advisor lanes may add paths once G0 lands.

## Questions for the coordinator

- **Q1 RESOLVED (coordinator: yes; fixed in 8c58f6e):** `tests/test_dogfood_sqla.py:91` filters rule results on `r["status"] == "FAILED"`; with `VIOLATION` it collects nothing and `test_rest_api_scan_flags_poor_design` fails. The file is outside May-touch. Fix: `"FAILED"` -> `"VIOLATION"` on that line. Please amend May-touch or apply it at merge.
- **Q2 (to the council, with the PASS vs PASSED choice):** G0 recapture through `scripts/sanitize_golden.py` keeps `nullable.json`/`meta.json`; check that it also keeps `enums.json` (not in May-touch, not verified).

## Gates (head a3f9531 + evidence commit)

- ruff check: all passed; ruff format --check: 550 files formatted; pyright: 0 errors.
- Full suite (`-n 4`, log `0.5.0-integration/.superpowers/sdd/0.5.0/logs/F5a-core-full.log`): 4668 passed, 9 skipped, 2 failed:
  - `tests/test_dogfood_sqla.py::test_rest_api_scan_flags_poor_design`: Q1, fixed in 8c58f6e (passes).
  - `tests/test_overhead_harness.py::test_every_budget_module_runs_last`: not this lane. `ImportError: cannot import name 'TIMING_MODULES' from 'conftest'` resolves to `tests/fixtures/apps/unbounded_read/conftest.py` when that conftest is imported first; reproduced with `pytest tests/fixtures tests/test_overhead_harness.py`, while the file passes alone (16 passed). The lane diff touches none of `tests/fixtures/apps`, `tests/conftest.py`, `tests/test_overhead_harness.py`: a pre-existing order dependence.

## How to resume

Nothing open in the lane. If the council picks `PASSED`: change `Status` and the defaults in `rules.py`, `_mark` in `report.py`, and the `enums.json` files, and add a NEW test (never edit the red tests).
