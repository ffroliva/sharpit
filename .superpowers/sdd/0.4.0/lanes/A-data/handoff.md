# Lane A-data handoff

Implementer: agy claude-sonnet-5-5-high + claude-subagent sonnet (resume)

Status: DONE_WITH_CONCERNS (Tasks 1-6 done; see Needs from coordinator).

## How to resume

- Worktree `C:\development\github\sharpit-wt\0.4.0-A-data`, branch `lane/0.4.0-A-data`, base `d37c6f2` (lane F head).
- Every `uv` command needs `UV_LINK_MODE=copy`; use `uv run --no-sync` after the first `uv sync --extra test`.
- Pytest logs outside the worktree: `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\A-data-*.log`.
- Evidence files are gitignored: `git add -f .superpowers/sdd/0.4.0/lanes/A-data/<file>`.

## Done (commits)

| Task | Red | Fix |
|---|---|---|
| 1 nullable.json | n/a | `cbde0ee` |
| 2 collector | `eb6497d0b447b21b64abf030c177773bb278ed41` | `c092d59c41ec9086cecaffc65216d1d36d9ca6d9` |
| 3 detail | `d551cedd00ad87095df7c885782633cf78921298` | `482abf764a0d4029ece739ca71156c19eb77d255` |
| 4 routes/flag/MCP/safety | `d46519a8e5eb105d2b85e8d7e76675e151652467` | `c781bae0ee2cc0a38915e89e8a6d6b20273329ec` |
| 5 Svelte view | `7b5a0270cfc49c9f58dc3bc39a44a59f15ce5b52` | `ddfaffb204141385fe66f51f9ac33284e40d6e88` |

## Red-test replay table (real reds; see below)


UI reds (vitest, `ui/tests/component/data.test.ts`, SHA `7b5a0270cfc49c9f58dc3bc39a44a59f15ce5b52`) are not pytest-replayable.
`test_repositories_golden_parity` skips until G0a's golden merges, so it is not a named red.

## Red tests (gate format)

| Test id | Red SHA | Assertion message |
|---|---|---|
| tests/engine/test_data.py::test_lists_one_row_per_mapped_class | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 |
| tests/engine/test_data.py::test_no_models_is_unavailable | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'pass models= to sharpit.install' |
| tests/engine/test_data.py::test_empty_registry | eb6497d0b447b21b64abf030c177773bb278ed41 | assert False is True |
| tests/engine/test_data.py::test_configured_mapper_lists_relationships | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 |
| tests/engine/test_data.py::test_models_forms_dedupe | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 1 |
| tests/engine/test_data.py::test_a_registry_alone_is_accepted | eb6497d0b447b21b64abf030c177773bb278ed41 | assert [] == [<sqlalchemy.orm.decl_api.registry ...>] |
| tests/engine/test_data.py::test_only_strangers_is_unavailable | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'models= holds no declarative base or registry' |
| tests/engine/test_data.py::test_one_bad_mapper_drops_only_its_row | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 1 |
| tests/engine/test_data.py::test_sqlalchemy_absent | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'SQLAlchemy is not imported by this application' |
| tests/engine/test_data.py::test_sqlalchemy_older_than_two | eb6497d0b447b21b64abf030c177773bb278ed41 | assert None == 'SQLAlchemy 1.4.50 is imported, but sharpit needs 2.0 or later' |
| tests/engine/test_data.py::test_detail_by_bean_name | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None |
| tests/engine/test_data.py::test_detail_by_fq_name | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None |
| tests/engine/test_data.py::test_detail_by_simple_name | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None |
| tests/engine/test_data.py::test_detail_unknown_is_none | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None |
| tests/engine/test_data.py::test_detail_simple_name_collision | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None |
| tests/fastapi/test_data_api.py::test_repositories_lists_the_models | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 |
| tests/fastapi/test_data_api.py::test_panel_disabled_403 | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 403 |
| tests/fastapi/test_data_api.py::test_mcp_lists_read_tool_only | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 'get_data_repositories' in {...} |
| tests/engine/test_data.py::test_cross_registry_new_mapper_is_not_configured | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert ['_check_configure', ...] == [] |
| tests/engine/test_data.py::test_join_mapped_class_keeps_its_row | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 1 |
| tests/engine/test_data.py::test_failing_field_drops_only_that_field | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 1 |
| tests/engine/test_data.py::test_warnings_mask_exception_text | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 'hunter2secret' not in 'Skipping a mapper ...' |
| tests/engine/test_data.py::test_mapped_class_with_a_mappers_column_is_accepted | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert 0 == 2 |
| tests/engine/test_data.py::test_registry_lookup_never_runs_class_descriptors | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | assert ['run', 'run', 'run'] == [] |
| tests/engine/test_data.py::test_lazy_is_a_strategy_name[None-noload] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'None' != 'noload' |
| tests/engine/test_data.py::test_lazy_is_a_strategy_name[True-select] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'True' != 'select' |
| tests/engine/test_data.py::test_lazy_is_a_strategy_name[False-joined] | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | lazy 'False' != 'joined' |
| tests/engine/test_data.py::test_registry_subclass_new_mapper_is_not_configured | 3ee9fe924d371ac21a821cc6c7d1fd8ae3228d9d | assert [_check_configure, ...] == [] |

## Historical reds (test or fixture changed after the red commit)

| Test id | Historical SHA | Assertion message |
|---|---|---|
| tests/engine/test_data.py::test_unconfigured_mapper_is_not_configured | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 |
| tests/engine/test_data.py::test_a_mapper_added_after_configure_is_not_configured | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 3 |
| tests/engine/test_data.py::test_broken_registry_degrades | eb6497d0b447b21b64abf030c177773bb278ed41 | assert 0 == 2 |
| tests/engine/test_data.py::test_detail_unconfigured_has_no_methods | d551cedd00ad87095df7c885782633cf78921298 | assert None is not None |
| tests/fastapi/test_data_api.py::test_get_never_configures_mappers | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 |
| tests/fastapi/test_data_api.py::test_panel_listed_when_implemented | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert None is not None |
| tests/fastapi/test_data_api.py::test_detail_by_name | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert 404 == 200 |
| tests/fastapi/test_data_api.py::test_detail_404_empty_body | d46519a8e5eb105d2b85e8d7e76675e151652467 | assert b'{"error":"Not Found"}' == b'' |

## UI reds (vitest)

| Test file | Commit | Assertion message |
|---|---|---|
| ui/tests/component/data.test.ts (4 view tests) | 7b5a0270cfc49c9f58dc3bc39a44a59f15ce5b52 | expected the placeholder text to contain 'Owner' |
| ui/tests/component/data.test.ts (4 round-1 tests) | 876bbda60cb23adf4a356b452de7f1423f2ab5cb | expected calls to include 'api/data/repositories/app.b.Owner' and others |

## Gates (worktree head)

- ruff check and ruff format --check: clean. pyright: 0 errors. vitest 262 passed, `npm run check` (tsc) clean.
- Full pytest `-n 4`: 3595 passed, 6 skipped, 10 failed. 2 are overhead budgets that passed alone (load from a concurrent
  `npm ci`). 8 are count-pinned tests outside my May-touch list that now see +1 panel, +1 tool, +2 routes (see below).

## Live check

In-process on `examples.fastapi_sqla.app.create_app()` (no port bound): GET `/sharpit/api/data/repositories` gives 200,
`total 2` (Owner, Pet), `relationships: null`, `unavailableReason` "Mappers are not configured yet..."; GET
`.../repositories/Owner` gives 200 with `methods: []`; GET `.../repositories/Nope` gives 404 with an empty body.

## Decisions and deviations

- The red commits of Tasks 2 and 3 were recreated once, before any SHA was recorded, to fix two defects in my own
  tests found at the first green run: (a) `test_models_forms_dedupe` expected one warning on an unconfigured base
  (the unconfigured warning is a second one); (b) classes built by `type(...)` and not held were garbage collected
  (a registry holds classes weakly), which made the detail collision test and the late-mapper test flaky.
  The branch is local and unpushed; history was rebuilt with `git reset --hard` to `cbde0ee` and replayed.
- `relationships` are read only when **every** mapper of that registry is `configured`, not just the row's own
  mapper: `Mapper.relationships` calls `_check_configure`, which configures the whole registry when a later mapper is
  pending (pinned by `test_a_mapper_added_after_configure_is_not_configured`). A registry whose configure failed
  (`test_broken_registry_degrades`) also gives `relationships: null` for all its classes.
- Unconfigured: row `relationships` is `null`, report `warnings` holds `UNCONFIGURED`, and report `unavailableReason`
  is `UNCONFIGURED` while the rows are still listed (`springDataPresent` stays true). Review Focus 1's "naming the
  class" is satisfied by the row with `relationships: null`; the reason text is the plan's constant.
- Accepted `models=` entries: a declarative base, a `registry`, or a mapped class (resolved through its `.registry`).
- Extra keys (spec §11 log): report `unavailableReason`, `warnings`; row `table`, `relationships`; detail `table`,
  `unavailableReason`. Detail `origin` is `"APPLICATION"` (spec §7), outside BootUI's enum `FRAGMENT, QUERY, DEFAULT,
  CRUD, DERIVED, ANNOTATED`.

## Needs from coordinator

- Count-pinned tests outside the May-touch list must be updated at integration (data adds panel `data`, tool
  `get_data_repositories`, routes `/api/data/repositories` and `/api/data/repositories/{name:path}`; MCP toolCount 18 to 19,
  CLI tool count +1): tests/engine/test_mcp.py::test_tools_list_has_no_action_tool,
  tests/engine/test_tools.py::test_catalogue_names_panels_actions_and_schemas,
  tests/fastapi/test_install.py::test_panels_platform_fastapi_and_ids and ::test_mvp_panels_stay_available,
  tests/fastapi/test_mcp_api.py::test_mcp_server_status_shape, tests/fastapi/test_cli_api.py::test_cli_status_shape_matches_contract,
  tests/test_safety_matrix.py::test_get_route_table_is_complete, tests/test_foundation_suite_equivalence.py.
- The UI test lives in ui/tests/component/data.test.ts (the repo's harness folder), not ui/src/views/Data.test.ts.
- ui/src/lib/panels04/data.ts flipped; the built ui static assets were not rebuilt (no npm run build).

- Golden fixtures for `data` (`tests/fixtures/bootui/2.2.0/data/repositories.captured.json` and
  `repository-detail.captured.json`, or `.provisional.json`) do not exist in this tree; neither G0a nor another worker
  has supplied them, and the lane may not write them (O2).

## Fix round 1 (head d97f0160000c90844caf1f2eec9032f502c9b2bd)


Also done in this round: test hygiene commit (shared spy helper tests/data_support.py, real ported names, exact golden
guard, safety rows pass models=, panel assertion). Deviations: (a) a real SQLAlchemy registry missing `_new_mappers` fails
closed, a foreign duck-typed registry (the SimpleNamespace fakes of test_one_bad_mapper...) falls back to per-mapper flags,
so the pinned existing test still passes; (b) detail does NOT carry `relationships` because `test_detail_by_bean_name`
pins the detail key set; the drawer takes lazy from the list row when the detail has none, and I dropped my own
`test_detail_carries_relationships` (it contradicted that pin; it is not in the table); (c) the first vitest
test's detail URL changed to the FQ name because the view now requests by repositoryInterface (vitest is not gate-replayed);
(d) `/panels` has no actionCapable key: the test asserts `readOnly is False` and `Panel.action_capable is False`.

## Fix round 2 (head 3464bbdeff142dacd9dc5df6fe3626c2fe9d3aae)


Deviation (a) corrected: registries are recognised by MRO.
